"""Packaged Build Real-Input Acceptance Verification.
Drives packaged games with genuine OS-level Win32 keyboard and mouse input delivered to the
live focused window. A step passes only when the game's own log shows the gameplay transition
that input must cause (GF_EVENT markers), so dispatching input alone never counts as a pass.

Zero Mocks. Zero Simulators. Zero Fake Connectors.
"""
from __future__ import annotations

import ctypes
from ctypes import wintypes
import json
import logging
import os
from pathlib import Path
import subprocess
import sys
import time
from typing import Dict, Any, List

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from src.gameforge_ide.unreal.real_input import (
    RealInputSession,
    find_game_window_for_pid,
    find_windows_for_pid,
    find_window_by_title_contains,
    focus_window,
    get_client_rect,
)

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
logger = logging.getLogger("gameforge.verify_packaged")


def capture_window_bmp(hwnd: int, output_png: Path) -> bool:
    """Captures a screenshot of the hwnd client area to a PNG/BMP file."""
    try:
        user32 = ctypes.windll.user32
        gdi32 = ctypes.windll.gdi32

        rect = wintypes.RECT()
        user32.GetClientRect(hwnd, ctypes.byref(rect))
        w = rect.right - rect.left
        h = rect.bottom - rect.top

        if w <= 0 or h <= 0:
            return False

        hdc_screen = user32.GetDC(hwnd)
        hdc_mem = gdi32.CreateCompatibleDC(hdc_screen)
        hbm = gdi32.CreateCompatibleBitmap(hdc_screen, w, h)
        gdi32.SelectObject(hdc_mem, hbm)

        # PrintWindow with PW_RENDERFULLCONTENT (2) for D3D12/DirectComposition content
        user32.PrintWindow(hwnd, hdc_mem, 2)

        # Save bitmap via PIL if available, or write raw BMP header
        try:
            from PIL import Image
            import numpy as np

            # BITMAPINFO
            class BITMAPINFOHEADER(ctypes.Structure):
                _fields_ = [
                    ("biSize", wintypes.DWORD),
                    ("biWidth", wintypes.LONG),
                    ("biHeight", wintypes.LONG),
                    ("biPlanes", wintypes.WORD),
                    ("biBitCount", wintypes.WORD),
                    ("biCompression", wintypes.DWORD),
                    ("biSizeImage", wintypes.DWORD),
                    ("biXPelsPerMeter", wintypes.LONG),
                    ("biYPelsPerMeter", wintypes.LONG),
                    ("biClrUsed", wintypes.DWORD),
                    ("biClrImportant", wintypes.DWORD),
                ]

            bi = BITMAPINFOHEADER()
            bi.biSize = ctypes.sizeof(BITMAPINFOHEADER)
            bi.biWidth = w
            bi.biHeight = -h  # Top-down
            bi.biPlanes = 1
            bi.biBitCount = 32
            bi.biCompression = 0

            buf = ctypes.create_string_buffer(w * h * 4)
            gdi32.GetDIBits(hdc_mem, hbm, 0, h, buf, ctypes.byref(bi), 0)

            arr = np.frombuffer(buf, dtype=np.uint8).reshape((h, w, 4))
            img = Image.fromarray(arr[:, :, [2, 1, 0, 3]])  # BGRA -> RGBA
            output_png.parent.mkdir(parents=True, exist_ok=True)
            img.save(str(output_png))
            logger.info("Captured screenshot to %s (%dx%d)", output_png, w, h)
            return True
        except ImportError:
            logger.warning("PIL or numpy not available for screenshot writing")
            return False
        finally:
            gdi32.DeleteObject(hbm)
            gdi32.DeleteDC(hdc_mem)
            user32.ReleaseDC(hwnd, hdc_screen)
    except Exception as exc:
        logger.error("Failed to capture screenshot: %s", exc)
        return False


class GameLog:
    """Reads GF_EVENT markers the packaged game writes at real gameplay transitions."""

    def __init__(self, path: Path):
        self.path = path
        self.offset = 0

    def new_events(self) -> List[str]:
        if not self.path.is_file():
            return []
        with open(self.path, "r", encoding="utf-8", errors="replace") as f:
            f.seek(self.offset)
            chunk = f.read()
            self.offset = f.tell()
        return [line.split("GF_EVENT ", 1)[1].strip() for line in chunk.splitlines() if "GF_EVENT " in line]


