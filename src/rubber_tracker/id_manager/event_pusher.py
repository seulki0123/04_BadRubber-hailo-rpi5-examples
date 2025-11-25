import json
import socket
import threading

import yaml

from .tcp.client import TCPClient
from .tcp.server import TCPServer
from rubber_tracker.utils import ModuleLogger

class EventPusher(ModuleLogger):
    def __init__(self, config_path="config.yaml"):
        super().__init__(__class__.__name__)
        with open(config_path, "r") as f:
            config = yaml.safe_load(f)

        self.output_server_host = config["idmanager"]["server"]["output_server"]["host"]
        self.output_server_port = config["idmanager"]["server"]["output_server"]["port"]
        self.output_server = TCPServer(self.output_server_host, self.output_server_port, self.__class__.__name__)

        self.imagedb_server_host = config["idmanager"]["client"]["imagedb_server"]["host"]
        self.imagedb_server_port = config["idmanager"]["client"]["imagedb_server"]["port"]
        self.imagedb_server = TCPClient(self.imagedb_server_host, self.imagedb_server_port, self.__class__.__name__)
    
    def accept_loop(self):
        self.output_server.accept_loop()
    
    def broadcast(self, ext_id: str, target: str, rejected: bool):
        self.output_server.broadcast(ext_id, target, rejected)
        self.imagedb_server.send_event(ext_id, target, rejected)