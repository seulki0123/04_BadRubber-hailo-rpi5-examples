from typing import NamedTuple
from datetime import datetime

class ReceiverPacket(NamedTuple):
    external_id: str
    time: datetime
    zone: str
    baler: str