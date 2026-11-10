"""End-to-end acceptance test of the real GameForge IDE window:

  type prompt -> Send -> plan + approval card
  -> click "Approve and build" -> live stage checklist -> result card with Play button.

Writes window captures and a JSON verdict to <workspace>/.gameforge/e2e/.

    python scripts/pipeline/ide_prompt_to_game_e2e.py --workspace E:\\GameForge\\ide_e2e_ws [--prompt "..."]
"""
from __future__ import annotations

import argparse
import json
import os
from pathlib import Path
import sys
import tempfile
import time
from typing import Any, Callable, Dict, Optional

REPO_ROOT = Path(__file__).resolve().parents[2]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))


def _write_atomic_json(target_path: Path, data: Any) -> None:
    """Atomically write JSON data to file using a temporary file and replace."""
    target_path.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.NamedTemporaryFile("w", encoding="utf-8", dir=target_path.parent, delete=False, suffix=".tmp") as tf:
        json.dump(data, tf, indent=2)
        tf_name = tf.name
    os.replace(tf_name, target_path)


def main() -> int:
    ap = argparse.ArgumentParser(description="End-to-end acceptance test of GameForge IDE window")
    ap.add_argument("--workspace", required=True, help="Workspace directory for test project")
    ap.add_argument("--prompt", default="create a tic tac toe game in unreal engine", help="Prompt to execute")
    ap.add_argument("--projects-root", default=r"E:\GameForge\projects\ide_e2e", help="Projects root directory")
    ap.add_argument("--timeout", type=float, default=3600, help="Max execution timeout in seconds")
    ap.add_argument("--offscreen", action="store_true", help="Run Qt in offscreen platform mode")
    a = ap.parse_args()

    if a.offscreen:
        os.environ["QT_QPA_PLATFORM"] = "offscreen"

    ws = Path(a.workspace).resolve()
    (ws / ".gameforge").mkdir(parents=True, exist_ok=True)
    settings_file = ws / ".gameforge" / "settings.json"
    _write_atomic_json(settings_file, {"projects_root": a.projects_root})

    out = ws / ".gameforge" / "e2e"
    out.mkdir(parents=True, exist_ok=True)

    from PySide6.QtWidgets import QApplication, QPushButton
    from src.gameforge_ide.desktop.main_window import MainWindow
    from src.gameforge_ide.desktop.panels.approval_card import ApprovalCard

    app = QApplication.instance() or QApplication(sys.argv)
    win = MainWindow(ws)
    win.resize(1600, 1000)
    win.show()

    iso_timestamp = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())
    verdict: Dict[str, Any] = {
        "timestamp": iso_timestamp,
        "prompt": a.prompt,
        "workspace": str(ws).replace("\\", "/"),
        "steps": [],
        "ok": False,
    }

    def pump(seconds: float, until: Optional[Callable[[], bool]] = None) -> bool:
        end = time.monotonic() + seconds
        while time.monotonic() < end:
            app.processEvents()
            if until and until():
                return True
            time.sleep(0.05)
        return bool(until and until())

    def shot(name: str) -> str:
        path = out / f"{name}.png"
        try:
            pix = win.grab()
            if not pix.isNull():
                pix.save(str(path))
                return str(path)
        except Exception as exc:
            print(f"Warning: screenshot capture failed for {name}: {exc}")
        return ""

    try:
        pump(2.0)
        chat = win._chat_panel
        chat._input.setPlainText(a.prompt)
        chat._on_send()

        got_card = pump(120, lambda: any(isinstance(w, ApprovalCard) for w in chat.findChildren(ApprovalCard)))
        verdict["steps"].append({"step": "approval_card_shown", "ok": got_card, "shot": shot("1_plan_and_approval")})
        if not got_card:
            verdict["ok"] = False
            _write_atomic_json(out / "verdict.json", verdict)
            return 1

        cards = chat.findChildren(ApprovalCard)
        card = cards[-1]
        approve = card.findChild(QPushButton, "approvalApprove") or getattr(card, "_btn_approve", None)
        if approve is None:
            verdict["steps"].append({"step": "approve_button_found", "ok": False, "error": "approvalApprove button not found"})
            verdict["ok"] = False
            _write_atomic_json(out / "verdict.json", verdict)
            return 1

        approve.click()
        started = time.monotonic()
        pump(20.0)
        verdict["steps"].append({"step": "running", "ok": True, "shot": shot("2_running")})

        play = card.findChild(QPushButton, "approvalPlay") or getattr(card, "_btn_play", None)
        finished = pump(
            a.timeout,
            lambda: bool(
                getattr(card, "_result", None)
                and card._result.isVisible()
                and ("Done" in card._result.text() or "Not complete" in card._result.text())
            ),
        )
        pump(1.0)

        result_text = card._result.text() if getattr(card, "_result", None) else ""
        play_visible = play.isVisible() if play else False
        ok = finished and play_visible and "Done" in result_text

        verdict["steps"].append({
            "step": "finished",
            "ok": ok,
            "elapsed_s": round(time.monotonic() - started, 1),
            "result_text": result_text,
            "exe": getattr(card, "_exe", None),
            "shot": shot("3_result"),
        })
        verdict["ok"] = ok
        _write_atomic_json(out / "verdict.json", verdict)
        print(json.dumps(verdict, indent=2))
        return 0 if ok else 1
    finally:
        win.confirm_on_close = False  # automation: skip the "Are you sure?" dialog
        win.close()
        pump(1.0)


if __name__ == "__main__":
    raise SystemExit(main())
