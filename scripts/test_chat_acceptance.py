"""Comprehensive acceptance test suite for GameForge Chat & Assistant Panel.
Tests the actual UI interaction, live model streaming, history, cancellation, and error states.
"""
from __future__ import annotations

import argparse
import json
import os
from pathlib import Path
import sys
import tempfile
import time
from typing import Any, Dict, List, Optional

# Ensure offscreen Qt platform
os.environ["QT_QPA_PLATFORM"] = "offscreen"
REPO_ROOT = Path(__file__).resolve().parent.parent
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from PySide6.QtCore import QEvent, Qt
from PySide6.QtGui import QKeyEvent
from PySide6.QtWidgets import QApplication

from src.gameforge_ide.desktop.main_window import MainWindow


def run_chat_tests(out_path: Optional[Path] = None) -> int:
    app = QApplication.instance() or QApplication(sys.argv)
    workspace = Path(os.environ.get("GAMEFORGE_WORKSPACE", REPO_ROOT / "scratch" / "chat_test_ws"))
    workspace.mkdir(parents=True, exist_ok=True)
    win = MainWindow(workspace_root=workspace)
    win.show()
    chat = win._chat_panel
    assistant = win._assistant_panel

    results: List[Dict[str, Any]] = []

    def wait_for_agent(timeout_s: float = 60.0) -> bool:
        t0 = time.monotonic()
        while time.monotonic() - t0 < timeout_s:
            app.processEvents()
            time.sleep(0.05)
            if not getattr(win, "_agent", None) or not win._agent.is_busy:
                # Extra small flush
                for _ in range(5):
                    app.processEvents()
                    time.sleep(0.02)
                return True
        return False

    try:
        print("--- 1. Testing Empty Prompt Discard ---")
        chat._input.setPlainText("   ")
        count_before = chat._msg_layout.count()
        chat._btn_send.click()
        app.processEvents()
        count_after = chat._msg_layout.count()
        t1_pass = (count_before == count_after)
        results.append({
            "test": "empty_prompt_discard",
            "passed": t1_pass,
            "detail": f"count_before={count_before}, count_after={count_after}"
        })
        print(f"Result: {'PASS' if t1_pass else 'FAIL'}")

        print("\n--- 2. Testing Conversational Prompt & Live Streaming ---")
        prompt_2 = "Hello! Briefly introduce yourself in one sentence."
        chat._input.setPlainText(prompt_2)
        t0 = time.monotonic()
        chat._btn_send.click()
        app.processEvents()

        # Check status during planning/streaming
        status_seen = []
        for _ in range(200):
            app.processEvents()
            time.sleep(0.05)
            st = chat._status_bar._state_lbl.text() if hasattr(chat._status_bar, "_state_lbl") else ""
            if st and st not in status_seen:
                status_seen.append(st)
            if hasattr(win, "_agent") and not win._agent.is_busy:
                break
        dur = time.monotonic() - t0

        last_bubble = None
        for i in reversed(range(chat._msg_layout.count())):
            item = chat._msg_layout.itemAt(i)
            w = item.widget() if item else None
            if w and type(w).__name__ == "_MessageBubble" and getattr(w, "role", "") == "assistant":
                last_bubble = w
                break
        resp_text = getattr(last_bubble, "_raw_text", "")
        agent_busy = getattr(win, "_agent", None) and win._agent.is_busy
        t2_pass = bool(resp_text and len(resp_text) > 5 and not agent_busy)
        results.append({
            "test": "conversational_streaming",
            "passed": t2_pass,
            "duration_s": round(dur, 2),
            "response_preview": resp_text[:120],
            "statuses_seen": status_seen
        })
        print(f"Result: {'PASS' if t2_pass else 'FAIL'} in {dur:.2f}s: {resp_text[:100]}...")

        print("\n--- 3. Testing Conversation Memory / Multi-Turn ---")
        chat._input.setPlainText("My secret game code is 98765. Please acknowledge.")
        chat._btn_send.click()
        wait_for_agent(45.0)

        chat._input.setPlainText("What was my secret game code? Answer with just the digits.")
        chat._btn_send.click()
        wait_for_agent(45.0)

        last_bubble = None
        for i in reversed(range(chat._msg_layout.count())):
            item = chat._msg_layout.itemAt(i)
            w = item.widget() if item else None
            if w and type(w).__name__ == "_MessageBubble" and getattr(w, "role", "") == "assistant":
                last_bubble = w
                break
        recall_text = getattr(last_bubble, "_raw_text", "")
        t3_pass = "98765" in recall_text
        results.append({
            "test": "conversation_history_recall",
            "passed": t3_pass,
            "response": recall_text[:100]
        })
        print(f"Result: {'PASS' if t3_pass else 'FAIL'} - Recalled text: {recall_text.strip()}")

        print("\n--- 4. Testing Enter Key EventFilter ---")
        chat._input.setPlainText("Respond with 'OK Enter'")
        event = QKeyEvent(QEvent.KeyPress, Qt.Key_Return, Qt.NoModifier)
        chat.eventFilter(chat._input, event)
        wait_for_agent(30.0)
        for i in reversed(range(chat._msg_layout.count())):
            item = chat._msg_layout.itemAt(i)
            w = item.widget() if item else None
            if w and type(w).__name__ == "_MessageBubble" and getattr(w, "role", "") == "assistant":
                last_bubble = w
                break
        enter_text = getattr(last_bubble, "_raw_text", "")
        t4_pass = bool(enter_text)
        results.append({
            "test": "enter_key_eventfilter",
            "passed": t4_pass,
            "response": enter_text[:100]
        })
        print(f"Result: {'PASS' if t4_pass else 'FAIL'}")

        print("\n--- 5. Testing Game Creation Prompt & OpenDesignCard ---")
        game_prompt = "Build an arcade arena shooter called CyberStorm with 3 waves of enemies."
        chat._input.setPlainText(game_prompt)
        chat._btn_send.click()
        wait_for_agent(30.0)

        card_found = None
        for i in range(chat._msg_layout.count()):
            item = chat._msg_layout.itemAt(i)
            w = item.widget() if item else None
            if w and w.objectName() == "openDesignCard":
                card_found = w
                break
        t5_pass = card_found is not None
        results.append({
            "test": "open_design_card_rendering",
            "passed": t5_pass,
            "card_object": type(card_found).__name__ if card_found else None
        })
        print(f"Result: {'PASS' if t5_pass else 'FAIL'} - openDesignCard present: {t5_pass}")

        print("\n--- 6. Testing Cancellation (Stop button) ---")
        chat._input.setPlainText("Write a comprehensive 1500-word design analysis of the platformer genre with historical examples from 1980 to 2026.")
        chat._btn_send.click()
        # Wait until it is streaming
        stopped_ok = False
        for _ in range(100):
            app.processEvents()
            time.sleep(0.05)
            if chat._btn_stop.isEnabled() and getattr(win, "_agent", None) and win._agent.is_busy:
                time.sleep(0.2)
                chat._btn_stop.click()
                stopped_ok = True
                break
        wait_for_agent(10.0)
        # Check if marked as stopped
        for i in reversed(range(chat._msg_layout.count())):
            item = chat._msg_layout.itemAt(i)
            w = item.widget() if item else None
            if w and type(w).__name__ == "_MessageBubble" and getattr(w, "role", "") == "assistant":
                last_bubble = w
                break
        stop_text = getattr(last_bubble, "_raw_text", "")
        agent_busy = getattr(win, "_agent", None) and win._agent.is_busy
        t6_pass = stopped_ok and ("[Stopped by user]" in stop_text or not agent_busy)
        results.append({
            "test": "user_cancellation",
            "passed": t6_pass,
            "stopped_ok": stopped_ok,
            "final_bubble_text": stop_text[-60:]
        })
        print(f"Result: {'PASS' if t6_pass else 'FAIL'} - Stop text: {stop_text[-60:]}")

        print("\n--- 7. Testing Slash Commands (/clear, /new) ---")
        wait_for_agent(15.0)
        chat._input.setPlainText("/clear")
        chat._on_send()
        app.processEvents()
        # After /clear, all bubbles should be removed and start screen shown
        bubbles_count = sum(1 for i in range(chat._msg_layout.count()) if getattr(chat._msg_layout.itemAt(i).widget(), "role", None))
        t7_pass = (bubbles_count == 0)
        results.append({
            "test": "slash_command_clear",
            "passed": t7_pass,
            "remaining_bubbles": bubbles_count
        })
        print(f"Result: {'PASS' if t7_pass else 'FAIL'} - Remaining bubbles: {bubbles_count}")

        print("\n--- 8. Testing Model Switching via Assistant Header ---")
        # Check models list
        models = ["gameforge-qwen3.5-9b:latest", "gameforge-qwen3.5-4b:latest"]
        assistant.set_models(models, current="gameforge-qwen3.5-4b:latest")
        assistant._on_model_changed("gameforge-qwen3.5-4b:latest")
        app.processEvents()
        switched_model = chat._current_model
        t8_pass = (switched_model == "gameforge-qwen3.5-4b:latest")
        results.append({
            "test": "model_switching",
            "passed": t8_pass,
            "switched_to": switched_model
        })
        print(f"Result: {'PASS' if t8_pass else 'FAIL'} - Chat model is now: {switched_model}")

    finally:
        win.confirm_on_close = False
        win.close()
        app.processEvents()

    target_out = out_path or (REPO_ROOT / "reports" / "acceptance_audit" / "chat_interaction_test_results.json")
    target_out.parent.mkdir(parents=True, exist_ok=True)
    tmp_out = target_out.with_suffix(".tmp")
    tmp_out.write_text(json.dumps(results, indent=2), encoding="utf-8")
    tmp_out.replace(target_out)
    print(f"\nAll tests completed. Results saved to {target_out}")

    all_ok = bool(results) and all(r.get("passed") for r in results)
    return 0 if all_ok else 1


def main() -> int:
    parser = argparse.ArgumentParser(description="Run GameForge Chat & Assistant Panel Acceptance Tests")
    parser.add_argument("--out", type=Path, default=None, help="Output JSON results path")
    args = parser.parse_args()
    return run_chat_tests(args.out)


if __name__ == "__main__":
    sys.exit(main())
