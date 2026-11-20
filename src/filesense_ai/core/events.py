from collections.abc import Callable
from typing import TypeVar

T = TypeVar("T")


class EventHook:
    """Small dependency-free callback collection for service progress."""

    def __init__(self) -> None:
        self._callbacks: list[Callable[[object], None]] = []

    def connect(self, callback: Callable[[object], None]) -> None:
        self._callbacks.append(callback)

    def emit(self, value: object) -> None:
        for callback in tuple(self._callbacks):
            callback(value)
