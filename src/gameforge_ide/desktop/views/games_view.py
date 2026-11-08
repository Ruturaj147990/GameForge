"""Games view for Studio UX v2 (spec §4.2, WI-4.5).

Displays:
- Grid/list toggle of game cards
- Thumbnail (latest scenario capture, else gameplay screenshot)
- Title, genre, last run status + time, GDS revision
- Card actions: Open (Design), Play, Build, Show in Explorer, Delete
- Delete confirmation dialog listing directories and requiring typed game name
- Refuses deletion if project is open in an active Unreal Editor link
"""
from __future__ import annotations

import logging
import os
from pathlib import Path
import subprocess
import sys
import time
from typing import Any, Dict, List, Optional, Tuple, Union

from PySide6.QtCore import (
    QAbstractListModel,
    QEvent,
    QModelIndex,
    QObject,
    QPoint,
    QRect,
    QRectF,
    QSize,
    Qt,
    Signal,
    Slot,
)
from PySide6.QtGui import (
    QAction,
    QBrush,
    QColor,
    QFont,
    QIcon,
    QPainter,
    QPainterPath,
    QPen,
    QPixmap,
)
from PySide6.QtWidgets import (
    QComboBox,
    QDialog,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QListView,
    QMenu,
    QMessageBox,
    QPushButton,
    QStyle,
    QStyledItemDelegate,
    QStyleOptionViewItem,
    QVBoxLayout,
    QWidget,
)

from ..icons import icon
from ..services.projects_service import (
    GameSummary,
    delete_project,
    list_games,
)
from ..styles import tokens
from ...core.jobs import JobHandle, default_job_manager
from ...core.projects import resolve_project_dir

logger = logging.getLogger(__name__)

GAME_ROLE = Qt.UserRole + 1


class GamesListModel(QAbstractListModel):
    """List model backed by a collection of GameSummary objects with filter and sort."""

    def __init__(self, parent: Optional[QObject] = None) -> None:
        super().__init__(parent)
        self._all_games: List[GameSummary] = []
        self._filtered_games: List[GameSummary] = []
        self._search_query: str = ""
        self._status_filter: str = "all"
        self._sort_mode: str = "recent"

    def rowCount(self, parent: QModelIndex = QModelIndex()) -> int:
        if parent.isValid():
            return 0
        return len(self._filtered_games)

    def data(self, index: QModelIndex, role: int = Qt.DisplayRole) -> Any:
        if not index.isValid() or not (0 <= index.row() < len(self._filtered_games)):
            return None
        game = self._filtered_games[index.row()]
        if role == Qt.DisplayRole:
            return game.title
        if role == GAME_ROLE:
            return game
        return None

    def set_games(self, games: List[GameSummary]) -> None:
        self._all_games = list(games)
        self._apply_filters()

    def get_game(self, row: int) -> Optional[GameSummary]:
        if 0 <= row < len(self._filtered_games):
            return self._filtered_games[row]
        return None

    def set_search_query(self, query: str) -> None:
        self._search_query = query.strip().lower()
        self._apply_filters()

    def set_status_filter(self, status: str) -> None:
        self._status_filter = status.lower()
        self._apply_filters()

    def set_sort_mode(self, mode: str) -> None:
        self._sort_mode = mode
        self._apply_filters()

    def _apply_filters(self) -> None:
        self.beginResetModel()
        filtered = []
        for g in self._all_games:
            # Search query
            if self._search_query:
                g_title = g.title or g.name or ""
                g_genre = g.genre or ""
                g_pitch = g.pitch or ""
                target = f"{g.name} {g_title} {g_genre} {g_pitch}".lower()
                if self._search_query not in target:
                    continue
            # Status filter
            if self._status_filter != "all":
                last_st = (g.last_run_status or "unbuilt").lower()
                if self._status_filter == "pass" and last_st not in ("done", "pass"):
                    continue
                elif self._status_filter == "fail" and last_st not in ("failed", "fail", "error"):
                    continue
                elif self._status_filter == "running" and last_st != "running":
                    continue
                elif self._status_filter == "unbuilt" and g.last_run_status:
                    continue
            filtered.append(g)

        # Sorting
        if self._sort_mode == "name":
            filtered.sort(key=lambda g: (g.title or g.name or "").lower())
        else:  # "recent"
            filtered.sort(key=lambda g: getattr(g, "updated_at", 0.0) or 0.0, reverse=True)

        self._filtered_games = filtered
        self.endResetModel()


