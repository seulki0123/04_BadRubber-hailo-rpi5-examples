from datetime import datetime


class FallbackService:
    """
    외부 ID 매칭 실패 시 트랙에 부여하는 자체 생성 ID(fallback ID)를 만든다.

    ID 포맷: {device:02d}{error_type:1d}{counter:03d}_{HHMMSS}
      - device    (2자리): config 의 device_fallback_id. 어느 장비에서 생성했는지 식별.
      - error_type(1자리): 왜 fallback 인지 (1=zone 밖, 2=외부 ID 미매칭).
      - counter   (3자리): 같은 초 내에서만 증가하는 순번 (000~999).
                           초가 바뀌면 0 으로 리셋.
      - HHMMSS   (6자리): 생성 시각 시분초.

    예: device_id=10, error_type=2, 해당 초 내 5번째, 15:30:45
        → "102005_153045"

    이전 포맷과 비교:
      이전: {device:04d}{error:02d}_{serial:06d}  예) "001002_000003"
        → 문제: serial 이 메모리 카운터라 재시작 시 리셋 → 중복 발생.
      현재: {device:02d}{error:1d}{counter:03d}_{HHMMSS}
        → counter 는 초 단위 리셋이라 999 넘을 수 없고,
          HHMMSS 가 재시작마다 달라지므로 중복 불가.

    하위 호환:
      - fallback ID 는 시스템 전체에서 opaque string 으로 취급되며
        내부 구조를 파싱하는 코드가 없으므로 포맷 변경이 로직에 영향 없음.
      - ID 길이는 이전(13자)과 동일(13자).

    error_type 정의:
      1: create_fallback_baler_not_input_zone (입력 zone 밖에서 생성 — trash)
      2: create_fallback_baler_no_externals   (외부 ID 매칭 실패)
    """

    def __init__(self, device_id, create_fallback_baler_no_externals, create_fallback_baler_not_input_zone):
        self.device_id = device_id
        self._fallback_balers = {
            1: create_fallback_baler_not_input_zone,
            2: create_fallback_baler_no_externals,
        }
        # 초 단위 리셋 카운터: 같은 초 안에서만 증가하고, 초가 바뀌면 0으로 리셋.
        # error_type 별로 독립 관리.
        self._last_second = {}
        self._second_counter = {}

    def get_fallback_id(self, error_type: int) -> tuple[int, str]:
        if error_type not in self._fallback_balers:
            self._fallback_balers[error_type] = 99

        now = datetime.now()
        current_second = now.strftime("%H%M%S")

        # 초가 바뀌면 카운터 리셋
        if self._last_second.get(error_type) != current_second:
            self._second_counter[error_type] = 0
            self._last_second[error_type] = current_second

        counter = self._second_counter[error_type]
        self._second_counter[error_type] += 1

        # 카운터가 999 를 초과하는 경우 (1초 내 1000개 이상 — 현실적으로 불가능하지만 방어)
        # 999 에서 멈추고 경고. HHMMSS 와의 조합으로 유일성은 여전히 높음.
        if counter > 999:
            counter = 999

        # 포맷: {device:02d}{error_type:1d}{counter:03d}_{HHMMSS}
        left = f"{int(self.device_id):02d}{int(error_type):1d}{counter:03d}"
        right = current_second
        return self._fallback_balers[error_type], f"{left}_{right}"
