import re
import time
import subprocess
from collections import deque

import yaml

from rubber_tracker.utils import MonitorLogger, safe_call, load_config

class VoltageMonitor(MonitorLogger):

    def __init__(self):
        super().__init__(self.__class__.__name__)
        cfg = load_config()
        self.logging_interval = cfg["voltage_monitor"]["logging_interval"]
        self.max_queue_size = cfg["voltage_monitor"]["max_queue_size"]
        
        self._data_clear()
        self._get_vcgencmd_version_and_logging()

    def task(self):
        if time.time() - self.last_log_time >= self.logging_interval:
            self._logging()
            self._data_clear()

        core_voltage = self._get_core_voltage()
        sdram_voltage = self._get_sdram_voltage()
        clock_speed = self._get_clock_speed()
        throttled_status = self._get_throttled_status()

        if core_voltage is not None:
            self.core_voltages.append(core_voltage)

        if sdram_voltage is not None:
            self.sdram_c_voltages.append(sdram_voltage[0])
            self.sdram_i_voltages.append(sdram_voltage[1])
            self.sdram_p_voltages.append(sdram_voltage[2])

        if clock_speed is not None:
            self.arm_clock_speeds.append(clock_speed[0])
            self.core_clock_speeds.append(clock_speed[1])

        if throttled_status is not None:
            self.under_voltage += throttled_status[0]
            self.freq_capped += throttled_status[1]
            self.throttling += throttled_status[2]

    def _data_clear(self):
        self.core_voltages = deque(maxlen=self.max_queue_size)
        self.sdram_c_voltages = deque(maxlen=self.max_queue_size)
        self.sdram_i_voltages = deque(maxlen=self.max_queue_size)
        self.sdram_p_voltages = deque(maxlen=self.max_queue_size)
        self.arm_clock_speeds = deque(maxlen=self.max_queue_size)
        self.core_clock_speeds = deque(maxlen=self.max_queue_size)
        self.under_voltage = 0
        self.freq_capped = 0
        self.throttling = 0

        self.last_log_time = time.time()

    def _logging(self):
        if len(self.core_voltages) > 0:
            avg_cv = sum(self.core_voltages) / len(self.core_voltages)
            max_cv = max(self.core_voltages)
            min_cv = min(self.core_voltages)
            self.log_info(f"Core Voltage(V) Average, Max, Min: {avg_cv:.4f}, {max_cv:.4f}, {min_cv:.4f}")
        else:
            self.log_info("No Core Voltage Data")

        if len(self.sdram_c_voltages) > 0:
            avg_rv_c = sum(self.sdram_c_voltages) / len(self.sdram_c_voltages)
            max_rv_c = max(self.sdram_c_voltages)
            min_rv_c = min(self.sdram_c_voltages)
            self.log_info(f"SDRAM C Voltage(V) Average, Max, Min: {avg_rv_c:.4f}, {max_rv_c:.4f}, {min_rv_c:.4f}")
        else:
            self.log_info("No SDRAM C Voltage Data")

        if len(self.sdram_i_voltages) > 0:
            avg_rv_i = sum(self.sdram_i_voltages) / len(self.sdram_i_voltages)
            max_rv_i = max(self.sdram_i_voltages)
            min_rv_i = min(self.sdram_i_voltages)
            self.log_info(f"SDRAM I Voltage(V) Average, Max, Min: {avg_rv_i:.4f}, {max_rv_i:.4f}, {min_rv_i:.4f}")
        else:
            self.log_info("No SDRAM I Voltage Data")

        if len(self.sdram_p_voltages) > 0:
            avg_rv_p = sum(self.sdram_p_voltages) / len(self.sdram_p_voltages)
            max_rv_p = max(self.sdram_p_voltages)
            min_rv_p = min(self.sdram_p_voltages)
            self.log_info(f"SDRAM P Voltage(V) Average, Max, Min: {avg_rv_p:.4f}, {max_rv_p:.4f}, {min_rv_p:.4f}")
        else:
            self.log_info("No SDRAM P Voltage Data")

        if len(self.arm_clock_speeds) > 0:
            avg_cs_a = sum(self.arm_clock_speeds) / len(self.arm_clock_speeds)
            max_cs_a = max(self.arm_clock_speeds)
            min_cs_a = min(self.arm_clock_speeds)
            self.log_info(f"ARM Clock Speed(Hz) Average, Max, Min: {avg_cs_a:.0f}, {max_cs_a:.0f}, {min_cs_a:.0f}")
        else:
            self.log_info("No ARM Clock Speed Data")

        if len(self.core_clock_speeds) > 0:
            avg_cs_c = sum(self.core_clock_speeds) / len(self.core_clock_speeds)
            max_cs_c = max(self.core_clock_speeds)
            min_cs_c = min(self.core_clock_speeds)
            self.log_info(f"Core Clock Speed(Hz) Average, Max, Min: {avg_cs_c:.0f}, {max_cs_c:.0f}, {min_cs_c:.0f}")
        else:
            self.log_info("No Core Clock Speed Data")

        if self.under_voltage > 0:
            self.log_warning(f"Under Voltage Event Count: {self.under_voltage}")

        if self.freq_capped > 0:
            self.log_warning(f"Freq Capped Event Count: {self.freq_capped}")

        if self.throttling > 0:
            self.log_warning(f"Throttling Event Count: {self.throttling}")

    @safe_call
    def _get_core_voltage(self):
        output = subprocess.check_output(['vcgencmd', 'measure_volts', 'core']).decode().strip()
        core_volts = float(output.replace('volt=', '').replace('V', ''))
        return core_volts

    @safe_call
    def _get_sdram_voltage(self):
        output_c = subprocess.check_output(['vcgencmd', 'measure_volts', 'sdram_c']).decode().strip()
        sdram_c_volts = float(output_c.replace('volt=', '').replace('V', ''))

        output_i = subprocess.check_output(['vcgencmd', 'measure_volts', 'sdram_i']).decode().strip()
        sdram_i_volts = float(output_i.replace('volt=', '').replace('V', ''))

        output_p = subprocess.check_output(['vcgencmd', 'measure_volts', 'sdram_p']).decode().strip()
        sdram_p_volts = float(output_p.replace('volt=', '').replace('V', ''))

        return sdram_c_volts, sdram_i_volts, sdram_p_volts
    
    @safe_call
    def _get_clock_speed(self):
        output_arm = subprocess.check_output(['vcgencmd', 'measure_clock', 'arm']).decode().strip()
        arm_clock = int(re.search(r'=(\d+)', output_arm).group(1))

        output_core = subprocess.check_output(['vcgencmd', 'measure_clock', 'core']).decode().strip()
        core_clock = int(re.search(r'=(\d+)', output_core).group(1))

        return arm_clock, core_clock

    @safe_call
    def _get_throttled_status(self):
        output = subprocess.check_output(['vcgencmd', 'get_throttled']).decode().strip()
        throttled_hex = output.split('=')[1]
        throttled_int = int(throttled_hex, 16)

        return (
            bool(throttled_int & 0x1), # under_voltage
            bool(throttled_int & 0x2), # freq_capped
            bool(throttled_int & 0x4), # throttling
            # bool(throttled_int & 0x10000), # past_under_voltage
            # bool(throttled_int & 0x20000), # past_freq_capped
            # bool(throttled_int & 0x40000), # past_throttling
        )

    @safe_call
    def _get_vcgencmd_version_and_logging(self):
        output = subprocess.check_output(['vcgencmd', 'version']).decode().strip()
        info = output.replace('\n', ', ')
        self.log_info(f"VCGENCMD Version: {info}")