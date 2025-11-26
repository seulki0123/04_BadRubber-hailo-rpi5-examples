import time
import json
import socket
from datetime import datetime

from rubber_tracker.utils import ModuleLogger
from rubber_tracker.utils import CustomThread

class TCPClient(ModuleLogger):
    def __init__(self, host, port, name):
        super().__init__(self.__class__.__name__ + "_" + name)
        self.name = name
        self.host = host
        self.port = port

        self.socket = None
        self.recv_buffer = ""
        self.send_buffer = bytearray()   # pending outgoing data

        self.thread = None
        self.callbacks = []

    def add_callback(self, callback):
        self.callbacks.append(callback)

    def start(self):
        self.thread = CustomThread(
            name=self.__class__.__name__ + "_" + self.name,
            task=self._task,
            interval=0.01
        )
        self.thread.start()

    def send(self, data):
        """Queue data into send_buffer (non-blocking send)."""
        if isinstance(data, dict):
            msg = json.dumps(data)
        else:
            msg = str(data)

        packet = (msg + "\n").encode("utf-8")

        # Append to outgoing buffer
        self.send_buffer.extend(packet)

        return True

    def _task(self):
        if self.socket is None:
            self._connect()

        if self.socket:
            self._flush_send_buffer()
            raw = self._receive()
            msgs = self._parse(raw)

            if msgs and self.callbacks:
                for m in msgs:
                    for c in self.callbacks:
                        try:
                            c(m)
                        except Exception as e:
                            self.log_error(f"Callback error [{c.__name__}]: {e}")

    def _connect(self):
        try:
            self.socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            self.socket.connect((self.host, self.port))
            self.socket.setblocking(False)    # ★ non-blocking mode

            self.log_info(f"{self.host}:{self.port} connected")

        except Exception as e:
            self.log_error(f"{self.host}:{self.port} connect failed: {e}. Retry in 2 sec...")
            self.socket = None
            time.sleep(2)

    def _flush_send_buffer(self):
        """Non-blocking send using partial send logic."""
        if not self.send_buffer or self.socket is None:
            return

        try:
            sent = self.socket.send(self.send_buffer)
            if sent > 0:
                del self.send_buffer[:sent]
                self.log_info(f"{self.host}:{self.port} sent {sent} bytes")

        except BlockingIOError:
            # Socket not ready
            pass

        except Exception as e:
            self.log_error(f"{self.host}:{self.port} send error: {e}")
            self._close()

    def _receive(self):
        """Non-blocking recv."""
        if self.socket is None:
            return None

        try:
            chunk = self.socket.recv(1024)
            if not chunk:
                self.log_error(f"{self.host}:{self.port} server closed connection")
                self._close()
                return None

            return chunk.decode("utf-8", errors="ignore")

        except BlockingIOError:
            # No data available
            return None

        except Exception as e:
            self.log_error(f"{self.host}:{self.port} receive error: {e}")
            self._close()
            return None

    def _parse(self, raw):
        if raw is None:
            return None

        self.recv_buffer += raw
        msgs = []

        while "\n" in self.recv_buffer:
            line, self.recv_buffer = self.recv_buffer.split("\n", 1)
            line = line.strip()
            if not line:
                continue
            try:
                msg = json.loads(line)
                msgs.append(msg)
                self.log_info(f"{self.host}:{self.port} recv: {msg}")
            except Exception as e:
                self.log_error(f"Invalid message: {line} ({e})")

        return msgs

    def _close(self):
        if self.socket:
            try:
                self.socket.close()
                self.log_info(f"{self.host}:{self.port} connection closed")
            except Exception as e:
                self.log_error(f"{self.host}:{self.port} close error: {e}")

        self.socket = None
        self.send_buffer.clear()
