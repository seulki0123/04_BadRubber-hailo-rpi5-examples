import json
import socket

from rubber_tracker.utils import ModuleLogger
from rubber_tracker.utils import CustomThread

class TCPServer(ModuleLogger):
    def __init__(self, host, port, name):
        super().__init__(self.__class__.__name__ + "_" + name)
        self.name = name
        self.host = host
        self.port = port
        self.socket = None
        self.clients = []

    def start(self):
        self.thread = CustomThread(name=self.__class__.__name__ + "_" + self.name, task=self._task, interval=0.01)
        self.thread.start()

    def _task(self):
        self._accept()

    def _open(self):
        try:
            self.socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            self.socket.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)

            self.socket.bind((self.host, self.port))
            self.socket.listen(5)

            # non-blocking accept
            self.socket.setblocking(False)

            self.log_info(f"TCPServer started on {self.host}:{self.port}")

        except Exception as e:
            self.log_error(f"Failed to start TCPServer: {e} on {self.host}:{self.port}")
            try:
                if self.socket:
                    self.socket.close()
            except:
                pass
            self.socket = None

    def _accept(self):
        if self.socket is None:
            self._open()
            return

        try:
            client, addr = self.socket.accept()
            client.setblocking(False)  # send 시 block 방지
            self.clients.append(client)
            self.log_info(f"Client connected: {addr}")
        except BlockingIOError:
            pass
        except Exception as e:
            self.log_error(f"Accept error: {e}")

    def broadcast(self, data):
        if isinstance(data, dict):
            msg = json.dumps(data)
        else:
            msg = str(data)

        msg = (msg + "\n").encode()

        dead_clients = []
        for c in self.clients:
            try:
                c.send(msg)
            except BlockingIOError:
                pass
            except Exception:
                dead_clients.append(c)

        for c in dead_clients:
            try:
                c.close()
            except Exception as e:
                self.log_error(f"Client close error: {e}")
            try:
                self.clients.remove(c)
            except Exception as e:
                self.log_error(f"Client remove error: {e}")