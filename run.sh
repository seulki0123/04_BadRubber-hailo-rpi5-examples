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

HEF_PATH=$(python3 -c "import yaml; print(yaml.safe_load(open('config.yaml'))['detect']['weight'])")
python3 src/main.py --hef-path $HEF_PATH --input user_appsrc

# sudo reboot