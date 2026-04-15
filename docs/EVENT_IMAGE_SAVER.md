# Event Image Saver

트래킹 이벤트(created, weigher_in/out, final_baler, exited, removed 등)마다
현재 프레임을 이미지 파일로 저장하는 기능입니다.

## 설계 원칙

- **비침투적(Non-intrusive)**
  기존 로직 수정 없음. 새 모듈(`src/rubber_tracker/event_image_saver/`) + `run.py` 5줄 추가만 필요.
  기존 `TrackEventHandler`는 그대로. 그 앞단에 `ImageEventCapture` decorator를 끼워 프레임만 캐싱.

- **비동기(Async)**
  저장은 별도 워커 스레드(`CustomThread`). 이벤트 콜백은 큐에 enqueue하고 즉시 리턴하므로
  메인 파이프라인(감지/트래킹/네트워크)에 지연을 주지 않음.

- **안전(Fail-safe)**
  - `enabled=false` 기본값 → 운영 영향 zero
  - 모든 예외를 내부에서 흡수 → 다른 콜백/파이프라인 보호
  - 저장 디렉토리 생성 실패 시 → 자동 disable
  - 큐 오버플로 시 → 드롭 + 주기적 경고 로그

- **설정 가능**
  `config/base.yaml` → `event_image_saver:` 섹션에서 모든 동작 조절.
  프로파일(`config/profiles/*.yaml`)에서 오버라이드 가능.

## 모듈 구조

```
src/rubber_tracker/event_image_saver/
├── __init__.py           # 패키지 진입점
├── frame_store.py        # 스레드 안전 프레임 캐시 (~90줄)
├── event_capture.py      # TrackEventHandler wrapper (~40줄)
└── saver.py              # 비동기 저장 서비스 (~280줄)

tests/
├── conftest.py           # 외부 의존성 stub (개발 환경용)
└── test_event_image_saver.py  # 25개 단위/통합 테스트
```

## 동작 흐름

```
[Detection Pipeline]
  └─ on_created(track_id, bbox, conf)
  └─ on_updated(track_id, bbox, frame, age)    ← frame이 여기서만 handler로 전달
  └─ on_removed(track_id, bbox, age)
         │
         ▼
[ImageEventCapture (wrapper)]
  └─ on_updated: frame을 FrameStore에 캐싱 → inner handler 호출
  └─ inner handler가 내부에서 weigher_in/weigher_out/removed 등 이벤트를 emit
         │
         ▼
[TrackManager.callbacks]
  └─ image_saver.on_event(evt)  ← enqueue to save_queue
         │
         ▼
[Worker Thread]
  └─ save_queue.get() → frame + bbox 주석 → cv2.imwrite
```

## 설정

`config/base.yaml`:

```yaml
event_image_saver:
  enabled: false                    # 기본 비활성
  save_dir: "results/event_images"  # 저장 경로 (프로젝트 루트 상대)
  draw_bbox: true                   # bbox + 라벨 주석
  draw_all_tracks: true             # 모든 활성 트랙 표시 (연회색)
  organize_by_event_type: true      # 이벤트 타입별 하위 폴더
  queue_size: 500                   # 비동기 큐 크기
  jpeg_quality: 90                  # JPEG 품질 1~100
  enabled_event_prefixes: ~         # null = 전체. 리스트로 필터링 가능
```

### 이벤트 필터링 예시

특정 이벤트만 저장하려면 `enabled_event_prefixes`에 접두사 리스트 지정:

```yaml
event_image_saver:
  enabled: true
  enabled_event_prefixes:
    - "weigher_in"      # weigher_in_zoneA, weigher_in_zoneB 등
    - "weigher_out"
    - "final_baler"
    - "removed"         # 불량 판정 (rejected=true)
```

## 저장 파일 구조

```
results/event_images/
├── weigher_in/
│   ├── 20260413_143012_341_weigher_in_zoneA_EXT1234.jpg
│   ├── 20260413_143018_102_weigher_in_zoneA_EXT1235.jpg
│   └── ...
├── weigher_out/
│   └── ...
├── final_baler/
│   └── ...
├── removed/
│   ├── 20260413_143025_844_removed_none_EXT1234_REJECTED.jpg
│   └── ...
└── exited/
    └── ...
```

**파일명 규칙:**
`{타임스탬프}_{이벤트타입}_{외부ID}_{REJECTED 여부}.jpg`

- 타임스탬프: `YYYYMMDD_HHMMSS_밀리초`
- 이벤트타입: `event_service.py`가 생성한 `type` 필드 (예: `weigher_in_zoneA`)
- 외부ID: MES가 부여한 고무의 외부 ID
- REJECTED: 불량 판정 시에만 추가

