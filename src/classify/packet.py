from typing import NamedTuple

class ClassificationPacket(NamedTuple):
    external_id: str
    classification: int
    confidence: float