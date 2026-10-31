"""Thread-safe in-process pub/sub event bus (Qt-free)."""
from __future__ import annotations

import threading
from typing import Any, Callable, Dict, List, Optional

Subscriber = Callable[[str, Dict[str, Any]], None]


class EventBus:
    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._subscribers: Dict[str, List[Subscriber]] = {}
        self._global_subscribers: List[Subscriber] = []

    def subscribe(self, topic: Optional[str], callback: Subscriber) -> Callable[[], None]:
        """Subscribe to a specific topic or all topics (if topic is None or '*'). Returns unsubscribe callable."""
        with self._lock:
            if topic is None or topic == "*":
                self._global_subscribers.append(callback)

                def unsubscribe() -> None:
                    with self._lock:
                        if callback in self._global_subscribers:
                            self._global_subscribers.remove(callback)

                return unsubscribe
            else:
                self._subscribers.setdefault(topic, []).append(callback)

                def unsubscribe() -> None:
                    with self._lock:
                        if topic in self._subscribers and callback in self._subscribers[topic]:
                            self._subscribers[topic].remove(callback)

                return unsubscribe

    def publish(self, topic: str, event: Dict[str, Any]) -> None:
        """Publish an event dict to a topic."""
        with self._lock:
            subs = list(self._subscribers.get(topic, []))
            globals_ = list(self._global_subscribers)
        for s in subs:
            try:
                s(topic, event)
            except Exception:
                pass
        for s in globals_:
            try:
                s(topic, event)
            except Exception:
                pass


_DEFAULT_BUS: Optional[EventBus] = None
_BUS_LOCK = threading.Lock()


def default_bus() -> EventBus:
    global _DEFAULT_BUS
    with _BUS_LOCK:
        if _DEFAULT_BUS is None:
            _DEFAULT_BUS = EventBus()
        return _DEFAULT_BUS
