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

    def start(self):
        self.server_socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        self.server_socket.bind((self.host, self.port))
        self.server_socket.listen(5)

        self.log_info(f"EventPusher server started on {self.host}:{self.port}")

        threading.Thread(target=self.accept_loop, daemon=True).start()

    def accept_loop(self):
        while True:
            client, addr = self.server_socket.accept()
            self.clients.append(client)
            self.log_info(f"ClientC connected: {addr}")

    def broadcast(self, ext_id: str, target: str, rejected: bool):
        message = {
            "id": ext_id,
            "target": target,
            "rejected": rejected,
        }

        dead_clients = []

        for c in self.clients:
            try:
                msg = json.dumps(message) + "\n"
                c.send(msg.encode())
            except:
                dead_clients.append(c)

        for c in dead_clients:
            self.clients.remove(c)