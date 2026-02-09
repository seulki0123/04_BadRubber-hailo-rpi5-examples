from .client import TCPClient
from .server import TCPServer
from rubber_tracker.utils import ProcessLogger, load_config

class NetworkEventHub(ProcessLogger):
    def __init__(self):
        super().__init__(__class__.__name__)
        config = load_config()

        # edge device client (listener)
        self.listener_clients = []
        for idx, listener_cfg in enumerate(config["network"]["listener"]):
            client = TCPClient(
                listener_cfg["host"],
                listener_cfg["port"],
                f"{__class__.__name__}_listener_{idx}"
            )
            self.listener_clients.append(client)

        # image db client (notifier)
        notifier_cfg = config["network"]["notifier"]
        self.notifier_client = None

        for client in self.listener_clients:
            if (
                client.host == notifier_cfg["host"]
                and client.port == notifier_cfg["port"]
            ):
                self.notifier_client = client
                self.log_warning("Notifier client is shared with a listener client")
                break

        if self.notifier_client is None:
            self.notifier_client = TCPClient(
                notifier_cfg["host"],
                notifier_cfg["port"],
                __class__.__name__ + "_notifier"
            )

        # local server (notifier)
        local_cfg = config["network"]["local"]
        self.local_server = TCPServer(
            local_cfg["host"],
            local_cfg["port"],
            __class__.__name__ + "_local"
        )
        
    def add_listener_callback(self, listener_callback):
        for client in self.listener_clients:
            client.add_callback(listener_callback)

    def notify_flow(self, data):
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

    def run(self):
        for client in self.listener_clients:
            client.start()
        if self.notifier_client not in self.listener_clients:
            self.notifier_client.start()
        self.local_server.start()
