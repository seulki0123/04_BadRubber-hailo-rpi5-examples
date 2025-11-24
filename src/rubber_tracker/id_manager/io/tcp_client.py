import json
import socket

import yaml

from rubber_tracker.utils import ModuleLogger

class TCPClient(ModuleLogger):
    def __init__(self, config_path="config.yaml"):
        super().__init__(__class__.__name__)
        with open(config_path, "r") as f:
            config = yaml.safe_load(f)

        self.host = config["idmanager"]["client"]["host"]
        self.port = config["idmanager"]["client"]["port"]
        self.socket = None
        self.buffer = ""

    def connect(self):
        self.socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        self.socket.connect((self.host, self.port))
        self.log_info(f"Connected to TCP server: {self.host}:{self.port}")

    def task(self):
        try:
            chunk = self.socket.recv(1024)
        except Exception as e:
            self.log_error(f"Socket error: {e}")
            return

        if not chunk:
            self.log_info("Server closed the connection.")
            return

        self.buffer += chunk.decode("utf-8", errors="ignore")

        while "\n" in self.buffer:
            line, self.buffer = self.buffer.split("\n", 1)
            line = line.strip()
            if not line:
                continue

            # self.log_info(f"Received data from TCP server: {line}")
            return self._process_data(line)

    def _process_data(self, line):
        try:
            data = json.loads(line)
            # self.log_info(f"Processed data: {data}")
            return data
        except json.JSONDecodeError:
            self.log_error(f"Invalid JSON: {line}")
            return None
        except Exception as e:
            self.log_error(f"Error processing data: {e}")
            return None