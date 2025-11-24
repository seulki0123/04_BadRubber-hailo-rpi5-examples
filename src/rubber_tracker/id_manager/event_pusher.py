import json
import socket
import threading

import yaml

from rubber_tracker.utils import ModuleLogger

class EventPusher(ModuleLogger):
    def __init__(self, config_path="config.yaml"):
        super().__init__(__class__.__name__)
        with open(config_path, "r") as f:
            config = yaml.safe_load(f)

        self.host = config["idmanager"]["server"]["host"]
        self.port = config["idmanager"]["server"]["port"]

        self.server_socket = None
        self.clients = []

    def _start(self):
        try:
            self.server_socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            self.server_socket.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)

            self.server_socket.bind((self.host, self.port))
            self.server_socket.listen(5)

            # non-blocking accept
            self.server_socket.setblocking(False)

            self.log_info(f"EventPusher server started on {self.host}:{self.port}")

        except Exception as e:
            self.log_error(f"Failed to start EventPusher server: {e}")
            try:
                if self.server_socket:
                    self.server_socket.close()
            except:
                pass
            self.server_socket = None

    def accept_loop(self):
        if self.server_socket is None:
            self._start()
            return

        try:
            client, addr = self.server_socket.accept()
            client.setblocking(False)  # send 시 block 방지
            self.clients.append(client)
            self.log_info(f"ClientC connected: {addr}")
        except BlockingIOError:
            # 연결 들어온 게 없음
            pass
        except Exception as e:
            self.log_error(f"Accept error: {e}")

    def broadcast(self, ext_id: str, target: str, rejected: bool):
        message = {
            "id": ext_id,
            "target": target,
            "rejected": rejected,
        }

        msg = (json.dumps(message) + "\n").encode()

        dead_clients = []

        for c in self.clients:
            try:
                c.send(msg)
            except Exception:
                dead_clients.append(c)

        for c in dead_clients:
            try:
                c.close()
            except:
                pass
            try:
                self.clients.remove(c)
            except:
                pass