class GameCardDelegate(QStyledItemDelegate):
    """Paints cards in IconMode or rows in ListMode with design tokens."""

    def __init__(self, parent: Optional[QObject] = None) -> None:
        super().__init__(parent)
        self._pixmap_cache: Dict[str, QPixmap] = {}

    def sizeHint(self, option: QStyleOptionViewItem, index: QModelIndex) -> QSize:
        list_view = option.widget
        if isinstance(list_view, QListView) and list_view.viewMode() == QListView.IconMode:
            return QSize(220, 240)
        return QSize(option.rect.width(), 64)

    def paint(self, painter: QPainter, option: QStyleOptionViewItem, index: QModelIndex) -> None:
        game: Optional[GameSummary] = index.data(GAME_ROLE)
        if not game:
            super().paint(painter, option, index)
            return

        painter.save()
        painter.setRenderHint(QPainter.Antialiasing, True)
        painter.setRenderHint(QPainter.SmoothPixmapTransform, True)

        list_view = option.widget
        is_icon_mode = isinstance(list_view, QListView) and list_view.viewMode() == QListView.IconMode

        if is_icon_mode:
            self._paint_card(painter, option, game)
        else:
            self._paint_row(painter, option, game)

        painter.restore()

    def _paint_card(self, painter: QPainter, option: QStyleOptionViewItem, game: GameSummary) -> None:
        r = option.rect.adjusted(6, 6, -6, -6)
        is_hover = bool(option.state & QStyle.State_MouseOver)
        is_selected = bool(option.state & QStyle.State_Selected)

        # Background
        bg_col = QColor(tokens.BG_HOVER) if is_hover else QColor(tokens.BG_SURFACE)
        border_col = QColor(tokens.ACCENT_PRIMARY) if (is_selected or is_hover) else QColor(tokens.BORDER)

        painter.setBrush(QBrush(bg_col))
        painter.setPen(QPen(border_col, 1.5 if (is_selected or is_hover) else 1.0))
        painter.drawRoundedRect(r, tokens.RADIUS, tokens.RADIUS)

        # Thumbnail area (top 124px)
        thumb_rect = QRect(r.x() + 8, r.y() + 8, r.width() - 16, 124)
        painter.setPen(Qt.NoPen)
        painter.setBrush(QBrush(QColor(tokens.BG_PANEL)))
        painter.drawRoundedRect(thumb_rect, 4, 4)

        pixmap = self._get_thumbnail(game.thumbnail_path, thumb_rect.size())
        if pixmap:
            painter.drawPixmap(thumb_rect.x(), thumb_rect.y(), pixmap)
        else:
            painter.setPen(QColor(tokens.TEXT_MUTED))
            font = painter.font()
            font.setPointSize(24)
            painter.setFont(font)
            painter.drawText(thumb_rect, Qt.AlignCenter, "🎮")

        # Title
        title_y = thumb_rect.bottom() + 10
        painter.setPen(QColor(tokens.TEXT_PRIMARY))
        font = painter.font()
        font.setPointSize(tokens.FONT_BODY)
        font.setBold(True)
        painter.setFont(font)
        title_rect = QRect(r.x() + 10, title_y, r.width() - 20, 20)
        title_str = game.title or game.name or "Untitled"
        elided_title = painter.fontMetrics().elidedText(title_str, Qt.ElideRight, title_rect.width())
        painter.drawText(title_rect, Qt.AlignLeft | Qt.AlignVCenter, elided_title)

        # Genre & revision badge
        meta_y = title_y + 22
        painter.setPen(QColor(tokens.TEXT_SECONDARY))
        font.setPointSize(tokens.FONT_BODY_SM)
        font.setBold(False)
        painter.setFont(font)
        meta_rect = QRect(r.x() + 10, meta_y, r.width() - 20, 16)
        genre_str = (game.genre or "unknown").capitalize()
        rev_val = getattr(game, "revision", 1) or 1
        painter.drawText(meta_rect, Qt.AlignLeft | Qt.AlignVCenter, f"{genre_str} · rev {rev_val}")

        # Status badge & time (bottom row)
        status_y = meta_y + 20
        status_text, dot_color = self._format_status_badge(game)

        # Dot
        dot_rect = QRect(r.x() + 10, status_y + 3, 8, 8)
        painter.setBrush(QBrush(QColor(dot_color)))
        painter.setPen(Qt.NoPen)
        painter.drawEllipse(dot_rect)

        # Status label
        painter.setPen(QColor(tokens.TEXT_MUTED))
        status_rect = QRect(r.x() + 24, status_y, r.width() - 34, 16)
        painter.drawText(status_rect, Qt.AlignLeft | Qt.AlignVCenter, status_text)

    def _paint_row(self, painter: QPainter, option: QStyleOptionViewItem, game: GameSummary) -> None:
        r = option.rect.adjusted(4, 2, -4, -2)
        is_hover = bool(option.state & QStyle.State_MouseOver)
        is_selected = bool(option.state & QStyle.State_Selected)

        bg_col = QColor(tokens.BG_HOVER) if is_hover else QColor(tokens.BG_SURFACE)
        border_col = QColor(tokens.ACCENT_PRIMARY) if (is_selected or is_hover) else QColor(tokens.BORDER)

        painter.setBrush(QBrush(bg_col))
        painter.setPen(QPen(border_col, 1.0))
        painter.drawRoundedRect(r, tokens.RADIUS, tokens.RADIUS)

        # Small thumbnail 48x48
        thumb_rect = QRect(r.x() + 6, r.y() + 6, 48, 48)
        painter.setBrush(QBrush(QColor(tokens.BG_PANEL)))
        painter.setPen(Qt.NoPen)
        painter.drawRoundedRect(thumb_rect, 4, 4)

        pixmap = self._get_thumbnail(game.thumbnail_path, thumb_rect.size())
        if pixmap:
            painter.drawPixmap(thumb_rect.x(), thumb_rect.y(), pixmap)
        else:
            painter.setPen(QColor(tokens.TEXT_MUTED))
            font = painter.font()
            font.setPointSize(16)
            painter.setFont(font)
            painter.drawText(thumb_rect, Qt.AlignCenter, "🎮")

        # Text information
        font = painter.font()
        font.setPointSize(tokens.FONT_BODY)
        font.setBold(True)
        painter.setFont(font)
        painter.setPen(QColor(tokens.TEXT_PRIMARY))
        title_str = game.title or game.name or "Untitled"
        elided_title = painter.fontMetrics().elidedText(title_str, Qt.ElideRight, 260)
        genre_str = (game.genre or "unknown").capitalize()
        rev_val = getattr(game, "revision", 1) or 1
        painter.drawText(QRect(r.x() + 64, r.y() + 10, 260, 20), Qt.AlignLeft | Qt.AlignVCenter, elided_title)

        font.setPointSize(tokens.FONT_BODY_SM)
        font.setBold(False)
        painter.setFont(font)
        painter.setPen(QColor(tokens.TEXT_SECONDARY))
        painter.drawText(QRect(r.x() + 64, r.y() + 32, 260, 16), Qt.AlignLeft | Qt.AlignVCenter, f"{genre_str} · rev {rev_val}")

        # Status on the right
        status_text, dot_color = self._format_status_badge(game)
        right_x = r.right() - 140
        dot_rect = QRect(right_x, r.y() + 26, 8, 8)
        painter.setBrush(QBrush(QColor(dot_color)))
        painter.setPen(Qt.NoPen)
        painter.drawEllipse(dot_rect)

        painter.setPen(QColor(tokens.TEXT_MUTED))
        painter.drawText(QRect(right_x + 14, r.y() + 22, 120, 16), Qt.AlignLeft | Qt.AlignVCenter, status_text)

    def clear_cache(self) -> None:
        self._pixmap_cache.clear()

    def _get_thumbnail(self, path: Optional[Path], size: QSize) -> Optional[QPixmap]:
        if not path or not str(path):
            return None
        key = f"{path}_{size.width()}x{size.height()}"
        if key in self._pixmap_cache:
            return self._pixmap_cache[key]

        if Path(path).is_file():
            try:
                pm = QPixmap(str(path))
                if not pm.isNull():
                    scaled = pm.scaled(size, Qt.KeepAspectRatioByExpanding, Qt.SmoothTransformation)
                    self._pixmap_cache[key] = scaled
                    return scaled
            except Exception:
                pass
        return None

    def _format_status_badge(self, game: GameSummary) -> Tuple[str, str]:
        st = game.last_run_status or "—"
        if st in ("DONE", "PASS"):
            dot_color = tokens.ACCENT_SUCCESS
            st_label = "PASS"
        elif st in ("FAILED", "FAIL", "ERROR"):
            dot_color = tokens.ACCENT_ERROR
            st_label = "FAIL"
        elif st == "RUNNING":
            dot_color = tokens.ACCENT_WARNING
            st_label = "RUNNING"
        else:
            dot_color = tokens.TEXT_MUTED
            st_label = "UNBUILT"

        time_part = ""
        up_at = getattr(game, "updated_at", 0.0) or 0.0
        if up_at > 0:
            diff_s = max(0.0, time.time() - up_at)
            if diff_s < 3600:
                time_part = f"{int(diff_s // 60)}m"
            elif diff_s < 86400:
                time_part = f"{int(diff_s // 3600)}h"
            else:
                time_part = f"{int(diff_s // 86400)}d"
        return f"{st_label} {time_part}".strip(), dot_color