def _expectation_met(expect: str, events: List[str]) -> bool:
    """``expect`` is an event name, optionally with required key=value tokens (e.g. 'card_play ok=1')."""
    name, *tokens = expect.split()
    return any(ev.split()[0] == name and all(tok in ev.split() for tok in tokens) for ev in events)


def test_game(exe_path: Path, game_name: str, test_actions: List[Dict[str, Any]]) -> Dict[str, Any]:
    """Drives the packaged game with real Win32 input; passes only if every action's expected
    gameplay transition appears in the game's own log after that action."""
    logger.info("=" * 60)
    logger.info("TESTING PACKAGED GAME: %s (%s)", game_name, exe_path)
    logger.info("=" * 60)

    if not exe_path.is_file():
        return {"game": game_name, "exe_path": str(exe_path), "ok": False,
                "error": f"Executable not found at {exe_path}"}

    log_path = LOG_DIR / f"{game_name}_{time.strftime('%Y%m%d_%H%M%S')}.log"
    log_path.parent.mkdir(parents=True, exist_ok=True)
    cmd = [str(exe_path), "-windowed", "-ResX=1280", "-ResY=720", f"-abslog={log_path}", "-forcelogflush", "-NoSound"]
    logger.info("Launching: %s", " ".join(cmd))
    proc = subprocess.Popen(cmd)
    game_log = GameLog(log_path)

    session = None
    report: Dict[str, Any] = {"game": game_name, "exe_path": str(exe_path), "pid": proc.pid,
                              "log_path": str(log_path), "steps": [], "ok": False}
    try:
        hwnd = None
        deadline = time.time() + 40.0
        while time.time() < deadline and not hwnd:
            if proc.poll() is not None:
                raise RuntimeError(f"Process exited prematurely with code {proc.returncode}")
            hwnd = find_game_window_for_pid(proc.pid)  # the UnrealWindow viewport, not a console
            if not hwnd:
                time.sleep(1.0)
        if not hwnd:
            raise TimeoutError(f"Game window for PID {proc.pid} ({game_name}) did not appear within 40s")
        logger.info("Found game window: HWND 0x%X", hwnd)
        time.sleep(8.0)  # first frames (PSO warm-up), HUD BeginPlay

        session = RealInputSession(hwnd, target_name=game_name)
        if not session.focus():
            raise RuntimeError(f"Failed to focus window HWND 0x{hwnd:X}")
        time.sleep(1.0)
        report["window_geometry"] = session.get_client_geometry()
        report["startup_events"] = game_log.new_events()

        for act in test_actions:
            kind = act["type"]
            if kind == "tap_key":
                session.tap_key(act["key"], hold_s=act.get("hold_s", 0.08))
            elif kind == "hold_key":
                session.hold_key(act["key"], duration_s=act["duration_s"])
            elif kind == "click_fraction":
                session.move_mouse_fraction(act["rel_x"], act["rel_y"])
                time.sleep(0.15)
                session.click_fraction(act["rel_x"], act["rel_y"], button=act.get("button", "left"))
            elif kind == "move_mouse":
                session.move_mouse_fraction(act["rel_x"], act["rel_y"])
            elif kind == "wait":
                time.sleep(act["duration_s"])
            expect = act.get("expect", [])
            observed: List[str] = []
            settle = time.time() + act.get("settle_s", 2.5)
            while time.time() < settle:
                time.sleep(0.25)
                observed += game_log.new_events()
                if all(_expectation_met(e, observed) for e in expect):
                    break
            met = {e: _expectation_met(e, observed) for e in expect}
            step = {"action": act, "observed_events": observed[:20], "expectations": met, "ok": all(met.values())}
            report["steps"].append(step)
            logger.info("Action %s -> %s %s", {k: v for k, v in act.items() if k != "expect"},
                        "OK" if step["ok"] else "MISSING", met)

        shot_path = ROOT / "reports" / f"packaged_{game_name}_real_input.png"
        report["screenshot_path"] = str(shot_path) if capture_window_bmp(hwnd, shot_path) else None
        report["actions"] = session.actions_log
        report["ok"] = bool(report["steps"]) and all(s["ok"] for s in report["steps"])

    except Exception as exc:
        logger.error("Test failed for %s: %s", game_name, exc)
        report["ok"] = False
        report["error"] = str(exc)

    finally:
        # Kill the whole tree so no game instance outlives the test.
        subprocess.run(["taskkill", "/T", "/F", "/PID", str(proc.pid)], capture_output=True)
        try:
            proc.wait(timeout=10.0)
        except subprocess.TimeoutExpired:
            proc.kill()
        logger.info("Packaged process tree stopped")

    return report


