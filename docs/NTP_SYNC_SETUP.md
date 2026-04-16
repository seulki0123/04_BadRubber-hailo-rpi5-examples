# NTP 시간 동기화 설정 가이드

Raspberry Pi 기반 장비(Tracking Device, ImageDB 등)의 시스템 시간을
지정된 NTP 서버(NBR PC 등)와 자동 동기화하는 설정 가이드.

## 왜 필요한가

운영 코드의 `sync.time` 기능은 외부 이벤트(`id_added_*`)와 내부 이벤트(`created_*`)를
타임스탬프 차이 `tolerance` 초 이내일 때 같은 객체로 매칭한다.

```yaml
# config/profiles/SSBR_branch+join.yaml
sync:
  time:
    tolerance: 2   # 초
```

장비 간 시계 drift 가 tolerance 를 넘으면 매칭이 실패하고 fallback 트랙이 생성된다.
NTP 동기화는 이 매칭의 전제 조건이다.

## 빠른 시작

```bash
# 장비에 SSH 접속 후:
sudo bash scripts/ntp/setup_ntp.sh                    # 테스트 (공인 NTP)
sudo bash scripts/ntp/setup_ntp.sh <NTP_SERVER_IP>    # 운영 (NBR PC IP)
```

스크립트가 자동으로 처리하는 것:
1. 디스크 공간 확인 + apt 캐시 정리 (500MB 미만 시)
2. systemd-timesyncd 비활성화 (chrony 충돌 방지)
3. chrony 설치
4. 설정 파일 백업 + NTP 서버 지정 (makestep/fallback/rtcsync 포함)
5. systemd override 적용 (프로세스 크래시 시 자동 재시작)
6. chrony 재시작 + 동기화 대기 + 결과 리포트

## 설정 파일

### chrony.conf (`/etc/chrony/chrony.conf`)

템플릿: `scripts/ntp/chrony.conf.template`

```
server <NBR_PC_IP> iburst            # 주 NTP 서버
server time.google.com iburst        # fallback 1
server time.cloudflare.com iburst    # fallback 2
makestep 1 3                         # 1초 이상 차이면 처음 3회 강제 점프 보정
rtcsync                              # 하드웨어 클럭 동기화
driftfile /var/lib/chrony/chrony.drift
logdir /var/log/chrony
```

### systemd override (`/etc/systemd/system/chrony.service.d/restart.conf`)

```ini
[Service]
Restart=always
RestartSec=5
```

chrony 프로세스가 어떤 이유로든 종료되면 5초 후 자동 재시작.

## 엣지 케이스 대응

| 시나리오 | 대응 | 검증 결과 |
| --- | --- | --- |
| 주 NTP 서버 접속 불가 | fallback 서버 (Google, Cloudflare) 자동 전환 | PASS — iptables 차단 테스트 |
| 시간 대규모 점프 (1시간 이상) | `makestep 1 3` 강제 보정 | PASS — date -s '+1 hour' 후 15초 내 복구 |
| chrony 프로세스 강제 종료 | `Restart=always` systemd 자동 재시작 | PASS — killall 후 8초 내 active 복구 |
| systemd-timesyncd 충돌 | chrony 설치 시 자동 제거됨 | PASS — 재활성화 시도 시 "not found" |
| 디스크 공간 부족 | setup 스크립트가 apt-get clean 선행 | PASS — 100%→96% 복구 후 설치 성공 |

## 검증 결과 (2026-04-16, Tracking Device)

### 기본 동기화

| 항목 | 값 |
| --- | --- |
| NTP 소스 | pool.ntp.org (한국 서버 자동 선택) |
| System time offset | 12~197 마이크로초 |
| sync.tolerance=2초 대비 여유 | 10,000배 이상 |
| Leap status | Normal |

### 반복 측정 (10초 간격 5회)

| 회차 | System offset |
| --- | --- |
| 1 | 74 us |
| 2 | 70 us |
| 3 | 66 us |
| 4 | 62 us |
| 5 | 58 us |

꾸준히 수렴 (chrony 능동 보정 확인).

### 재부팅 테스트

- chrony 자동 기동 확인 (systemctl enabled)
- 재부팅 직후 offset 0.25 us
- NTP 소스 즉시 동기화 (`^*` 마커)

### 장시간 안정성 (30초 간격 10회 = 5분)

197 us 에서 시작해 72 us 까지 꾸준히 수렴. drift 재발 없음.

## 운영 전환

테스트 완료 후 NBR PC IP 확보 시:

```bash
sudo sed -i 's/^server pool.ntp.org/server <NTP_SERVER_IP>/' /etc/chrony/chrony.conf
sudo systemctl restart chrony
chronyc sources    # ^* 마커 확인
chronyc tracking   # offset + Leap status 확인
```

또는 setup 스크립트 재실행:

```bash
sudo bash scripts/ntp/setup_ntp.sh <NTP_SERVER_IP>
```

## 확인 명령어

```bash
# 현재 동기화 상태
chronyc tracking

# NTP 소스 목록
chronyc sources -v

# chrony 서비스 상태
systemctl status chrony

# 로그
journalctl -u chrony --since "1 hour ago"
```

## 롤백

```bash
# 설정 원복 (setup 시 자동 백업된 파일 사용)
sudo cp /etc/chrony/chrony.conf.bak.<날짜> /etc/chrony/chrony.conf
sudo systemctl restart chrony

# 또는 chrony 완전 제거 + timesyncd 복구
sudo systemctl disable --now chrony
sudo apt remove -y chrony
sudo apt install -y systemd-timesyncd
sudo systemctl enable --now systemd-timesyncd
```
