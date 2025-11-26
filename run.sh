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

HEF_PATH=$(python3 - << 'EOF'
from rubber_tracker.utils import load_config
print(load_config()["detect"]["weight"])
EOF
)
python3 src/main.py --hef-path $HEF_PATH --input user_appsrc

# sudo reboot