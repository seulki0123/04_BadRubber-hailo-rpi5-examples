import re
import os
import time
import subprocess
from typing import Optional, Tuple

import yaml
import psutil

from rubber_tracker.utils import ModuleLogger, safe_call, load_config

class ResourceMonitor(ModuleLogger):

    def __init__(self, npu_error_callback=None, disk_cleanup_callback=None):
        super().__init__(self.__class__.__name__)
        cfg = load_config()
        self.cpu_interval = cfg["resource_monitor"]["cpu_interval"]
        self.cpu_threshold = cfg["resource_monitor"]["cpu_threshold"]
        self.ram_threshold = cfg["resource_monitor"]["ram_threshold"]
        self.disk_threshold = cfg["resource_monitor"]["disk_threshold"]

        self.npu_error_callback = npu_error_callback
        self.disk_cleanup_callback = disk_cleanup_callback
        if self.disk_cleanup_callback is not None:
            self.log_info("Disk cleanup callback is set")
        else:
            self.log_warning("Disk cleanup callback is not set")

    def task(self):
        cpu_info = self._get_cpu_info()
        ram_info = self._get_ram_info()
        disk_info = self._get_disk_info()
        # npu_info = self._get_npu_usage()
        npu_info = None

        # cpu
        if cpu_info is not None:
            cpu_temp, cpu_used = cpu_info
            self.log_info(f"CPU Temperature: {cpu_temp:.1f}°C")
            self.log_info(f"CPU Usage: {cpu_used:.1f}%")

            if cpu_used > self.cpu_threshold:
                self.log_warning(f"HIGH CPU USAGE: {cpu_used:.1f}%")

        # ram
        if ram_info is not None:
            ram_used, ram_total, ram_percent = ram_info
            self.log_info(f"Memory: {ram_used:.1f}MB / {ram_total:.1f}MB ({ram_percent:.1f}%)")

            if ram_percent > self.ram_threshold:
                self.log_warning(f"HIGH MEMORY USAGE: {ram_percent:.1f}%")

        # disk
        if disk_info is not None:
            disk_used, disk_total, disk_percent = disk_info
            self.log_info(f"Disk: {disk_used:.1f}GB / {disk_total:.1f}GB ({disk_percent:.1f}%)")

            if disk_percent > self.disk_threshold:
                self.log_warning(f"HIGH DISK USAGE: {disk_percent:.1f}%")
                if self.disk_cleanup_callback is not None:
                    self.disk_cleanup_callback()

        # npu
        if npu_info is not None:
            npu_used, npu_fps, npu_device_ids = npu_info
            self.log_info(f"NPU Utilization: {npu_used:.1f}%")
            self.log_info(f"NPU FPS: {npu_fps:.1f}")
            self.log_info(f"NPU Device IDs: {npu_device_ids}")
            
            # TODO: ERROR CALLBACK
            if npu_used == 100 and npu_fps == 0:
                self.log_warning("NPU Utilization is 100% and FPS is 0")
            elif npu_used == 0 and npu_fps == 0:
                self.log_warning("NPU Utilization is 0% and FPS is 0")

    @safe_call
    def _get_cpu_info(self) -> Optional[Tuple[float, float]]:
        # temperature
        temp = None
        if os.path.exists('/sys/class/thermal/thermal_zone0/temp'):
            with open('/sys/class/thermal/thermal_zone0/temp', 'r') as f:
                temp = float(f.read().strip()) / 1000
        
        if temp is None:
            result = subprocess.check_output(['vcgencmd', 'measure_temp']).decode()
            temp = float(result.replace('temp=', '').replace('\'C', ''))

        # usage
        cpu_percent = psutil.cpu_percent(interval=self.cpu_interval, percpu=True)
        cpu_percent_avg = sum(cpu_percent) / len(cpu_percent)
            
        return temp, cpu_percent_avg

    @safe_call
    def _get_ram_info(self) -> Optional[Tuple[float, float, float]]:
        memory = psutil.virtual_memory()
        memory_used_mb = memory.used / (1024 * 1024)
        memory_total_mb = memory.total / (1024 * 1024)
        memory_percent = memory.percent
        return memory_used_mb, memory_total_mb, memory_percent
    
    @safe_call
    def _get_disk_info(self) -> Optional[Tuple[float, float, float]]:
        return get_disk_info()

    @safe_call
    def _get_npu_usage(self) -> Optional[Tuple[float, float, list[str]]]:
        cmd = f"script -q -c 'timeout 0.1 hailortcli monitor' /dev/null"
        result = subprocess.run(cmd, shell=True, capture_output=True, text=True)

        # utilization, fps
        pattern = r"yolov8n\s+([\d\.]+)\s+([\d\.]+)"
        match = re.search(pattern, result.stdout)

        if match is None:
            ansi_escape = re.compile(r'\x1B(?:[@-Z\\-_]|\[[0-?]*[ -/]*[@-~])')
            clean_stdout = ansi_escape.sub('', result.stdout)
            raise Exception("NPU Usage is not found\n" + clean_stdout)

        utilization = float(match.group(1))
        fps = float(match.group(2))

        # 디바이스 개수
        device_ids = ['임시입니다.']
        if device_ids:
            device_ids = device_ids[0]
        else:
            device_ids = None

        return utilization, fps, device_ids

def get_disk_info() -> Optional[Tuple[float, float, float]]:
    disk = psutil.disk_usage('/')
    disk_used_gb = disk.used / (1024 * 1024 * 1024)
    disk_total_gb = disk.total / (1024 * 1024 * 1024)
    disk_percent = disk.percent
    return disk_used_gb, disk_total_gb, disk_percent
