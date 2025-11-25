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

        self.host = config["idmanager"]["client"]["input_server"]["host"]
        self.port = config["idmanager"]["client"]["input_server"]["port"]
        self.event_callback = event_callback

        self.tcp_client = TCPClient(self.host, self.port, self.__class__.__name__)
        
    def recv_loop(self):
        data = self.tcp_client.recv_loop()
        if data is None:
            return
        
        ext_id = data["id"]
        zone = data["zone"]
        time = data["time"]
        self.event_callback(ext_id, zone, time)