import time
import json
import socket
from datetime import datetime

from rubber_tracker.utils import ModuleLogger
from rubber_tracker.utils import CustomThread

class TCPClient(ModuleLogger):
    def __init__(self, host, port, name, callback):
        super().__init__(self.__class__.__name__+ "_" + name)
        self.name = name
        self.host = host
        self.port = port
        self.socket = None
        self.buffer = ""
        self.callback = callback
        self.thread = None

    def start(self):
        self.thread = CustomThread(name=self.__class__.__name__ + "_" + self.name, task=self._task, interval=0.01)
        self.thread.start()

    def _task(self):
        raw = self._receive()
        msgs = self._parse(raw)
        if msgs and self.callback is not None:
            for m in msgs:
                self.callback(m)

    def _connect(self):
        try:
            self.socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            self.socket.connect((self.host, self.port))
            self.log_info(f"{self.host}:{self.port} server connected")
        except Exception as e:
            self.log_error(f"{self.host}:{self.port} server connection failed: {e}. Retrying in 2 seconds...")
            self.socket = None
            time.sleep(2)
    
    def _receive(self):
        if self.socket is None:
            self._connect()
            if self.socket is None:
                return None
        
        try:
            chunk = self.socket.recv(1024)
            if not chunk:
                self.log_error(f"{self.host}:{self.port} server closed the connection.")
                self._close()
                return None
            return chunk.decode("utf-8", errors="ignore")
            
        except Exception as e:
            self.log_error(f"{self.host}:{self.port} server receive error: {e}")
            self._close()
            return None

    def _parse(self, raw):
        if raw is None:
            return None
        
        self.buffer += raw
        messages = []
        while "\n" in self.buffer:
            line, self.buffer = self.buffer.split("\n", 1)
            line = line.strip()
            if not line:
                continue

            try:
                msg = json.loads(line)
                messages.append(msg)
                self.log_info(f"{self.host}:{self.port} received data: {msg}")
            except json.JSONDecodeError:
                self.log_error(f"Invalid JSON: {line}")
                continue
            except Exception as e:
                self.log_error(f"Error parsing message: {e}")
                continue

        return messages
    
    def _close(self):
        if self.socket is not None:
            try:
                self.socket.close()
                self.log_info(f"{self.host}:{self.port} server connection closed")
            except Exception as e:
                self.log_error(f"{self.host}:{self.port} server connection close error: {e}")
            self.socket = None

    def send(self, data):
        if self.socket is None:
            self._connect()
            if self.socket is None:
                return False

        try:
            if isinstance(data, dict):
                msg = json.dumps(data)
            else:
                msg = str(data)

            self.socket.sendall((msg + "\n").encode("utf-8"))
            self.log_info(f"{self.host}:{self.port} sent data: {msg}")
            return True

        except Exception as e:
            self.log_error(f"{self.host}:{self.port} send error: {e}")
            self._close()
            return False