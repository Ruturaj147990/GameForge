"""Thread-safe in-process pub/sub event bus (Qt-free)."""
from __future__ import annotations

import collections
import fnmatch
import logging
import threading
from typing import Any, Callable, Deque, Dict, List, Optional, Tuple

logger = logging.getLogger(__name__)

Subscriber = Callable[[str, Dict[str, Any]], None]


class EventBus:
    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._subscribers: Dict[str, List[Subscriber]] = {}
        self._pattern_subscribers: Dict[str, List[Subscriber]] = {}
        self._global_subscribers: List[Subscriber] = []
        self._last_errors: Deque[Tuple[str, Exception]] = collections.deque(maxlen=100)

    def subscribe(self, topic: Optional[str], callback: Subscriber) -> Callable[[], None]:
        """Subscribe to a specific topic, wildcard pattern (e.g. 'run.*'), or all topics ('*'/None). Returns unsubscribe callable."""
        with self._lock:
            if topic is None or topic == "*":
                self._global_subscribers.append(callback)

                def unsubscribe() -> None:
                    with self._lock:
                        if callback in self._global_subscribers:
                            self._global_subscribers.remove(callback)

                return unsubscribe
            elif "*" in topic or "?" in topic:
                self._pattern_subscribers.setdefault(topic, []).append(callback)

                def unsubscribe() -> None:
                    with self._lock:
                        if topic in self._pattern_subscribers and callback in self._pattern_subscribers[topic]:
                            self._pattern_subscribers[topic].remove(callback)
                            if not self._pattern_subscribers[topic]:
                                del self._pattern_subscribers[topic]

                return unsubscribe
            else:
                self._subscribers.setdefault(topic, []).append(callback)

                def unsubscribe() -> None:
                    with self._lock:
                        if topic in self._subscribers and callback in self._subscribers[topic]:
                            self._subscribers[topic].remove(callback)
                            if not self._subscribers[topic]:
                                del self._subscribers[topic]

                return unsubscribe

    def unsubscribe(self, topic: Optional[str], callback: Subscriber) -> bool:
        """Unsubscribe a callback from a topic, pattern, or global subscription. Returns True if removed."""
        with self._lock:
            removed = False
            if topic is None or topic == "*":
                if callback in self._global_subscribers:
                    self._global_subscribers.remove(callback)
                    removed = True
            elif "*" in topic or "?" in topic:
                if topic in self._pattern_subscribers and callback in self._pattern_subscribers[topic]:
                    self._pattern_subscribers[topic].remove(callback)
                    if not self._pattern_subscribers[topic]:
                        del self._pattern_subscribers[topic]
                    removed = True
            else:
                if topic in self._subscribers and callback in self._subscribers[topic]:
                    self._subscribers[topic].remove(callback)
                    if not self._subscribers[topic]:
                        del self._subscribers[topic]
                    removed = True
            return removed

    def _invoke_subscriber(self, s: Subscriber, topic: str, payload: Dict[str, Any]) -> None:
        """Invokes a subscriber safely, supporting both (topic, event) and (event) signatures and isolating errors."""
        try:
            try:
                s(topic, dict(payload))
            except TypeError as te:
                # If subscriber takes only 1 argument (the event payload), call it with payload
                try:
                    s(dict(payload))  # type: ignore[call-arg]
                except Exception:
                    raise te
        except Exception as exc:
            logger.exception("EventBus subscriber %r error on topic %s: %s", s, topic, exc)
            with self._lock:
                self._last_errors.append((topic, exc))

    def publish(self, topic: str, event: Any) -> None:
        """Publish an event dict to a topic in a thread-safe manner, isolating subscriber failures."""
        if isinstance(event, dict):
            evt_copy = dict(event)
        else:
            evt_copy = {"payload": event}

        with self._lock:
            subs = list(self._subscribers.get(topic, []))
            # Match wildcard/pattern subscribers
            for pattern, p_subs in self._pattern_subscribers.items():
                if fnmatch.fnmatch(topic, pattern):
                    for ps in p_subs:
                        if ps not in subs:
                            subs.append(ps)
            globals_ = list(self._global_subscribers)

        # Call subscribers outside lock to prevent deadlocks, strictly isolating exceptions per subscriber
        for s in subs:
            self._invoke_subscriber(s, topic, evt_copy)

        for s in globals_:
            self._invoke_subscriber(s, topic, evt_copy)

    def subscriber_count(self, topic: Optional[str] = None) -> int:
        """Return the number of subscribers for a specific topic, or total across all topics if None."""
        with self._lock:
            if topic is None:
                return (
                    len(self._global_subscribers)
                    + sum(len(v) for v in self._subscribers.values())
                    + sum(len(v) for v in self._pattern_subscribers.values())
                )
            if topic == "*":
                return len(self._global_subscribers)
            if "*" in topic or "?" in topic:
                return len(self._pattern_subscribers.get(topic, []))
            return len(self._subscribers.get(topic, []))

    @property
    def errors(self) -> List[Tuple[str, Exception]]:
        """Return a copy of recently recorded subscriber errors."""
        with self._lock:
            return list(self._last_errors)

    def clear_errors(self) -> None:
        """Clear recorded subscriber errors."""
        with self._lock:
            self._last_errors.clear()

    def clear(self) -> None:
        """Unsubscribe all listeners and clear recorded errors."""
        with self._lock:
            self._subscribers.clear()
            self._pattern_subscribers.clear()
            self._global_subscribers.clear()
            self._last_errors.clear()



_DEFAULT_BUS: Optional[EventBus] = None
_BUS_LOCK = threading.Lock()


def default_bus() -> EventBus:
    global _DEFAULT_BUS
    with _BUS_LOCK:
        if _DEFAULT_BUS is None:
            _DEFAULT_BUS = EventBus()
        return _DEFAULT_BUS


def reset_default_bus() -> None:
    """Reset the default bus instance (useful for test isolation and clean shutdown)."""
    global _DEFAULT_BUS
    with _BUS_LOCK:
        if _DEFAULT_BUS is not None:
            _DEFAULT_BUS.clear()
        _DEFAULT_BUS = None

