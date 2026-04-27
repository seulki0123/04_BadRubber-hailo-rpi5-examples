from .client import TCPClient
from .server import TCPServer
from rubber_tracker.utils import ProcessLogger, load_config

class NetworkEventHub(ProcessLogger):
    def __init__(self, profile_id=None):
        # 멀티 프로파일에서는 NetworkEventHub 인스턴스가 여러 개이므로
        # logger / TCP 클라이언트/서버 이름에 profile_id 를 섞어 식별성을 높인다.
        suffix = "" if profile_id is None else f"[{profile_id}]"
        logger_name = __class__.__name__ + suffix
        super().__init__(logger_name)
        self.profile_id = profile_id
        config = load_config(profile_id)

        # edge device client (listener)
        self.listener_clients = []
        for idx, listener_cfg in enumerate(config["network"]["listener"]):
            client = TCPClient(
                listener_cfg["host"],
                listener_cfg["port"],
                f"{logger_name}_listener_{idx}"
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
                logger_name + "_notifier"
            )

        # local server (notifier)
        local_cfg = config["network"]["local"]
        self.local_server = TCPServer(
            local_cfg["host"],
            local_cfg["port"],
            logger_name + "_local"
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

    def send_track_event_count(self, payload: dict):
        """이벤트 카운트 스냅샷만 notifier 로 전송 (로컬 broadcast 없음)."""
        self.notifier_client.send(payload)

    def run(self):
        for client in self.listener_clients:
            client.start()
        if self.notifier_client not in self.listener_clients:
            self.notifier_client.start()
        self.local_server.start()