## 이미지 주석

`draw_bbox=true` 시:
- 모든 활성 트랙: **연회색 박스** + `#{track_id}` 라벨
- 이벤트 레이블(상단): `이벤트타입 | id=... | zone=... | baler=... | REJECTED`
  - 정상 이벤트: 녹색 배경
  - REJECTED 이벤트: 빨간 배경

## 운영 활성화

### 1. 기본 활성화 (전체 이벤트 저장)

`config/base.yaml`에서:
```yaml
event_image_saver:
  enabled: true
```

### 2. 프로파일별 활성화 (권장)

특정 라인에서만 이미지 저장하고 싶을 때:

`config/profiles/SSBR_workA.yaml`:
```yaml
event_image_saver:
  enabled: true
  enabled_event_prefixes:
    - "weigher_in"
    - "weigher_out"
    - "removed"
```

### 3. 재시작

```bash
./run.sh
```

로그에서 다음 라인을 확인:
```
[EventImageSaver] EventImageSaver started | save_dir=results/event_images | ...
```

## 테스트

### 단위/통합 테스트 실행

```bash
cd 프로젝트루트
python3 -m pytest tests/test_event_image_saver.py -v
```

25개 테스트 모두 통과 확인. 테스트 카테고리:

1. **FrameStore** (9개)
   - 초기 상태, update/snapshot, 프레임 유지, remove
   - 깊은 복사 보장
   - 잘못된 track_id 무시
   - get_bbox / size
   - 다중 스레드 stress

2. **ImageEventCapture** (6개)
   - on_created/on_updated/on_removed delegation
   - on_updated의 "inner 호출 전 캐싱" 순서 보장
   - on_removed의 "inner 호출 후 정리" 순서 보장
   - None 주입 방어

3. **EventImageSaver** (9개)
   - disabled 시 no-op
   - 프레임 없을 때 skip
   - 정상 저장
   - 이벤트 타입별 하위 폴더
   - Prefix 필터
   - REJECTED 마커
   - 비정상 이벤트 방어
   - 큐 오버플로 graceful drop
   - 쓰기 불가 디렉토리 자동 disable

4. **Integration** (1개)
   - `created → updated → event → removed` 전체 시나리오

### 테스트 환경

`tests/conftest.py`가 macOS/Windows 등 GStreamer(`gi`)가 없는 개발 환경에서도
테스트가 실행되도록 외부 의존성을 stub 처리합니다. 운영 환경(서버)에서는
stub이 활성화되지 않고 실제 패키지를 사용합니다.

## 성능 영향

- **Enabled=false 시**: 완전 no-op. 성능 영향 zero.
- **Enabled=true 시**:
  - 이벤트 콜백: `put_nowait` 비용만 (~μs 단위)
  - 프레임 캐싱: `update_frame` + dict 수정 (~μs 단위)
  - 실제 이미지 저장: 별도 워커 스레드 → 메인 파이프라인 무영향
- **디스크 I/O 고려**:
  - 초당 수십~수백 이벤트 발생 가능. `queue_size`를 적절히 설정 (기본 500)
  - `jpeg_quality` 조절로 파일 크기 조절 (기본 90)
  - 주기적으로 `results/event_images/` 정리 필요 (자동 rotation 미구현)

## 알려진 제한

1. **"created" 이벤트의 프레임**
   `on_created`는 handler에 frame을 전달하지 않음. 이 이벤트 시점의 프레임은
   **직전 `on_updated`의 프레임**이 사용됨 (수 ms 전 상태). 실제 프레임과
   사실상 동일하나, 극단적으로 빠른 이동이 있으면 약간의 차이 가능.

2. **delayed_call 이벤트**
   `weigher_in`/`weigher_out`은 `weigher_delay`만큼 지연 발행됨 (예: 0.5초).
   이 시점의 프레임은 **현재(발행 시점) 프레임**이며, 이벤트 발생 원인 프레임과 다름.
   → 계량기 동작 시점의 프레임을 보는 것이 실무적으로 더 유용할 수 있음.

3. **디스크 공간 관리**
   자동 rotation/삭제 기능 없음. cron/logrotate 등 외부 도구 필요.
   향후 `max_days` / `max_size` 옵션 추가 가능.

## 롤백 방법

기능을 완전히 제거하려면:

1. `config/base.yaml`의 `event_image_saver.enabled: false` 유지
2. (필요 시) `src/rubber_tracker/app/run.py`에서 `(신규)` 라인 5줄 삭제
3. `src/rubber_tracker/event_image_saver/` 디렉토리 삭제

기존 코드는 전혀 영향받지 않으므로 롤백 시 사이드 이펙트 없음.
