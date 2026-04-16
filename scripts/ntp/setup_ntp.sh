#!/bin/bash
# ============================================================
# NTP 시간 동기화 설정 스크립트
#
# Raspberry Pi 기반 장비(Tracking Device, ImageDB 등)에서
# 직접 실행하는 스크립트. chrony 설치/설정/검증을 자동 수행.
#
# 사용법 (장비에 SSH 접속 후):
#   sudo bash scripts/ntp/setup_ntp.sh [NTP_SERVER_IP]
#
# 예:
#   sudo bash scripts/ntp/setup_ntp.sh                  # 기본값: pool.ntp.org (테스트)
#   sudo bash scripts/ntp/setup_ntp.sh <NTP_SERVER_IP>    # 운영: NBR PC IP
#
# 동작 순서:
#   1) 적용 전 시간 상태 기록
#   2) 디스크 공간 확보 (apt 캐시 정리)
#   3) systemd-timesyncd 비활성화 (chrony 충돌 방지)
#   4) chrony 설치
#   5) chrony.conf 백업 + 설정 적용 (makestep/fallback/rtcsync 포함)
#   6) systemd override 적용 (프로세스 크래시 시 자동 재시작)
#   7) chrony 재시작 + 동기화 대기
#   8) 적용 후 측정 + 결과 리포트
# ============================================================

set -euo pipefail

# ---- 설정 ----
NTP_SERVER="${1:-pool.ntp.org}"
BACKUP_SUFFIX="$(date '+%Y-%m-%d_%H%M%S')"
SYNC_WAIT=20
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

echo "============================================================"
echo "NTP 시간 동기화 설정"
echo "  NTP 서버 : $NTP_SERVER"
echo "  장비     : $(hostname)"
echo "  시각     : $(date '+%Y-%m-%d %H:%M:%S')"
echo "============================================================"

# ---- [1] 적용 전 측정 ----
echo ""
echo "[1/8] 적용 전 시간 상태"
echo "  현재 시각  : $(date '+%Y-%m-%d %H:%M:%S.%N')"
if command -v chronyc &> /dev/null; then
    echo "  [기존 chrony 발견]"
    chronyc tracking 2>/dev/null | grep -E 'System time|Last offset|Leap' || true
else
    echo "  chrony 미설치"
fi
if command -v timedatectl &> /dev/null; then
    echo "  NTP service: $(timedatectl | grep 'NTP service' | awk '{print $3}')"
    echo "  Synchronized: $(timedatectl | grep 'synchronized' | awk '{print $3}')"
fi

# ---- [2] 디스크 공간 확보 ----
echo ""
echo "[2/8] 디스크 공간 확보"
DISK_AVAIL=$(df / --output=avail -BM | tail -1 | tr -d ' M')
echo "  현재 여유: ${DISK_AVAIL}MB"
if [ "$DISK_AVAIL" -lt 500 ]; then
    echo "  여유 500MB 미만 — apt 캐시 정리 실행"
    apt-get clean -qq
    DISK_AFTER=$(df / --output=avail -BM | tail -1 | tr -d ' M')
    echo "  정리 후 여유: ${DISK_AFTER}MB"
else
    echo "  충분 — skip"
fi

# ---- [3] systemd-timesyncd 비활성화 ----
echo ""
echo "[3/8] systemd-timesyncd 비활성화"
if systemctl is-active systemd-timesyncd &> /dev/null; then
    systemctl disable --now systemd-timesyncd
    echo "  비활성화 완료"
else
    echo "  이미 비활성 또는 미설치 — skip"
fi

# ---- [4] chrony 설치 ----
echo ""
echo "[4/8] chrony 설치"
if dpkg -l chrony 2>/dev/null | grep -q '^ii'; then
    echo "  이미 설치됨 — skip"
