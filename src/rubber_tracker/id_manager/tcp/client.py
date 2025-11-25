import time
import json
import socket
from datetime import datetime

from rubber_tracker.utils import ModuleLogger

class TCPClient(ModuleLogger):
    def __init__(self, host, port, name):
        super().__init__(self.__class__.__name__+ "_" + name)
        self.host = host
        self.port = port
        self.socket = None
        self.buffer = ""

    def _connect(self):
        try:
            self.socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            self.socket.connect((self.host, self.port))
            self.log_info(f"{self.host}:{self.port} server connected")
        except Exception as e:
            self.log_error(f"{self.host}:{self.port} server connection failed: {e}. Retrying in 2 seconds...")
            self.socket = None
            time.sleep(2)

    def recv_loop(self):
        if self.socket is None:
            self._connect()
            return

        try:
            chunk = self.socket.recv(1024)
        except Exception as e:
            self.log_error(f"{self.host}:{self.port} server communication error: {e}")
            return

        if not chunk:
            self.log_info(f"{self.host}:{self.port} server closed the connection.")
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
                self.log_info(f"{self.host}:{self.port} received data: {data}")
                return data

    def send_event(self, ext_id, zone, rejected):
        if self.socket is None:
            self.log_error(f"{self.host}:{self.port} server not connected. Cannot send event.")
            return

        time = datetime.now().strftime("%Y-%m-%d %H:%M:%S.%f")[:-3]
        message = json.dumps({
            "id": ext_id,
            "zone": zone,
            "rejected": rejected,
            "time": time
        }) + "\n"

        try:
            self.socket.send(message.encode())
        except Exception as e:
            self.log_error(f"{self.host}:{self.port} failed to send event: {e}")

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