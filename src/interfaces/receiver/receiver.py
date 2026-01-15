from datetime import datetime

from .packet import ReceiverPacket
from ..utils import TCPClient
from ..utils import Connection
from utils import load_config, Queue, ProcessLogger

class Receiver(ProcessLogger):
    REQUIRED_KEYS = {"id", "time", "zone", "baler"}

    def __init__(self):
        super().__init__(self.__class__.__name__)
        config = load_config()["receiver"]

        self.conn: Connection = TCPClient(
            host=config["host"],
            port=config["port"],
            name=self.__class__.__name__,
        )
        self.conn.add_callback(self._on_message)

        self.queue: Queue[ReceiverPacket] = Queue(name=self.__class__.__name__, max_size=config["max_size"])

    def run(self) -> None:
        self.conn.start()

    def get_externals(self) -> list[ReceiverPacket]:
        return self.queue.get_all()

    def _on_message(self, msg: dict) -> None:
        try:
            packet = self._validate_and_build_packet(msg)
            self.queue.add(packet)
        except Exception as e:
            self.log_warning(f"Invalid message dropped: {msg} ({e})")

    def _validate_and_build_packet(self, msg: dict) -> ReceiverPacket:
        # 1. type check
        if not isinstance(msg, dict):
            raise ValueError("Message is not a dict")

        # 2. required keys exist
        missing = self.REQUIRED_KEYS - msg.keys()
        if missing:
            raise ValueError(f"Missing keys: {missing}")

        # 3. time parsing
        try:
            time = datetime.strptime(
                msg["time"], "%Y-%m-%d %H:%M:%S.%f"
            )
        except ValueError as e:
            raise ValueError(f"Invalid time format: {msg['time']}") from e

        # 4. packet creation
        return ReceiverPacket(
            external_id=str(msg["id"]),
            time=time,
            zone=str(msg["zone"]),
            baler=str(msg["baler"]),
        )