"""CodeView: Developer mode hosting code editor, explorer, unreal, diff, and terminal docks (WI-4.3)."""

from __future__ import annotations

import logging
from pathlib import Path
import re
from typing import List, Optional, Tuple

from PySide6.QtCore import QSettings, Qt, Slot
from PySide6.QtGui import QColor, QFont, QSyntaxHighlighter, QTextCharFormat, QTextCursor
from PySide6.QtWidgets import (
    QApplication,
    QDockWidget,
    QFrame,
    QHBoxLayout,
    QLabel,
    QMainWindow,
    QPlainTextEdit,
    QPushButton,
    QTabWidget,
    QVBoxLayout,
    QWidget,
)

from ..panels.asset_panel import AssetPanel
from ..panels.design_panel import DesignPanel
from ..panels.diff_panel import DiffPanel
from ..panels.explorer_panel import ExplorerPanel
from ..panels.mission_panel import MissionPanel
from ..panels.plan_panel import PlanPanel
from ..panels.terminal_panel import TerminalPanel
from ..panels.unreal_panel import UnrealPanel
from ..services.tool_service import ToolService
from ..styles import tokens

logger = logging.getLogger(__name__)


class CodeHighlighter(QSyntaxHighlighter):
    """Syntax highlighter for C++, Python, JSON, and shaders."""

    def __init__(self, parent=None, language: str = "cpp") -> None:
        super().__init__(parent)
        self._rules: List[Tuple[re.Pattern, QTextCharFormat]] = []
        self._setup_rules(language)

    def _setup_rules(self, language: str) -> None:
        self._rules.clear()

        # Keyword format
        kw_format = QTextCharFormat()
        kw_format.setForeground(QColor(tokens.ACCENT_PRIMARY))
        kw_format.setFontWeight(QFont.Bold)

        # Type format
        type_format = QTextCharFormat()
        type_format.setForeground(QColor(tokens.ACCENT_HOVER))
        type_format.setFontWeight(QFont.DemiBold)

        # String format
        str_format = QTextCharFormat()
        str_format.setForeground(QColor(tokens.ACCENT_SUCCESS))

        # Comment format
        comment_format = QTextCharFormat()
        comment_format.setForeground(QColor(tokens.TEXT_MUTED))
        comment_format.setFontItalic(True)

        # Number format
        num_format = QTextCharFormat()
        num_format.setForeground(QColor(tokens.ACCENT_WARNING))

        # Preprocessor format
        pre_format = QTextCharFormat()
        pre_format.setForeground(QColor(tokens.ACCENT_WARNING))

        # Unreal macros
        ue_format = QTextCharFormat()
        ue_format.setForeground(QColor(tokens.ACCENT_PRIMARY))
        ue_format.setFontWeight(QFont.Bold)

        cpp_keywords = [
            r"\bclass\b", r"\bconst\b", r"\benum\b", r"\bexplicit\b", r"\bfriend\b",
            r"\binline\b", r"\bnamespace\b", r"\boperator\b", r"\bprivate\b",
            r"\bprotected\b", r"\bpublic\b", r"\bsignals\b", r"\bslots\b",
            r"\bstatic\b", r"\bstruct\b", r"\btemplate\b", r"\btypedef\b",
            r"\btypename\b", r"\bunion\b", r"\bvirtual\b", r"\bvolatile\b",
            r"\breturn\b", r"\bif\b", r"\belse\b", r"\bfor\b", r"\bwhile\b",
            r"\bdo\b", r"\bswitch\b", r"\bcase\b", r"\bdefault\b", r"\bbreak\b",
            r"\bcontinue\b", r"\bgoto\b", r"\btry\b", r"\bcatch\b", r"\bthrow\b",
            r"\bnew\b", r"\bdelete\b", r"\bauto\b", r"\bnullptr\b", r"\btrue\b", r"\bfalse\b",
        ]
        py_keywords = [
            r"\band\b", r"\bas\b", r"\bassert\b", r"\basync\b", r"\bawait\b",
            r"\bbreak\b", r"\bclass\b", r"\bcontinue\b", r"\bdef\b", r"\bdel\b",
            r"\belif\b", r"\belse\b", r"\bexcept\b", r"\bfinally\b", r"\bfor\b",
            r"\bfrom\b", r"\bglobal\b", r"\bif\b", r"\bimport\b", r"\bin\b",
            r"\bis\b", r"\blambda\b", r"\bnonlocal\b", r"\bnot\b", r"\bor\b",
            r"\bpass\b", r"\braise\b", r"\breturn\b", r"\btry\b", r"\bwhile\b",
            r"\bwith\b", r"\byield\b", r"\bTrue\b", r"\bFalse\b", r"\bNone\b", r"\bself\b",
        ]

        if language in ("py", "python"):
            for kw in py_keywords:
                self._rules.append((re.compile(kw), kw_format))
            self._rules.append((re.compile(r"#[^\n]*"), comment_format))
            self._rules.append((re.compile(r'"[^"\\]*(\\.[^"\\]*)*"'), str_format))
            self._rules.append((re.compile(r"'[^'\\]*(\\.[^'\\]*)*'"), str_format))
        else:
            for kw in cpp_keywords:
                self._rules.append((re.compile(kw), kw_format))
            for m in (r"\bUPROPERTY\b", r"\bUFUNCTION\b", r"\bUCLASS\b", r"\bUSTRUCT\b", r"\bUENUM\b", r"\bGENERATED_BODY\b"):
                self._rules.append((re.compile(m), ue_format))
            self._rules.append((re.compile(r"#[a-zA-Z_]+[^\n]*"), pre_format))
            for t in (r"\bint\b", r"\bfloat\b", r"\bdouble\b", r"\bbool\b", r"\bchar\b", r"\bvoid\b", r"\bFString\b", r"\bFName\b", r"\bFVector\b", r"\bFRotator\b", r"\bAActor\b", r"\bAPawn\b", r"\bACharacter\b", r"\bUObject\b"):
                self._rules.append((re.compile(t), type_format))
            self._rules.append((re.compile(r"//[^\n]*"), comment_format))
            self._rules.append((re.compile(r'"[^"\\]*(\\.[^"\\]*)*"'), str_format))

        self._rules.append((re.compile(r"\b[0-9]+(?:\.[0-9]+)?f?\b"), num_format))

    def highlightBlock(self, text: str) -> None:
        for pattern, fmt in self._rules:
            for match in pattern.finditer(text):
                self.setFormat(match.start(), match.end() - match.start(), fmt)


