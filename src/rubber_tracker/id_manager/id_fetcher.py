import json
import time
import socket
from datetime import datetime

import yaml

from .tcp.client import TCPClient
from rubber_tracker.utils import ModuleLogger

class IDFetcher(ModuleLogger):
    def __init__(self, event_callback, config_path="config.yaml"):
        super().__init__(__class__.__name__)
        with open(config_path, "r") as f:
            config = yaml.safe_load(f)

        host = config["idmanager"]["client"]["input_server"]["host"]
        port = config["idmanager"]["client"]["input_server"]["port"]
        self.id_fetcher_event = event_callback

        self.tcp_client = TCPClient(
            host,
            port,
            self.__class__.__name__,
            self._callback,
        )

        self.tcp_client.start()

    def send(self, ext_id, zone, rejected):
        self.tcp_client.send({
            "id": ext_id,
            "zone": zone,
            "rejected": rejected,
        })
    
    def _callback(self, data):
        if self.id_fetcher_event is None:
            return
        
        if not "id" in data or not "zone" in data:
            self.log_error(f"Invalid data received: {data}")
            return
        ext_id = data["id"]
        zone = data["zone"]
        time = data["time"] if "time" in data else ""
        self.id_fetcher_event(ext_id, zone, time)