else
    apt-get update -qq
    apt-get install -y -qq chrony
    if dpkg -l chrony 2>/dev/null | grep -q '^ii'; then
        echo "  설치 성공: $(dpkg -l chrony | grep '^ii' | awk '{print $3}')"
    else
        echo "  [오류] chrony 설치 실패. 디스크 공간 확인 필요."
        df -h /
        exit 1
    fi
fi

# ---- [5] chrony.conf 설정 ----
echo ""
echo "[5/8] chrony.conf 설정"
CONF="/etc/chrony/chrony.conf"
BACKUP="${CONF}.bak.${BACKUP_SUFFIX}"
cp "$CONF" "$BACKUP"
echo "  백업: $BACKUP"

# 템플릿이 있으면 사용, 없으면 직접 작성
TEMPLATE="${SCRIPT_DIR}/chrony.conf.template"
if [ -f "$TEMPLATE" ]; then
    sed "s/NTP_SERVER_PRIMARY/${NTP_SERVER}/" "$TEMPLATE" > "$CONF"
    echo "  템플릿 적용 (${TEMPLATE})"
else
    cat > "$CONF" << CONF_EOF
server ${NTP_SERVER} iburst
server time.google.com iburst
server time.cloudflare.com iburst
makestep 1 3
rtcsync
driftfile /var/lib/chrony/chrony.drift
logdir /var/log/chrony
CONF_EOF
    echo "  직접 작성 (템플릿 없음)"
fi
echo "  NTP 서버: $NTP_SERVER + fallback 2개"
echo "  makestep 1 3 (대규모 시간 점프 강제 보정)"

# ---- [6] systemd override (프로세스 크래시 자동 재시작) ----
echo ""
echo "[6/8] systemd override (Restart=always)"
mkdir -p /etc/systemd/system/chrony.service.d
cat > /etc/systemd/system/chrony.service.d/restart.conf << 'SYSD_EOF'
[Service]
Restart=always
RestartSec=5
SYSD_EOF
systemctl daemon-reload
echo "  적용 완료"

# ---- [7] chrony 재시작 + 동기화 대기 ----
echo ""
echo "[7/8] chrony 재시작 + ${SYNC_WAIT}초 대기"
systemctl restart chrony
systemctl enable chrony
echo "  상태: $(systemctl is-active chrony)"
echo "  부팅 자동시작: $(systemctl is-enabled chrony)"
echo "  동기화 대기 중..."
sleep "$SYNC_WAIT"

# ---- [8] 적용 후 측정 + 리포트 ----
echo ""
echo "[8/8] 적용 후 측정"
echo "  현재 시각: $(date '+%Y-%m-%d %H:%M:%S.%N')"
echo ""
echo "  --- chronyc sources ---"
chronyc sources
echo ""
echo "  --- chronyc tracking ---"
chronyc tracking | grep -E 'Reference|System time|Last offset|RMS offset|Root delay|Leap status'

echo ""
echo "============================================================"
echo "설정 완료"
echo "  NTP 서버      : $NTP_SERVER (+ fallback: Google, Cloudflare)"
echo "  makestep      : 1초 이상 차이 시 강제 보정 (처음 3회)"
echo "  프로세스 복구  : Restart=always (5초 내 자동 재시작)"
echo "  설정 백업      : $BACKUP"
echo ""

# 동기화 상태 판정
LEAP=$(chronyc tracking 2>/dev/null | grep 'Leap status' | awk -F: '{print $2}' | xargs)
if [ "$LEAP" = "Normal" ]; then
    echo "  결과: 정상 동기화 완료"
else
    echo "  결과: [주의] Leap status = $LEAP — 동기화 미완료 상태."
    echo "  수 분 후 다시 확인: chronyc tracking"
fi

echo "============================================================"
echo ""
echo "운영 전환 시:"
echo "  sudo sed -i 's/^server .* iburst$/server <NBR_PC_IP> iburst/' /etc/chrony/chrony.conf"
echo "  sudo systemctl restart chrony"
echo "  chronyc sources"