class CodeEditor(QWidget):
    """Central document editor for viewing code with syntax highlighting and read-only protection."""

    def __init__(self, parent: Optional[QWidget] = None) -> None:
        super().__init__(parent)
        self.setObjectName("codeEditorContainer")
        self._current_file: Optional[Path] = None

        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)

        # Header bar
        header = QFrame(self)
        header.setObjectName("codeEditorHeader")
        header.setStyleSheet(
            f"background-color: {tokens.BG_PANEL}; border-bottom: 1px solid {tokens.BORDER};"
        )
        hdr_layout = QHBoxLayout(header)
        hdr_layout.setContentsMargins(8, 4, 8, 4)
        hdr_layout.setSpacing(8)

        self._lbl_filename = QLabel("No file open", header)
        self._lbl_filename.setObjectName("lblCodeFilename")
        self._lbl_filename.setStyleSheet(f"color: {tokens.TEXT_PRIMARY}; font-weight: 600; font-size: 12px;")
        hdr_layout.addWidget(self._lbl_filename)

        self._lbl_status = QLabel("", header)
        self._lbl_status.setStyleSheet(f"color: {tokens.TEXT_MUTED}; font-size: 11px;")
        hdr_layout.addWidget(self._lbl_status)

        hdr_layout.addStretch(1)

        self._btn_copy_path = QPushButton("Copy Path", header)
        self._btn_copy_path.setObjectName("btnCodeCopyPath")
        self._btn_copy_path.setCursor(Qt.PointingHandCursor)
        self._btn_copy_path.setStyleSheet(
            f"QPushButton {{"
            f"  background-color: {tokens.BG_SURFACE}; color: {tokens.TEXT_SECONDARY};"
            f"  border: 1px solid {tokens.BORDER}; border-radius: 4px; padding: 2px 8px; font-size: 11px;"
            f"}}"
            f"QPushButton:hover {{ background-color: {tokens.BG_HOVER}; color: {tokens.TEXT_PRIMARY}; }}"
        )
        self._btn_copy_path.clicked.connect(self._copy_path)
        hdr_layout.addWidget(self._btn_copy_path)

        layout.addWidget(header)

        # Editor
        self._edit = QPlainTextEdit(self)
        self._edit.setObjectName("codePlainTextEdit")
        self._edit.setReadOnly(True)
        self._edit.setStyleSheet(
            f"QPlainTextEdit#{self._edit.objectName()} {{"
            f"  background-color: {tokens.BG_ROOT};"
            f"  color: {tokens.TEXT_PRIMARY};"
            f"  border: none;"
            f"  font-family: 'Cascadia Code', 'Consolas', monospace;"
            f"  font-size: 12px;"
            f"  selection-background-color: {tokens.ACCENT_PRIMARY};"
            f"}}"
        )
        layout.addWidget(self._edit, 1)

        self._highlighter: Optional[CodeHighlighter] = None

    def open_file(self, file_path: Path | str, line: int = 1) -> bool:
        p = Path(file_path).resolve()
        if not p.is_file():
            self._lbl_filename.setText(f"File not found: {p.name}")
            self._lbl_status.setText(str(p))
            self._edit.setPlainText(f"Error: File not found at {p}")
            return False

        try:
            sz = p.stat().st_size
            if sz > 5 * 1024 * 1024:
                self._lbl_filename.setText(f"{p.name} (File too large: {sz / (1024*1024):.1f} MB)")
                self._lbl_status.setText(str(p))
                self._edit.setPlainText(f"File size exceeds 5 MB ({sz} bytes). Large binary or data files are not loaded in the code view.")
                return False
            raw_bytes = p.read_bytes()
        except Exception as exc:
            self._lbl_filename.setText(f"Error reading {p.name}")
            self._lbl_status.setText(str(p))
            self._edit.setPlainText(f"Could not read file: {exc}")
            return False

        if b"\0" in raw_bytes[:4096]:
            self._lbl_filename.setText(f"{p.name} (Binary file)")
            self._lbl_status.setText(str(p))
            self._edit.setPlainText("Binary file cannot be displayed in text editor.")
            return False

        try:
            content = raw_bytes.decode("utf-8")
        except UnicodeDecodeError:
            try:
                content = raw_bytes.decode("latin-1")
            except Exception:
                content = raw_bytes.decode("utf-8", errors="replace")

        self._current_file = p
        self._lbl_filename.setText(f"📄 {p.name}")
        self._lbl_status.setText(f"{p.parent}  ·  {len(content.splitlines())} lines (Read-Only)")

        ext = p.suffix.lower()
        lang = "py" if ext == ".py" else ("json" if ext == ".json" else "cpp")
        self._highlighter = CodeHighlighter(self._edit.document(), language=lang)

        self._edit.setPlainText(content)

        if line > 1:
            self.jump_to_line(line)

        return True

    def jump_to_line(self, line_no: int) -> None:
        block = self._edit.document().findBlockByLineNumber(max(0, line_no - 1))
        if block.isValid():
            cursor = self._edit.textCursor()
            cursor.setPosition(block.position())
            self._edit.setTextCursor(cursor)
            self._edit.centerCursor()

    def _copy_path(self) -> None:
        if self._current_file:
            QApplication.clipboard().setText(str(self._current_file))


