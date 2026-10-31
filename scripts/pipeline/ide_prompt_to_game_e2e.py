"""End-to-end acceptance test of the real GameForge IDE window:

  type "create a tic tac toe game in unreal engine" -> Send -> plan + approval card
  -> click "Approve and build" -> live stage checklist -> result card with Play button.

Writes window captures and a JSON verdict to <workspace>/.gameforge/e2e/.

    python scripts/pipeline/ide_prompt_to_game_e2e.py --workspace E:\\GameForge\\ide_e2e_ws [--prompt "..."]
"""

import argparse
import json
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--workspace", required=True)
    ap.add_argument("--prompt", default="create a tic tac toe game in unreal engine")
    ap.add_argument("--projects-root", default=r"E:\GameForge\projects\ide_e2e")
    ap.add_argument("--timeout", type=float, default=3600)
    a = ap.parse_args()

    ws = Path(a.workspace)
    (ws / ".gameforge").mkdir(parents=True, exist_ok=True)
    (ws / ".gameforge" / "settings.json").write_text(json.dumps({"projects_root": a.projects_root}), encoding="utf-8")
    out = ws / ".gameforge" / "e2e"
    out.mkdir(parents=True, exist_ok=True)

    from PySide6.QtCore import Qt
    from PySide6.QtWidgets import QApplication, QPushButton
    from src.gameforge_ide.desktop.main_window import MainWindow
    from src.gameforge_ide.desktop.panels.approval_card import ApprovalCard

    app = QApplication.instance() or QApplication(sys.argv)
    win = MainWindow(ws)
    win.resize(1600, 1000)
    win.show()
    verdict = {"prompt": a.prompt, "steps": []}

    def pump(seconds: float, until=None) -> bool:
        end = time.monotonic() + seconds
        while time.monotonic() < end:
            app.processEvents()
            if until and until():
                return True
            time.sleep(0.05)
        return bool(until and until())

    def shot(name: str) -> str:
        path = out / f"{name}.png"
        win.grab().save(str(path))
        return str(path)

    pump(2.0)
    chat = win._chat_panel
    chat._input.setPlainText(a.prompt)
    chat._on_send()
    got_card = pump(120, lambda: any(isinstance(w, ApprovalCard) for w in chat.findChildren(ApprovalCard)))
    verdict["steps"].append({"step": "approval_card_shown", "ok": got_card, "shot": shot("1_plan_and_approval")})
    if not got_card:
        verdict["ok"] = False
        (out / "verdict.json").write_text(json.dumps(verdict, indent=1), encoding="utf-8")
        return 1

    card = chat.findChildren(ApprovalCard)[-1]
    approve = card.findChild(QPushButton, "approvalApprove")
    approve.click()
    started = time.monotonic()
    pump(20)
    verdict["steps"].append({"step": "running", "ok": True, "shot": shot("2_running")})
    play = card.findChild(QPushButton, "approvalPlay")
    finished = pump(a.timeout, lambda: card._result.isVisible() and "Done" in card._result.text()
                    or "Not complete" in card._result.text())
    pump(1.0)
    ok = finished and play.isVisible() and "Done" in card._result.text()
    verdict["steps"].append({"step": "finished", "ok": ok, "elapsed_s": round(time.monotonic() - started, 1),
                             "result_text": card._result.text(), "exe": card._exe,
                             "shot": shot("3_result")})
    verdict["ok"] = ok
    (out / "verdict.json").write_text(json.dumps(verdict, indent=1), encoding="utf-8")
    print(json.dumps(verdict, indent=1))
    win.confirm_on_close = False  # automation: skip the "Are you sure?" dialog
    win.close()
    pump(1.0)
    return 0 if ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
