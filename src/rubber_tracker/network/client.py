import time
import json
import socket
import threading
from datetime import datetime

from rubber_tracker.utils import ProcessLogger
from rubber_tracker.utils import CustomThread

class TCPClient(ProcessLogger):
    def __init__(self, host, port, name, bind=None, send_buffer_config=None):
        super().__init__(self.__class__.__name__ + "_" + name)
        self.name = name
        self.host = host
        self.port = port
        self.bind = bind or None
        send_buffer_config = send_buffer_config or {}
        self.max_send_buffer_bytes = int(send_buffer_config.get("max_bytes", 1024 * 1024))
        self.drop_log_interval_seconds = float(
            send_buffer_config.get("drop_log_interval_seconds", 60)
        )

        self.socket = None
        self.recv_buffer = ""
        self.send_buffer = bytearray()   # pending outgoing data
        self._send_lock = threading.Lock()
        self._dropped_count = 0
        self._last_drop_log_time = time.monotonic()

        self.thread = None
        self.callbacks = []

    def add_callback(self, callback):
        self.callbacks.append(callback)

    def start(self):
        """멀티 프로파일에서 notifier 소켓을 공유할 때 중복 start 가 호출될 수 있다."""
        if self.thread is not None:
            inner = getattr(self.thread, "thread", None)
            if inner is not None and inner.is_alive():
                return

        self.thread = CustomThread(
            name=self.__class__.__name__ + "_" + self.name,
            task=self._task,
            interval=0.01
        )
        self.thread.start()

    def send(self, data):
        """Queue live data only while connected; offline data is discarded."""
        if isinstance(data, dict):
            msg = json.dumps(data)
        else:
            msg = str(data)

        packet = (msg + "\n").encode("utf-8")

        with self._send_lock:
            if self.socket is None:
                self._record_drop_locked("disconnected")
                return False

            if len(self.send_buffer) + len(packet) > self.max_send_buffer_bytes:
                self._record_drop_locked("send buffer full")
                return False

            self.send_buffer.extend(packet)
        self.log_info(f"{self.host}:{self.port} send buffer extend: {msg}")

        return True

    def _record_drop_locked(self, reason):
        """Count dropped events and periodically emit a summary."""
        self._dropped_count += 1
        now = time.monotonic()
        if now - self._last_drop_log_time >= self.drop_log_interval_seconds:
            self.log_warning(
                f"{self.host}:{self.port} {reason}: "
                f"dropped {self._dropped_count} events during the last interval"
            )
            self._dropped_count = 0
            self._last_drop_log_time = now

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
            if self.bind:
                self.socket.bind((self.bind, 0))
            self.socket.connect((self.host, self.port))
            self.socket.setblocking(False)    # ★ non-blocking mode

            bind_desc = f" (bind={self.bind})" if self.bind else ""
            self.log_info(f"{self.host}:{self.port} connected{bind_desc}")

        except Exception as e:
            self.log_error(f"{self.host}:{self.port} connect failed: {e}. Retry in 2 sec...")
            try:
                if self.socket is not None:
                    self.socket.close()
            except Exception:
                pass
            self.socket = None
            time.sleep(2)

    def _flush_send_buffer(self):
        """Non-blocking send using partial send logic."""
        if not self.send_buffer or self.socket is None:
            return

        with self._send_lock:
            try:
                sent = self.socket.send(self.send_buffer)
                if sent > 0:
                    del self.send_buffer[:sent]
                    self.log_info(f"{self.host}:{self.port} sent {sent} bytes")

            except BlockingIOError:
                self.log_info(f"{self.host}:{self.port} socket not ready for sending")
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
        with self._send_lock:
            self.send_buffer.clear()
