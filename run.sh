#!/bin/bash
echo "=== Start run.sh ==="
set -e
source setup_env.sh

handle_interrupt() {
    echo "사용자 강제 종료 감지..."
    clean_processes
    exit 0
}
trap handle_interrupt SIGINT

export HAILO_MONITOR=1
export PYTHONPATH="$PYTHONPATH:$(pwd)/src"

ID=$(./yq '.id' config/setting.yaml)
HEF_PATH=$(./yq '.detect.weight' config/profiles/"$ID".yaml)
echo "Profile ID: $ID"
echo "HEF_PATH: $HEF_PATH"
python3 src/main.py --hef-path $HEF_PATH --input user_appsrc

# sudo reboot