"""GameForge IDE — Studio UX Desktop Shell Package.

Provides core shell frame components: activity rail navigation, command palette,
view host container, top navigation bar, collapsible assistant panel, and toast overlays.
"""

from __future__ import annotations

from .view_host import ViewHost
from .rail import Rail, RailButton
from .top_bar import TopBar
from .assistant_panel import AssistantPanel
from .toasts import ToastOverlay, ToastCard
from .palette import CommandPalette

__all__ = [
    "ViewHost",
    "Rail",
    "RailButton",
    "TopBar",
    "AssistantPanel",
    "ToastOverlay",
    "ToastCard",
    "CommandPalette",
]