ROOT = Path(__file__).resolve().parent.parent
LOG_DIR = Path(r"E:\GameForge\validation\real_input_logs")
PROJECTS = Path(r"E:\GameForge\projects")

# Click targets are the HUD's own hitbox rectangles at 1280x720 (card_battler AGFCardHUD::DrawHUD):
# 4-card hand -> card 0 centre (392, 600); player half of lane index 1 -> centre (640, 280).
GAME_TESTS: Dict[str, List[Dict[str, Any]]] = {
    "Platformer": [
        {"type": "tap_key", "key": "SPACE", "hold_s": 0.1, "expect": ["jump"]},
        {"type": "hold_key", "key": "W", "duration_s": 1.2, "expect": ["moved"]},
        {"type": "tap_key", "key": "R", "expect": ["reset"]},
    ],
    "Arena": [
        {"type": "hold_key", "key": "W", "duration_s": 1.0, "expect": ["moved"]},
        {"type": "click_fraction", "rel_x": 0.5, "rel_y": 0.5, "button": "left", "expect": ["attack"]},
        {"type": "tap_key", "key": "SPACE", "hold_s": 0.1, "expect": ["attack"], "settle_s": 3.0},
        {"type": "tap_key", "key": "R", "expect": ["reset"]},
    ],
    "Cards": [
        {"type": "click_fraction", "rel_x": 392 / 1280, "rel_y": 600 / 720, "expect": ["select_card hand=0"]},
        {"type": "click_fraction", "rel_x": 640 / 1280, "rel_y": 280 / 720, "expect": ["card_play ok=1 hand=0 lane=1"]},
        {"type": "tap_key", "key": "E", "expect": ["turn_end"]},
        {"type": "tap_key", "key": "TAB", "expect": ["select_card"]},
        {"type": "tap_key", "key": "3", "expect": ["select_lane lane=2"]},
        {"type": "tap_key", "key": "ENTER", "expect": ["card_play"]},
        {"type": "tap_key", "key": "R", "expect": ["reset"]},
    ],
    "World": [
        # The world character spawns ~3.5 m above the terrain; let it land before walking.
        {"type": "wait", "duration_s": 3.0},
        {"type": "hold_key", "key": "W", "duration_s": 2.0, "expect": ["moved"]},
        {"type": "tap_key", "key": "SPACE", "hold_s": 0.1, "expect": ["jump"]},
        {"type": "tap_key", "key": "R", "expect": ["reset"]},
    ],
}


def main(argv=None) -> int:
    argv = sys.argv[1:] if argv is None else argv
    games = [a for a in argv if not a.startswith("--")] or list(GAME_TESTS)
    reports = []
    for g in games:
        name = "Audit" + g
        packaged = PROJECTS / name / "Packaged" / "Windows"
        exe = packaged / name / "Binaries" / "Win64" / f"{name}.exe"
        if not exe.is_file():
            exe = packaged / f"{name}.exe"
        reports.append(test_game(exe, name, GAME_TESTS[g]))

    summary_path = ROOT / "reports" / "packaged_real_input_summary.json"
    summary_path.write_text(json.dumps(reports, indent=2), encoding="utf-8")
    logger.info("Summary saved to %s", summary_path)

    all_ok = all(r.get("ok") for r in reports)
    print("\n" + "=" * 60)
    print(f"PACKAGED REAL-INPUT ACCEPTANCE: {'ALL PASSED' if all_ok else 'SOME FAILED'}")
    for r in reports:
        steps = r.get("steps", [])
        print(f"  [{'PASS' if r.get('ok') else 'FAIL'}] {r.get('game')}: "
              f"{sum(s['ok'] for s in steps)}/{len(steps)} actions produced their gameplay transition"
              + (f" ({r['error']})" if r.get("error") else ""))
    print("=" * 60)
    return 0 if all_ok else 1


if __name__ == "__main__":
    sys.exit(main())
