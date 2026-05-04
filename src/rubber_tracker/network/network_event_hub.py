from .client import TCPClient
from .server import TCPServer
from rubber_tracker.utils import ProcessLogger, load_config

class NetworkEventHub(ProcessLogger):
    """
    network.client allows only one TCPClient per endpoint(host, port).

    network:
        client:
        - bind: "192.168.20.11"
        host: "192.168.20.10"
        port: 5000
        notify: { enabled: true, types: ["track_event_movement"] }
        listen: { enabled: true, types: ["track_event_count_reset"] }
        server:
        bind: "192.168.20.11"
        port: 5000
        types: ["track_event_movement"]
    """

    def __init__(self, profile_id=None):
        suffix = "" if profile_id is None else f"[{profile_id}]"
        logger_name = __class__.__name__ + suffix
        super().__init__(logger_name)

        self._clients = []
        self.notifier_clients = []
        self.listener_clients = []

        net_cfg = load_config(profile_id)["network"]
        self._build_clients(net_cfg["client"], logger_name)
        self._build_server(net_cfg["server"], logger_name)

    def add_listener_callback(self, listener_callback):
        for client, types in self.listener_clients:
            client.add_callback(self._make_filtered_callback(listener_callback, types))

    def notify_flow(self, data):
        t = data["type"]
        for client, types in self.notifier_clients:
            if t in types:
                client.send(data)
        if t in self.server_types:
            self.server.broadcast(data)

    def send_track_event_count(self, payload: dict):
        # TODO: notify_flow 랑 겹침, track_event_count 전용 코드들 확인 필요할듯.. 너무 하드코딩이?
        t = payload["type"]
        for client, types in self.notifier_clients:
            if t in types:
                client.send(payload)

    def run(self):
        for client in self._clients:
            client.start()
        self.server.start()

    def _build_clients(self, clients_cfg, logger_name):
        self._check_duplicate_endpoints(clients_cfg)

        for idx, c in enumerate(clients_cfg):
            self._attach_client(idx, c, logger_name)

    def _attach_client(self, idx, c, logger_name):
        notify = c["notify"]
        listen = c["listen"]

        client = TCPClient(
            c["host"],
            c["port"],
            f"{logger_name}_c{idx}",
            bind=c["bind"]
        )
        self._clients.append(client)
        if notify["enabled"]: self.notifier_clients.append((client, frozenset(notify["types"])))
        if listen["enabled"]: self.listener_clients.append((client, frozenset(listen["types"])))

    def _build_server(self, server_cfg, logger_name):
        self.server = TCPServer(
            server_cfg["bind"],
            server_cfg["port"],
            logger_name + "_server",
        )
        self.server_types = frozenset(server_cfg["types"])

    @staticmethod
    def _check_duplicate_endpoints(clients_cfg):
        eps = [(c["host"], c["port"]) for c in clients_cfg]
        if len(eps) != len(set(eps)):
            raise ValueError("network.client endpoint duplicated")
                
    @staticmethod
    def _make_filtered_callback(callback, allowed_types):
        def _filtered(data):
            if data["type"] in allowed_types:
                callback(data)
        return _filtered