from ..dialogs.delete_game_dialog import DeleteGameDialog


class GamesView(QWidget):
    """Games view implementation for Studio UX (spec §4.2, WI-4.5)."""

    openGameRequested = Signal(str)     # (project_name) -> open in Design
    playGameRequested = Signal(str)     # (project_name) -> Play view / launch
    buildGameRequested = Signal(str)    # (project_name) -> Build view
    gameSelected = Signal(str)          # (project_name) -> active project selection
    newProjectRequested = Signal(str, Path)   # (project_name, project_dir)
    openProjectRequested = Signal(Path)       # (project_dir)
    beforeGameDeleted = Signal(str, Path)     # (project_name, project_dir)
    gameDeleted = Signal(str, Path)           # (project_name, project_dir)
    _delete_finished = Signal(bool, str, str, Path)  # (success, project_name, error_msg, project_dir)

    def __init__(
        self,
        projects_root: Optional[Union[str, Path]] = None,
        workspace_dir: Optional[Union[str, Path]] = None,
        projects_service: Optional[Any] = None,
        parent: Optional[QWidget] = None,
    ) -> None:
        super().__init__(parent)
        self.setObjectName("gamesView")
        self.setAccessibleName("GameForge Games View")

        self._projects_root = Path(projects_root).resolve() if projects_root else None
        self._workspace_dir = Path(workspace_dir).resolve() if workspace_dir else None
        self._projects_service: Optional[Any] = None
        self._refresh_seq: int = 0
        self._selected_game_name: Optional[str] = None
        self._model = GamesListModel(self)
        self._job_manager = default_job_manager()
        self._delete_finished.connect(self._on_delete_finished)

        main_layout = QVBoxLayout(self)
        main_layout.setContentsMargins(24, 20, 24, 20)
        main_layout.setSpacing(tokens.SPACE_MD)

        # ── Toolbar ──────────────────────────────────────────────────────────
        tb_layout = QHBoxLayout()
        tb_layout.setSpacing(tokens.SPACE_SM)

        title_lbl = QLabel("Games", self)
        title_lbl.setObjectName("gamesTitle")
        title_lbl.setAccessibleName("Games View Title")
        title_lbl.setStyleSheet(
            f"color: {tokens.TEXT_PRIMARY};"
            f"font-size: {tokens.FONT_HEADING}px;"
            f"font-weight: 700;"
        )
        tb_layout.addWidget(title_lbl)
        tb_layout.addSpacing(tokens.SPACE_MD)

        # Search bar
        self._search_input = QLineEdit(self)
        self._search_input.setObjectName("gamesSearchInput")
        self._search_input.setAccessibleName("Search games")
        self._search_input.setPlaceholderText("Search games… (Esc to clear)")
        self._search_input.setClearButtonEnabled(True)
        self._search_input.setFixedWidth(240)
        self._search_input.setStyleSheet(
            f"QLineEdit#{self._search_input.objectName()} {{"
            f"  background-color: {tokens.BG_SURFACE};"
            f"  color: {tokens.TEXT_PRIMARY};"
            f"  border: 1px solid {tokens.BORDER};"
            f"  border-radius: {tokens.RADIUS}px;"
            f"  padding: 4px {tokens.SPACE_SM}px;"
            f"  font-size: {tokens.FONT_BODY}px;"
            f"}}"
            f"QLineEdit#{self._search_input.objectName()}:focus {{"
            f"  border-color: {tokens.BORDER_FOCUS};"
            f"  outline: none;"
            f"}}"
        )
        self._search_input.textChanged.connect(self._model.set_search_query)
        self._search_input.installEventFilter(self)
        tb_layout.addWidget(self._search_input)

        # Filter combo
        self._filter_combo = QComboBox(self)
        self._filter_combo.setObjectName("gamesFilterCombo")
        self._filter_combo.setAccessibleName("Filter games by status")
        self._filter_combo.addItems(["All statuses", "PASS", "FAIL", "Running", "Unbuilt"])
        self._filter_combo.setStyleSheet(
            f"QComboBox#{self._filter_combo.objectName()} {{"
            f"  background-color: {tokens.BG_SURFACE};"
            f"  color: {tokens.TEXT_PRIMARY};"
            f"  border: 1px solid {tokens.BORDER};"
            f"  border-radius: {tokens.RADIUS}px;"
            f"  padding: 4px {tokens.SPACE_SM}px;"
            f"}}"
        )
        self._filter_combo.currentTextChanged.connect(self._on_filter_changed)
        tb_layout.addWidget(self._filter_combo)

        # Sort combo
        self._sort_combo = QComboBox(self)
        self._sort_combo.setObjectName("gamesSortCombo")
        self._sort_combo.setAccessibleName("Sort games")
        self._sort_combo.addItem("Most Recent", userData="recent")
        self._sort_combo.addItem("Name A-Z", userData="name")
        self._sort_combo.setStyleSheet(
            f"QComboBox#{self._sort_combo.objectName()} {{"
            f"  background-color: {tokens.BG_SURFACE};"
            f"  color: {tokens.TEXT_PRIMARY};"
            f"  border: 1px solid {tokens.BORDER};"
            f"  border-radius: {tokens.RADIUS}px;"
            f"  padding: 4px {tokens.SPACE_SM}px;"
            f"}}"
        )
        self._sort_combo.currentIndexChanged.connect(self._on_sort_changed)
        tb_layout.addWidget(self._sort_combo)

        tb_layout.addStretch(1)

        # Grid / List toggle
        self._btn_mode = QPushButton("Grid", self)
        self._btn_mode.setObjectName("gamesBtnViewMode")
        self._btn_mode.setAccessibleName("Toggle Grid and List View Mode")
        self._btn_mode.setToolTip("View mode: Grid. Click to switch to List view.")
        self._btn_mode.setCursor(Qt.PointingHandCursor)
        self._btn_mode.setStyleSheet(
            f"QPushButton#{self._btn_mode.objectName()} {{"
            f"  background-color: {tokens.BG_SURFACE};"
            f"  color: {tokens.TEXT_PRIMARY};"
            f"  border: 1px solid {tokens.BORDER};"
            f"  border-radius: {tokens.RADIUS}px;"
            f"  padding: 4px {tokens.SPACE_MD}px;"
            f"  font-size: {tokens.FONT_BODY_SM}px;"
            f"  font-weight: 500;"
            f"}}"
            f"QPushButton#{self._btn_mode.objectName()}:hover, QPushButton#{self._btn_mode.objectName()}:focus {{"
            f"  background-color: {tokens.BG_HOVER};"
            f"  border-color: {tokens.BORDER_FOCUS};"
            f"  outline: none;"
            f"}}"
        )
        self._btn_mode.clicked.connect(self._toggle_view_mode)
        tb_layout.addWidget(self._btn_mode)

        # Refresh button
        self._btn_refresh = QPushButton("Refresh", self)
        self._btn_refresh.setObjectName("gamesBtnRefresh")
        self._btn_refresh.setAccessibleName("Refresh games list")
        self._btn_refresh.setCursor(Qt.PointingHandCursor)
        self._btn_refresh.setStyleSheet(
            f"QPushButton#{self._btn_refresh.objectName()} {{"
            f"  background-color: {tokens.BG_SURFACE};"
            f"  color: {tokens.TEXT_PRIMARY};"
            f"  border: 1px solid {tokens.BORDER};"
            f"  border-radius: {tokens.RADIUS}px;"
            f"  padding: 4px {tokens.SPACE_MD}px;"
            f"  font-size: {tokens.FONT_BODY_SM}px;"
            f"}}"
        )
        self._btn_refresh.clicked.connect(self.refresh_games)
        tb_layout.addWidget(self._btn_refresh)

        # Open Project button
        self._btn_open = QPushButton("Open…", self)
        self._btn_open.setObjectName("gamesBtnOpenProject")
        self._btn_open.setAccessibleName("Open existing project directory")
        self._btn_open.setCursor(Qt.PointingHandCursor)
        self._btn_open.setStyleSheet(
            f"QPushButton#{self._btn_open.objectName()} {{"
            f"  background-color: {tokens.BG_SURFACE};"
            f"  color: {tokens.TEXT_PRIMARY};"
            f"  border: 1px solid {tokens.BORDER};"
            f"  border-radius: {tokens.RADIUS}px;"
            f"  padding: 4px {tokens.SPACE_MD}px;"
            f"  font-size: {tokens.FONT_BODY_SM}px;"
            f"}}"
        )
        self._btn_open.clicked.connect(self._on_open_project_clicked)
        tb_layout.addWidget(self._btn_open)

        # New Project button
        self._btn_new = QPushButton("+ New Project…", self)
        self._btn_new.setObjectName("gamesBtnNewProject")
        self._btn_new.setAccessibleName("Create new project at user-selected directory")
        self._btn_new.setCursor(Qt.PointingHandCursor)
        self._btn_new.setStyleSheet(
            f"QPushButton#{self._btn_new.objectName()} {{"
            f"  background-color: {tokens.ACCENT_PRIMARY};"
            f"  color: {tokens.TEXT_PRIMARY};"
            f"  border: none;"
            f"  border-radius: {tokens.RADIUS}px;"
            f"  padding: 4px {tokens.SPACE_MD}px;"
            f"  font-size: {tokens.FONT_BODY_SM}px;"
            f"  font-weight: 600;"
            f"}}"
        )
        self._btn_new.clicked.connect(self._on_new_project_clicked)
        tb_layout.addWidget(self._btn_new)

        main_layout.addLayout(tb_layout)

        # ── List / Grid View ──────────────────────────────────────────────────
        self._list_view = QListView(self)
        self._list_view.setObjectName("gamesListView")
        self._list_view.setAccessibleName("Games catalog view")
        self._list_view.setModel(self._model)
        self._delegate = GameCardDelegate(self._list_view)
        self._list_view.setItemDelegate(self._delegate)
        self._list_view.setViewMode(QListView.IconMode)
        self._list_view.setResizeMode(QListView.Adjust)
        self._list_view.setSpacing(12)
        self._list_view.setUniformItemSizes(True)
        self._list_view.setFocusPolicy(Qt.StrongFocus)
        self._list_view.setContextMenuPolicy(Qt.CustomContextMenu)
        self._list_view.customContextMenuRequested.connect(self._show_context_menu)
        self._list_view.doubleClicked.connect(self._on_item_double_clicked)
        self._list_view.installEventFilter(self)
        self._list_view.setStyleSheet(
            f"QListView#{self._list_view.objectName()} {{"
            f"  background-color: transparent;"
            f"  border: none;"
            f"  outline: none;"
            f"}}"
        )
        if self._list_view.selectionModel():
            self._list_view.selectionModel().currentChanged.connect(self._on_selection_changed)
        main_layout.addWidget(self._list_view)

        # Empty state placeholder with call-to-action button
        self._empty_container = QWidget(self)
        self._empty_container.setObjectName("gamesEmptyContainer")
        empty_layout = QVBoxLayout(self._empty_container)
        empty_layout.setAlignment(Qt.AlignCenter)
        empty_layout.setSpacing(tokens.SPACE_MD)

        self._lbl_empty = QLabel(
            "No games found. Click '+ New Project…' to create a game or 'Open…' to import an existing project.",
            self._empty_container,
        )
        self._lbl_empty.setObjectName("gamesEmptyLabel")
        self._lbl_empty.setAlignment(Qt.AlignCenter)
        self._lbl_empty.setStyleSheet(
            f"color: {tokens.TEXT_MUTED};"
            f"font-size: {tokens.FONT_BODY}px;"
            f"padding: {tokens.SPACE_LG}px;"
        )
        empty_layout.addWidget(self._lbl_empty)

        self._btn_empty_new = QPushButton("+ New Project…", self._empty_container)
        self._btn_empty_new.setObjectName("gamesBtnEmptyNewProject")
        self._btn_empty_new.setAccessibleName("Create new project from empty catalog")
        self._btn_empty_new.setCursor(Qt.PointingHandCursor)
        self._btn_empty_new.setStyleSheet(
            f"QPushButton#{self._btn_empty_new.objectName()} {{"
            f"  background-color: {tokens.ACCENT_PRIMARY};"
            f"  color: {tokens.TEXT_PRIMARY};"
            f"  border: none;"
            f"  border-radius: {tokens.RADIUS}px;"
            f"  padding: 8px {tokens.SPACE_LG}px;"
            f"  font-size: {tokens.FONT_BODY}px;"
            f"  font-weight: 600;"
            f"}}"
            f"QPushButton#{self._btn_empty_new.objectName()}:hover {{"
            f"  background-color: {tokens.ACCENT_HOVER};"
            f"}}"
        )
        self._btn_empty_new.clicked.connect(self._on_new_project_clicked)
        empty_layout.addWidget(self._btn_empty_new, 0, Qt.AlignCenter)

        self._empty_container.setVisible(False)
        self._lbl_empty.setVisible(False)
        main_layout.addWidget(self._empty_container)

        # Initial projects service connection or refresh
        if projects_service is not None:
            self.attach_projects_service(projects_service)
        else:
            self.refresh_games()

    def showEvent(self, event: Any) -> None:
        super().showEvent(event)
        self.refresh_games()

    def eventFilter(self, watched: QObject, event: QEvent) -> bool:
        if watched is self._search_input and event.type() == QEvent.KeyPress:
            if event.key() == Qt.Key_Escape:
                self._search_input.clear()
                return True
            elif event.key() in (Qt.Key_Down, Qt.Key_Return, Qt.Key_Enter):
                self._list_view.setFocus()
                return True
        elif watched is self._list_view and event.type() == QEvent.KeyPress:
            if event.key() in (Qt.Key_Return, Qt.Key_Enter, Qt.Key_Space):
                index = self._list_view.currentIndex()
                if index.isValid():
                    self._on_item_double_clicked(index)
                    return True
            elif event.key() == Qt.Key_Delete:
                index = self._list_view.currentIndex()
                if index.isValid():
                    game = self._model.get_game(index.row())
                    if game:
                        self._confirm_delete(game)
                    return True
        return super().eventFilter(watched, event)

    # ── Slots & Logic ────────────────────────────────────────────────────────

    def attach_projects_service(self, service: Any) -> None:
        """Connect to shared ProjectsService to consume project updates."""
        self._projects_service = service
        if hasattr(service, "_projects_root") and service._projects_root:
            self._projects_root = service._projects_root
        if hasattr(service, "_workspace_dir") and service._workspace_dir:
            self._workspace_dir = service._workspace_dir
        if hasattr(service, "gamesLoaded"):
            service.gamesLoaded.connect(self._on_service_games_loaded)
        if hasattr(service, "gameDeleted"):
            service.gameDeleted.connect(self._on_service_game_deleted)
        if hasattr(service, "operationFailed"):
            service.operationFailed.connect(self._on_service_operation_failed)
        self.refresh_games()

    @Slot(list)
    def _on_service_games_loaded(self, games: List[GameSummary]) -> None:
        self._loaded_games = games
        self._on_games_loaded()

    @Slot(str)
    def _on_service_game_deleted(self, project_name: str) -> None:
        pdir = resolve_project_dir(project_name, self._projects_root)
        self._delete_finished.emit(True, project_name, "", pdir or Path())

    @Slot(str)
    def _on_service_operation_failed(self, error_msg: str) -> None:
        self._delete_finished.emit(False, "", error_msg, Path())

    def set_projects_root(self, root: Optional[Union[str, Path]]) -> None:
        """Update candidate projects root and refresh view."""
        resolved = Path(root).resolve() if (root and str(root).strip()) else None
        if resolved is not None:
            from ...core.projects import is_gameforge_project
            self._projects_root = resolved.parent if is_gameforge_project(resolved) else resolved
        else:
            self._projects_root = None

        if hasattr(self, "_projects_service") and self._projects_service is not None:
            if hasattr(self._projects_service, "_projects_root"):
                self._projects_service._projects_root = self._projects_root
        self.refresh_games()

    @Slot()
    def refresh_games(self) -> None:
        """Fetch games asynchronously via ProjectsService or JobManager with stale rejection."""
        self._refresh_seq += 1
        seq = self._refresh_seq
        if hasattr(self, "_delegate"):
            self._delegate.clear_cache()

        # Capture currently selected game to preserve selection across refresh
        cur_idx = self._list_view.currentIndex() if hasattr(self, "_list_view") else None
        if cur_idx is not None and cur_idx.isValid():
            cur_game = self._model.get_game(cur_idx.row())
            self._selected_game_name = cur_game.name if cur_game else None

        if hasattr(self, "_projects_service") and self._projects_service is not None:
            if hasattr(self._projects_service, "refresh"):
                self._projects_service.refresh()
                return

        p_root = self._projects_root
        ws_dir = self._workspace_dir

        def work() -> List[GameSummary]:
            return list_games(projects_root=p_root, workspace_dir=ws_dir)

        def done(handle: JobHandle) -> None:
            if seq != self._refresh_seq:
                return
            try:
                import shiboken6
                if not shiboken6.isValid(self):
                    return
            except Exception:
                pass
            if handle.status == "DONE":
                res = handle.result()
                if res is not None:
                    from PySide6.QtCore import QMetaObject, Qt
                    self._loaded_games = res
                    try:
                        QMetaObject.invokeMethod(self, "_on_games_loaded", Qt.QueuedConnection)
                    except Exception:
                        pass
            elif handle.status == "FAILED":
                logger.error("Scan Games for GamesView failed: %s", handle.error)

        handle = self._job_manager.submit(work, name="Scan Games for GamesView")
        handle.add_done_callback(done)

    @Slot()
    def _on_games_loaded(self) -> None:
        games = getattr(self, "_loaded_games", [])
        self._model.set_games(games)

        has_games = self._model.rowCount() > 0
        if hasattr(self, "_lbl_empty"):
            self._lbl_empty.setVisible(not has_games)
        if hasattr(self, "_empty_container"):
            self._empty_container.setVisible(not has_games)
        self._list_view.setVisible(has_games)

        # Restore selection or select first game for instant keyboard navigation
        sel_name = getattr(self, "_selected_game_name", None)
        target_row = 0
        if sel_name:
            for row in range(self._model.rowCount()):
                g = self._model.get_game(row)
                if g and g.name.lower() == sel_name.lower():
                    target_row = row
                    break
        if has_games:
            new_idx = self._model.index(target_row, 0)
            self._list_view.setCurrentIndex(new_idx)
            g = self._model.get_game(target_row)
            if g:
                self._selected_game_name = g.name
                self.gameSelected.emit(g.name)
        else:
            self._selected_game_name = None
            self.gameSelected.emit("")

    @Slot(QModelIndex, QModelIndex)
    def _on_selection_changed(self, current: QModelIndex, previous: Optional[QModelIndex] = None) -> None:
        if current.isValid():
            game = self._model.get_game(current.row())
            if game:
                self._selected_game_name = game.name
                self.gameSelected.emit(game.name)

    @Slot(str)
    def _on_filter_changed(self, text: str) -> None:
        mapping = {
            "All statuses": "all",
            "PASS": "pass",
            "FAIL": "fail",
            "Running": "running",
            "Unbuilt": "unbuilt",
        }
        self._model.set_status_filter(mapping.get(text, "all"))

    @Slot()
    def _on_new_project_clicked(self) -> None:
        from ..dialogs.new_project_dialog import NewProjectDialog
        dlg = NewProjectDialog(self)
        if dlg.exec():
            name, pdir = dlg.get_resolved_project_dir()
            self.newProjectRequested.emit(name, pdir)

    @Slot()
    def _on_open_project_clicked(self) -> None:
        from PySide6.QtWidgets import QFileDialog
        from ...core.settings import get_settings
        start_dir = str(get_settings().projects_root or Path.home() / "Documents" / "GameForge" / "Projects")
        chosen = QFileDialog.getExistingDirectory(self, "Select Existing Project Directory", start_dir)
        if chosen:
            self.openProjectRequested.emit(Path(chosen).resolve())

    @Slot(int)
    def _on_sort_changed(self, index: int) -> None:
        data = self._sort_combo.itemData(index) or "recent"
        self._model.set_sort_mode(str(data))

    @Slot()
    def _toggle_view_mode(self) -> None:
        if self._list_view.viewMode() == QListView.IconMode:
            self._list_view.setViewMode(QListView.ListMode)
            self._btn_mode.setText("List")
            self._btn_mode.setToolTip("View mode: List. Click to switch to Grid.")
        else:
            self._list_view.setViewMode(QListView.IconMode)
            self._btn_mode.setText("Grid")
            self._btn_mode.setToolTip("View mode: Grid. Click to switch to List.")
        self._list_view.update()

    @Slot(QModelIndex)
    def _on_item_double_clicked(self, index: QModelIndex) -> None:
        game = self._model.get_game(index.row())
        if game:
            self.openGameRequested.emit(game.name)

    @Slot(QPoint)
    def _show_context_menu(self, pos: QPoint) -> None:
        index = self._list_view.indexAt(pos)
        if not index.isValid():
            return
        game = self._model.get_game(index.row())
        if not game:
            return

        menu = QMenu(self)
        menu.setObjectName("gamesContextMenu")

        act_open = menu.addAction("Open in Design")
        act_open.triggered.connect(lambda: self.openGameRequested.emit(game.name))

        act_build = menu.addAction("Build")
        act_build.triggered.connect(lambda: self.buildGameRequested.emit(game.name))

        act_play = menu.addAction("Play")
        act_play.setEnabled(game.has_package)
        act_play.triggered.connect(lambda: self.playGameRequested.emit(game.name))

        menu.addSeparator()

        act_explorer = menu.addAction("Show in Explorer")
        act_explorer.triggered.connect(lambda: self._open_in_explorer(game.project_dir))

        menu.addSeparator()

        act_delete = menu.addAction("Delete Game…")
        act_delete.triggered.connect(lambda: self._confirm_delete(game))

        menu.exec(self._list_view.viewport().mapToGlobal(pos))

    def _open_in_explorer(self, folder: Path) -> None:
        if not folder or not Path(folder).is_dir():
            return
        if sys.platform == "win32":
            os.startfile(str(folder))
        else:
            subprocess.Popen(["xdg-open", str(folder)])

    def _confirm_delete(self, game: GameSummary) -> None:
        # Check active editor link first
        try:
            from ...backend.tools.game_tools import GameTools
            for link in GameTools.all_links():
                link_name = getattr(link, "project_name", "")
                if link_name and (
                    link_name == game.name
                    or link_name == game.title
                    or (game.project_dir and link_name == game.project_dir.name)
                ):
                    QMessageBox.warning(
                        self,
                        "Cannot Delete Project",
                        f"Cannot delete project '{game.name}': an active Unreal Editor link is currently open.",
                    )
                    return
        except Exception:
            pass

        dlg = DeleteGameDialog(game, self)
        if dlg.exec() == QDialog.Accepted:
            self.beforeGameDeleted.emit(game.name, game.project_dir)
            self._execute_delete(game.name, game.project_dir)

    def _execute_delete(self, project_name: str, project_dir: Optional[Path] = None) -> None:
        pdir = project_dir or resolve_project_dir(project_name, self._projects_root)

        if hasattr(self, "_projects_service") and self._projects_service is not None:
            if hasattr(self._projects_service, "delete_game"):
                self._projects_service.delete_game(project_name, project_dir=pdir)
                return

        def work() -> bool:
            success = delete_project(project_name, project_dir=pdir)
            if not success:
                raise RuntimeError(f"Could not delete directory for project '{project_name}' at {pdir}.")
            return True

        def done(handle: JobHandle) -> None:
            try:
                import shiboken6
                if not shiboken6.isValid(self):
                    return
            except Exception:
                pass
            try:
                if handle.status == "DONE" and handle.result():
                    self._delete_finished.emit(True, project_name, "", pdir or Path())
                else:
                    err_msg = str(handle.error) if handle.error else f"Failed to delete project '{project_name}'."
                    self._delete_finished.emit(False, project_name, err_msg, pdir or Path())
            except Exception:
                pass

        handle = self._job_manager.submit(work, name=f"Delete Project {project_name}")
        handle.add_done_callback(done)

    @Slot(bool, str, str, Path)
    def _on_delete_finished(self, success: bool, project_name: str, error_msg: str, project_dir: Path) -> None:
        if success:
            if self._selected_game_name and self._selected_game_name.lower() == project_name.lower():
                self._selected_game_name = None
            logger.info("Project '%s' at %s successfully deleted.", project_name, project_dir)
            self.gameDeleted.emit(project_name, project_dir)
        else:
            logger.error("Failed to delete project '%s': %s", project_name, error_msg)
            QMessageBox.warning(
                self,
                "Delete Failed",
                f"Failed to delete project '{project_name}':\n\n{error_msg}\n\nPlease check file permissions or close any open applications accessing this folder.",
            )
        self.refresh_games()
