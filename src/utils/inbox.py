from typing import Generic, TypeVar

T = TypeVar("T")

class Inbox(Generic[T]):
    def __init__(self):
        self._items: list[T] = []

    def push(self, items: list[T]):
        self._items.extend(items)

    def snapshot(self) -> list[T]:
        return list(self._items)

    def ack(self, used_items: list[T]):
        self._items = [i for i in self._items if i not in used_items]

    def __repr__(self):
        n = len(self._items)
        return f"Inbox(num={n}, items={self._items})"
