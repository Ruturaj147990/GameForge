"""ViewHost: QStackedWidget hosting Studio UX views lazily (WI-4.3)."""

from __future__ import annotations

from typing import Callable, Dict, Optional, Tuple

from PySide6.QtCore import Signal
from PySide6.QtWidgets import QStackedWidget, QWidget


class ViewHost(QStackedWidget):
    """Hosts application views with lazy instantiation and enable-guards."""

    viewChanged = Signal(str)

    def __init__(self, parent: Optional[QWidget] = None) -> None:
        super().__init__(parent)
        self.setObjectName("studioViewHost")
        self._factories: Dict[str, Callable[[], QWidget]] = {}
        self._enabled_guards: Dict[str, Callable[[], Tuple[bool, str]]] = {}
        self._widgets: Dict[str, QWidget] = {}
        self._current_view_id: str = ""

    def register(
        self,
        view_id: str,
        factory: Callable[[], QWidget],
        enabled_when: Optional[Callable[[], Tuple[bool, str]]] = None,
    ) -> None:
        """Register a view factory and optional enable predicate."""
        self._factories[view_id] = factory
        if enabled_when is not None:
            self._enabled_guards[view_id] = enabled_when

    def is_enabled(self, view_id: str) -> Tuple[bool, str]:
        """Check whether a view is currently enabled. Returns (is_enabled, reason_if_disabled)."""
        guard = self._enabled_guards.get(view_id)
        if guard is not None:
            return guard()
        return True, ""

    def show_view(self, view_id: str) -> bool:
        """Switch to view_id, instantiating it lazily if not yet created.

        Returns False without switching if view is disabled or unregistered.
        """
        if view_id not in self._factories:
            return False

        enabled, _ = self.is_enabled(view_id)
        if not enabled:
            return False

        if view_id not in self._widgets:
            try:
                widget = self._factories[view_id]()
                if widget is None:
                    return False
                widget.setObjectName(f"studioView_{view_id}")
                self.addWidget(widget)
                self._widgets[view_id] = widget
            except Exception as exc:
                import logging
                logging.getLogger(__name__).exception("Failed to instantiate view '%s': %s", view_id, exc)
                return False

        widget = self._widgets[view_id]
        self.setCurrentWidget(widget)
        self._current_view_id = view_id
        self.viewChanged.emit(view_id)
        return True

    @property
    def current_view_id(self) -> str:
        return self._current_view_id

    def get_view_widget(self, view_id: str) -> Optional[QWidget]:
        """Return the created widget for view_id if instantiated, else None."""
        return self._widgets.get(view_id)

    def instantiated_views(self) -> Tuple[str, ...]:
        return tuple(self._widgets.keys())
