"""Mission Control: live resources, approvals inbox and created games.

Efficiency (Blueprint v2 §8.1): sampling runs on a 2 s timer ONLY while the panel is visible,
uses cheap psutil calls and a 1 s Ollama /api/ps probe off the UI thread, and the games list is
rescanned only on demand or after a build finishes.
"""

from __future__ import annotations

import json
import os
import shutil
import urllib.request
from pathlib import Path
from typing import Dict, List, Optional

from PySide6.QtCore import QObject, QRunnable, QThreadPool, QTimer, Qt, Signal, Slot
from PySide6.QtWidgets import (QHBoxLayout, QLabel, QListWidget, QListWidgetItem, QProgressBar, QPushButton,
                               QTabWidget, QVBoxLayout, QWidget)


class _ProbeSignals(QObject):
    done = Signal(dict)


class _OllamaProbe(QRunnable):
    def __init__(self) -> None:
        super().__init__()
        self.signals = _ProbeSignals()

    def run(self) -> None:
        out: Dict = {"online": False, "models": []}
        try:
            with urllib.request.urlopen("http://127.0.0.1:11434/api/ps", timeout=1) as r:
                data = json.loads(r.read().decode("utf-8"))
            out = {"online": True, "models": [{"name": m.get("name"), "vram_mb": round((m.get("size_vram") or 0) / 2**20)}
                                              for m in data.get("models", [])]}
        except Exception:
            pass
        self.signals.done.emit(out)


def _bar(label: str) -> tuple:
    row = QHBoxLayout()
    lbl = QLabel(label)
    lbl.setMinimumWidth(70)
    bar = QProgressBar()
    bar.setRange(0, 100)
    bar.setTextVisible(True)
    bar.setFixedHeight(16)
    row.addWidget(lbl)
    row.addWidget(bar, 1)
    return row, bar