class CodeView(QMainWindow):
    """Developer view hosting code editor, explorer, unreal, diff, and terminal docks."""

    def __init__(
        self,
        workspace_root: Path,
        tools: ToolService,
        parent: Optional[QWidget] = None,
    ) -> None:
        super().__init__(parent)
        self.setObjectName("studioView_code")
        self.setWindowFlags(Qt.Widget)
        self._workspace = Path(workspace_root).resolve()
        self._tools = tools

        self.setCorner(Qt.BottomLeftCorner, Qt.LeftDockWidgetArea)
        self.setCorner(Qt.BottomRightCorner, Qt.RightDockWidgetArea)
        self.setTabPosition(Qt.AllDockWidgetAreas, QTabWidget.North)

        # Central code editor
        self._editor = CodeEditor(parent=self)
        self.setCentralWidget(self._editor)

        # Panels
        self._explorer = ExplorerPanel(self._tools, self._workspace, parent=self)
        self._mission = MissionPanel(self._workspace, parent=self)
        self._plan_panel = PlanPanel(self._workspace, parent=self)
        self._asset_panel = AssetPanel(self._workspace, parent=self)
        self._design_panel = DesignPanel(self._workspace, parent=self)
        self._unreal_panel = UnrealPanel(self._tools, self._workspace, parent=self)
        self._diff_panel = DiffPanel(self._tools, parent=self)
        self._terminal = TerminalPanel(self._workspace, parent=self)

        # Wire file selection from explorer directly into the code editor
        self._explorer.file_selected.connect(self.open_file)

        # Docks
        self._dock_explorer = self._create_dock("Explorer", "dock_explorer", self._explorer, Qt.LeftDockWidgetArea)
        self._dock_unreal = self._create_dock("Unreal Engine", "dock_unreal", self._unreal_panel, Qt.RightDockWidgetArea)
        self._dock_diff = self._create_dock("Diff Review", "dock_diff", self._diff_panel, Qt.RightDockWidgetArea)
        self._dock_terminal = self._create_dock("Terminal", "dock_terminal", self._terminal, Qt.BottomDockWidgetArea)

        self._dock_explorer.setMinimumWidth(200)
        self._dock_unreal.setMinimumWidth(280)
        self._dock_terminal.setMinimumHeight(120)

        self.tabifyDockWidget(self._dock_unreal, self._dock_diff)
        self._dock_unreal.raise_()
        self._default_dock_layout = self.saveState()

    def _create_dock(self, title: str, obj_name: str, widget: QWidget, area: Qt.DockWidgetArea) -> QDockWidget:
        dock = QDockWidget(title, self)
        dock.setObjectName(obj_name)
        dock.setWidget(widget)
        dock.setFeatures(QDockWidget.DockWidgetMovable | QDockWidget.DockWidgetClosable | QDockWidget.DockWidgetFloatable)
        self.addDockWidget(area, dock)
        return dock

    @Slot(str)
    def open_file(self, file_path: Path | str, line: int = 1) -> bool:
        """Open a file in the code editor with syntax highlighting and jump to line."""
        return self._editor.open_file(file_path, line=line)

    def set_workspace(self, workspace_root: Path | str) -> None:
        """Switch workspace across child docks and panels."""
        self._workspace = Path(workspace_root).resolve()
        if hasattr(self, "_explorer"):
            self._explorer.set_workspace(self._workspace, self._tools)
        if hasattr(self, "_terminal"):
            self._terminal.set_workspace(self._workspace)
        if hasattr(self, "_unreal_panel"):
            self._unreal_panel.set_workspace(self._tools, self._workspace)

    def save_dock_state(self, settings: QSettings) -> None:
        """Persist dock positions and sizes."""
        settings.setValue("studio/code_view_layout", self.saveState())

    def restore_dock_state(self, settings: QSettings) -> bool:
        """Restore dock positions and sizes if saved."""
        saved = settings.value("studio/code_view_layout")
        if saved:
            return self.restoreState(saved)
        return False

    def reset_dock_layout(self) -> None:
        """Reset docks back to default layout."""
        if hasattr(self, "_default_dock_layout"):
            self.restoreState(self._default_dock_layout)
