import yaml

from .client import TCPClient
from .server import TCPServer
from rubber_tracker.utils import ModuleLogger

class NetworkEventHub(ModuleLogger):
    def __init__(self, config_path="config.yaml"):
        super().__init__(__class__.__name__)
        with open(config_path, "r") as f:
            config = yaml.safe_load(f)

        # edge device client (listener)
        listener_host = config["network"]["listener"]["host"]
        listener_port = config["network"]["listener"]["port"]
        self.listener_client = TCPClient(listener_host, listener_port, __class__.__name__ + "_listener")
        
        # image db client (notifier)
        notifier_host = config["network"]["notifier"]["host"]
        notifier_port = config["network"]["notifier"]["port"]
        if notifier_host == listener_host and notifier_port == listener_port:
            self.notifier_client = self.listener_client
            self.log_warning("Notifier client is the same as listener client")
        else:
            self.notifier_client = TCPClient(notifier_host, notifier_port, self.__class__.__name__ + "_notifier")

        # local server (notifier)
        local_host = config["network"]["local"]["host"]
        local_port = config["network"]["local"]["port"]
        self.local_server = TCPServer(local_host, local_port, __class__.__name__ + "_local")

    def add_listener_callback(self, listener_callback):
        self.listener_client.add_callback(listener_callback)

    def start(self):
        self.listener_client.start()
        if self.listener_client != self.notifier_client:
            self.notifier_client.start()
        self.local_server.start()

    def notify_exit(self, data):
        """
        {
            "id": ext_id,
            "zone": zone,
            "rejected": rejected (true / false),
            "time": yyyy-MM-dd HH:mm:ss
        }
        """
        self.notifier_client.send(data)
        self.local_server.broadcast(data)
    
    def notify_weigher(self, data):
        """
        {
            "id": ext_id,
            "zone": zone, (weigher_a / weigher_b)
            "rejected": rejected (true / false),
            "time": yyyy-MM-dd HH:mm:ss
        }
        """
        self.notifier_client.send(data)
        self.local_server.broadcast(data)