class MissionPanel(QWidget):
    open_approval = Signal(dict)   # ask the chat panel to show/approve a pending action
    play_requested = Signal(str)

    def __init__(self, workspace_root: Path, parent: Optional[QWidget] = None) -> None:
        super().__init__(parent)
        self._workspace = Path(workspace_root)
        self._pool = QThreadPool.globalInstance()
        self._probe_running = False
        self._proc = None
        try:
            import psutil
            self._psutil = psutil
            self._proc = psutil.Process()
            self._proc.cpu_percent(None)
            psutil.cpu_percent(None)
        except ImportError:
            self._psutil = None

        lay = QVBoxLayout(self)
        lay.setContentsMargins(6, 6, 6, 6)
        self._tabs = QTabWidget()
        lay.addWidget(self._tabs)

        # Resources
        res = QWidget()
        rl = QVBoxLayout(res)
        r1, self._cpu = _bar("System CPU")
        r2, self._ram = _bar("System RAM")
        r3, self._disk = _bar("Disk")
        for r in (r1, r2, r3):
            rl.addLayout(r)
        self._ide_lbl = QLabel("IDE: –")
        self._models_lbl = QLabel("Models: –")
        self._models_lbl.setWordWrap(True)
        self._procs_lbl = QLabel("Engine processes: –")
        self._procs_lbl.setWordWrap(True)
        for w in (self._ide_lbl, self._models_lbl, self._procs_lbl):
            rl.addWidget(w)
        self._hosted_lbl = QLabel("Hosted models: –")
        self._hosted_lbl.setWordWrap(True)
        rl.addWidget(self._hosted_lbl)
        self._meta_lbl = QLabel("Workspace metadata: –")
        self._btn_cleanup = QPushButton("Clean up workspace metadata…")
        self._btn_cleanup.clicked.connect(self._on_cleanup)
        rl.addWidget(self._meta_lbl)
        rl.addWidget(self._btn_cleanup)
        rl.addStretch(1)
        self._tabs.addTab(res, "Resources")

        # Approvals inbox
        appr = QWidget()
        al = QVBoxLayout(appr)
        self._approvals = QListWidget()
        self._approvals.itemDoubleClicked.connect(self._on_approval_activated)
        al.addWidget(QLabel("Pending approvals (double-click to review in chat):"))
        al.addWidget(self._approvals, 1)
        self._tabs.addTab(appr, "Approvals")

        # Games
        games = QWidget()
        gl = QVBoxLayout(games)
        self._games = QListWidget()
        from PySide6.QtCore import QSize
        self._games.setIconSize(QSize(128, 72))
        gl.addWidget(self._games, 1)
        row = QHBoxLayout()
        self._btn_play = QPushButton("▶ Play")
        self._btn_report = QPushButton("Report")
        self._btn_folder = QPushButton("Folder")
        self._btn_refresh = QPushButton("Refresh")
        for b in (self._btn_play, self._btn_report, self._btn_folder, self._btn_refresh):
            row.addWidget(b)
        gl.addLayout(row)
        self._btn_play.clicked.connect(self._on_play)
        self._btn_report.clicked.connect(lambda: self._open_selected("report"))
        self._btn_folder.clicked.connect(lambda: self._open_selected("folder"))
        self._btn_refresh.clicked.connect(self.refresh_lists)
        self._tabs.addTab(games, "Games")

        # Execution Plan (DAG multi-step planner)
        from .plan_panel import PlanPanel
        self._plan_panel = PlanPanel(self._workspace)
        self._tabs.addTab(self._plan_panel, "Execution Plan")

        self._timer = QTimer(self)
        self._timer.setInterval(2000)
        self._timer.timeout.connect(self._sample)

    # ── visibility-gated sampling ───────────────────────────────────────────
    def showEvent(self, event) -> None:  # noqa: N802
        super().showEvent(event)
        self.refresh_lists()
        self._sample()
        self._timer.start()

    def hideEvent(self, event) -> None:  # noqa: N802
        super().hideEvent(event)
        self._timer.stop()

    def set_workspace(self, workspace_root: Path) -> None:
        self._workspace = Path(workspace_root)
        if hasattr(self, "_plan_panel"):
            self._plan_panel._workspace = self._workspace
        self.refresh_lists()

    @Slot()
    def _sample(self) -> None:
        if self._psutil:
            ps = self._psutil
            self._cpu.setValue(int(ps.cpu_percent(None)))
            vm = ps.virtual_memory()
            self._ram.setValue(int(vm.percent))
            self._ram.setFormat(f"{vm.used / 2**30:.1f} / {vm.total / 2**30:.0f} GB")
            try:
                mem = self._proc.memory_full_info()
                private = getattr(mem, "private", mem.uss)
                self._ide_lbl.setText(f"IDE: {private / 2**20:.0f} MB private, {self._proc.cpu_percent(None):.1f}% CPU")
            except Exception:
                pass
            names = {}
            for p in ps.process_iter(["name"]):
                n = (p.info.get("name") or "")
                if n.startswith(("UnrealEditor", "UnrealBuildTool", "AutomationTool", "ShaderCompileWorker")) or \
                        n.endswith("-Win64-Shipping.exe"):
                    names[n] = names.get(n, 0) + 1
            self._procs_lbl.setText("Engine processes: " + (", ".join(f"{k}×{v}" for k, v in names.items()) or "none"))
        try:
            du = shutil.disk_usage(str(self._workspace.anchor or self._workspace))
            self._disk.setValue(int(du.used / du.total * 100))
            self._disk.setFormat(f"{du.free / 2**30:.0f} GB free on {self._workspace.anchor}")
        except OSError:
            pass
        if not self._probe_running:
            self._probe_running = True
            probe = _OllamaProbe()
            probe.signals.done.connect(self._on_probe)
            self._pool.start(probe)

    @Slot(dict)
    def _on_probe(self, data: dict) -> None:
        self._probe_running = False
        if not data.get("online"):
            self._models_lbl.setText("Models: Ollama offline")
        elif not data["models"]:
            self._models_lbl.setText("Models: none loaded (VRAM free)")
        else:
            self._models_lbl.setText("Models loaded: " + ", ".join(f"{m['name']} ({m['vram_mb']} MB VRAM)"
                                                                   for m in data["models"]))

    # ── lists ───────────────────────────────────────────────────────────────
    def _projects_root(self) -> Path:
        try:
            from ...backend.tools.game_tools import GameTools
            return GameTools(self._workspace).projects_root
        except Exception:
            return self._workspace / "Games"

    def _refresh_hosted(self) -> None:
        """Tier status: which hosted providers this workspace may use, and today's spend."""
        try:
            from ...backend.providers.hosted import EgressPolicy, SpendLedger, load_profiles
            profiles = load_profiles()
            allowed = set(EgressPolicy(self._workspace).allowed())
            ledger = SpendLedger(self._workspace)
            parts = []
            for pid, prof in profiles.items():
                if prof.enabled and pid in allowed:
                    parts.append(f"{pid}: ${ledger.spent(pid):.4f} today (cap ${prof.per_day_usd_cap:.2f})")
            self._hosted_lbl.setText("Hosted models: " + ("; ".join(parts) if parts else
                                     "none active for this workspace — local tier in use (File → Hosted Models…)"))
        except Exception as exc:
            self._hosted_lbl.setText(f"Hosted models: unavailable ({exc})")

    @Slot()
    def refresh_lists(self) -> None:
        self._refresh_hosted()
        self._approvals.clear()
        try:
            from ...backend.tools.game_tools import ApprovalStore
            for rec in ApprovalStore(self._workspace).list_pending():
                item = QListWidgetItem(f"{rec['tool'].replace('_', ' ')} — {rec.get('summary', '')[:90]}")
                item.setData(Qt.UserRole, rec)
                self._approvals.addItem(item)
        except Exception:
            pass
        if self._approvals.count() == 0:
            self._approvals.addItem("No pending approvals.")
        self._tabs.setTabText(1, f"Approvals ({sum(1 for i in range(self._approvals.count()) if self._approvals.item(i).data(Qt.UserRole))})")

        self._games.clear()
        root = self._projects_root()
        entries: List[tuple] = []
        if root.is_dir():
            for proj in root.iterdir():
                report = proj / "Saved" / "GameForge" / "pipeline_report.json"
                if not report.is_file():
                    continue
                try:
                    data = json.loads(report.read_text(encoding="utf-8"))
                except (OSError, json.JSONDecodeError):
                    continue
                exe = proj / "Packaged" / "Windows" / f"{proj.name}.exe"
                entries.append((report.stat().st_mtime, proj, data, exe))
        for _, proj, data, exe in sorted(entries, reverse=True):
            mark = "✔" if data.get("ok") else "✖"
            kind = "free-form" if "author" in data else data.get("recipe", "recipe")
            item = QListWidgetItem(f"{mark} {proj.name}  ·  {kind}" + ("" if data.get("ok") else f"  (failed: {data.get('failed_stage')})"))
            shot = proj / "Saved" / "GameForge" / "packaged_gameplay.png"
            if shot.is_file():
                from PySide6.QtGui import QIcon, QPixmap
                pm = QPixmap(str(shot))
                if not pm.isNull():
                    item.setIcon(QIcon(pm.scaled(128, 72, Qt.KeepAspectRatio, Qt.SmoothTransformation)))
            q = next((st for st in data.get("stages", []) if st.get("stage") == "quality_review"), None)
            if q and q.get("data", {}).get("final_verdict") is not None:
                verdict = "reviewer satisfied" if q["data"]["final_verdict"] else "reviewer flags issues: " + "; ".join(q.get("errors", []))[:300]
                item.setText(item.text() + ("  ·  ✓ review" if q["data"]["final_verdict"] else "  ·  ⚠ review"))
                item.setToolTip(verdict)
            item.setData(Qt.UserRole, {"dir": str(proj), "exe": str(exe) if exe.exists() and data.get("ok") else "",
                                       "report": str(proj / "Saved" / "GameForge" / "pipeline_report.md")})
            self._games.addItem(item)
        if self._games.count() == 0:
            self._games.addItem(f"No games yet in {root}")
        if hasattr(self, "_plan_panel"):
            self._plan_panel.refresh_from_disk()

    def _on_cleanup(self) -> None:
        from PySide6.QtWidgets import QMessageBox
        from ...backend import storage_hygiene as sh
        pl = sh.plan(self._workspace)
        self._meta_lbl.setText("Workspace metadata: " + pl.summary())
        if not pl.delete and not pl.rotate:
            QMessageBox.information(self, "Clean up", "Nothing to clean: " + pl.summary())
            return
        preview = "\n".join(Path(p).name for p in pl.delete[:15]) + ("\n…" if len(pl.delete) > 15 else "")
        if QMessageBox.question(self, "Clean up workspace metadata",
                                pl.summary() + "\n\nOldest items first (sessions, pending approvals and the spend "
                                "ledger are never removed):\n" + preview) == QMessageBox.Yes:
            sh.apply(self._workspace, pl)
            self._meta_lbl.setText("Workspace metadata: " + sh.plan(self._workspace).summary())

    def _on_approval_activated(self, item: QListWidgetItem) -> None:
        rec = item.data(Qt.UserRole)
        if rec:
            self.open_approval.emit(rec)

    def _selected_game(self) -> Optional[Dict]:
        item = self._games.currentItem()
        return item.data(Qt.UserRole) if item else None

    def _on_play(self) -> None:
        g = self._selected_game()
        if g and g.get("exe"):
            self.play_requested.emit(g["exe"])

    def _open_selected(self, what: str) -> None:
        g = self._selected_game()
        if not g:
            return
        path = g["report"] if what == "report" else g["dir"]
        if Path(path).exists():
            os.startfile(path)  # noqa: S606 - opens a GameForge-created file or folder
