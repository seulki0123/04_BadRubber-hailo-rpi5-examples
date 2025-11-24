import json
import time
import socket

import yaml

from rubber_tracker.utils import ModuleLogger

class IDFetcher(ModuleLogger):
    def __init__(self, event_callback, config_path="config.yaml"):
        super().__init__(__class__.__name__)
        with open(config_path, "r") as f:
            config = yaml.safe_load(f)

        self.host = config["idmanager"]["client"]["host"]
        self.port = config["idmanager"]["client"]["port"]
        self.socket = None
        self.buffer = ""
        self.event_callback = event_callback
        
    def _connect(self):
        try:
            self.socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            self.socket.connect((self.host, self.port))
            self.log_info(f"Connected to ServerA {self.host}:{self.port}")
        except Exception as e:
            self.log_error(f"Connection failed: {e}. Retrying in 2 seconds...")
            self.socket = None
            time.sleep(2)

    def recv_loop(self):
        if self.socket is None:
            self._connect()
            return

        try:
            chunk = self.socket.recv(1024)
        except Exception as e:
            self.log_error(f"Socket error: {e}")
            return

        if not chunk:
            self.log_info("Server closed the connection.")
            self.socket.close()
            self.socket = None
            return

        self.buffer += chunk.decode("utf-8", errors="ignore")

        while "\n" in self.buffer:
            line, self.buffer = self.buffer.split("\n", 1)
            line = line.strip()
            if not line:
                continue

            # self.log_info(f"Received data from TCP server: {line}")
            data = self._process_data(line)
            if data is not None:
                """
                {
                    "id": "ext_id",
                    "zone": "zone",
                    "time": "yyyy-MM-dd HH:mm:ss"
                }
                """
                ext_id = data["id"]
                zone = data["zone"]
                time = data["time"]
                self.event_callback(ext_id, zone, time)

    def send_event(self, ext_id, zone, rejected):
        if self.socket is None:
            self.log_error("Socket not connected. Cannot send event.")
            return

        message = json.dumps({
            "id": ext_id,
            "zone": zone,
            "rejected": rejected,
            "time": "yyyy-MM-dd HH:mm:ss"
        }) + "\n"

        try:
            self.socket.send(message.encode())
        except Exception as e:
            self.log_error(f"Failed to send event: {e}")

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