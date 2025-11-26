import json
import socket
import threading

import yaml

from .tcp.client import TCPClient
from .tcp.server import TCPServer
from rubber_tracker.utils import ModuleLogger

class EventNotifier(ModuleLogger):
    def __init__(self, config_path="config.yaml"):
        super().__init__(__class__.__name__)
        with open(config_path, "r") as f:
            config = yaml.safe_load(f)

        # server
        host = config["idmanager"]["server"]["output_server"]["host"]
        port = config["idmanager"]["server"]["output_server"]["port"]
        self.output_server = TCPServer(
            host=host,
            port=port,
            name=self.__class__.__name__,
        )
        self.output_server.start()

        # client
        host = config["idmanager"]["client"]["imagedb_server"]["host"]
        port = config["idmanager"]["client"]["imagedb_server"]["port"]
        self.imagedb_client = TCPClient(
            host,
            port,
            self.__class__.__name__,
            None,
        )

        self.imagedb_client.start()
    
    def notify(self, ext_id, target, rejected):
        data = {
            "id": ext_id,
            "zone": zone,
            "rejected": rejected,
        }
        self.imagedb_client.send(data)
        self.output_server.broadcast(data)