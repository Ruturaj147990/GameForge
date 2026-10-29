"""Packaged Build Real-Input Acceptance Verification.
Exercises GFPlatformer.exe, GFArenaCombat.exe, and GFCardBattler.exe using genuine
OS-level Win32 keyboard and mouse input events delivered to the live focused window.

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

        # PrintWindow with PW_CLIENTONLY (1)
        user32.PrintWindow(hwnd, hdc_mem, 1)

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


def test_game(exe_path: Path, game_name: str, test_actions: List[Dict[str, Any]]) -> Dict[str, Any]:
    logger.info("=" * 60)
    logger.info("TESTING PACKAGED GAME: %s (%s)", game_name, exe_path)
    logger.info("=" * 60)

    if not exe_path.is_file():
        return {
            "game": game_name,
            "exe_path": str(exe_path),
            "ok": False,
            "error": f"Executable not found at {exe_path}",
        }

    cmd = [
        str(exe_path),
        "-windowed",
        "-ResX=1280",
        "-ResY=720",
        "-log",
        "-NoSound",
    ]

    logger.info("Launching: %s", " ".join(cmd))
    proc = subprocess.Popen(cmd)

    hwnd = None
    title = ""
    session = None
    report: Dict[str, Any] = {
        "game": game_name,
        "exe_path": str(exe_path),
        "pid": proc.pid,
        "actions": [],
        "ok": False,
    }

    try:
        # Await game window appearance
        deadline = time.time() + 25.0
        while time.time() < deadline:
            if proc.poll() is not None:
                raise RuntimeError(f"Process exited prematurely with code {proc.returncode}")

            hwnds = find_windows_for_pid(proc.pid)
            if hwnds:
                hwnd = hwnds[0]
                break

            # Fallback by title
            hwnd = find_window_by_title_contains(game_name)
            if hwnd:
                break

            time.sleep(1.0)

        if not hwnd:
            raise TimeoutError(f"Game window for PID {proc.pid} ({game_name}) did not appear within 25s")

        logger.info("Found game window: HWND 0x%X", hwnd)
        time.sleep(3.0)  # Wait for first frame render

        session = RealInputSession(hwnd, target_name=game_name)
        assert session.focus(), f"Failed to focus window HWND 0x%X"
        logger.info("Successfully focused window")
        time.sleep(1.0)

        geom = session.get_client_geometry()
        logger.info("Window client geometry: %s", geom)

        # Execute test actions
        for act in test_actions:
            act_type = act.get("type")
            if act_type == "tap_key":
                key = act["key"]
                hold_s = act.get("hold_s", 0.08)
                logger.info("Action: Tap key '%s' (hold %.2fs)", key, hold_s)
                session.tap_key(key, hold_s=hold_s)
                time.sleep(0.3)
            elif act_type == "hold_key":
                key = act["key"]
                dur_s = act["duration_s"]
                logger.info("Action: Hold key '%s' for %.2fs", key, dur_s)
                session.hold_key(key, duration_s=dur_s)
                time.sleep(0.3)
            elif act_type == "click_fraction":
                rx = act["rel_x"]
                ry = act["rel_y"]
                btn = act.get("button", "left")
                logger.info("Action: Click mouse '%s' at fraction (%.2f, %.2f)", btn, rx, ry)
                session.click_fraction(rx, ry, button=btn)
                time.sleep(0.3)
            elif act_type == "move_mouse":
                rx = act["rel_x"]
                ry = act["rel_y"]
                session.move_mouse_fraction(rx, ry)
                time.sleep(0.1)

        # Capture evidence screenshot
        shot_path = Path(f"reports/packaged_{game_name}_real_input.png")
        shot_ok = capture_window_bmp(hwnd, shot_path)
        logger.info("Evidence screenshot captured: %s (ok=%s)", shot_path, shot_ok)

        report["ok"] = True
        report["screenshot_path"] = str(shot_path) if shot_ok else None
        report["actions"] = session.actions_log
        report["window_geometry"] = geom

    except Exception as exc:
        logger.error("Test failed for %s: %s", game_name, exc)
        report["ok"] = False
        report["error"] = str(exc)

    finally:
        # Graceful shutdown
        logger.info("Terminating packaged process PID %d...", proc.pid)
        try:
            if session:
                session.tap_key("ESCAPE")
            time.sleep(1.0)
        except Exception:
            pass

        if proc.poll() is None:
            proc.terminate()
            try:
                proc.wait(timeout=5.0)
            except subprocess.TimeoutExpired:
                proc.kill()
                proc.wait()
        logger.info("Packaged process cleanly stopped")

    return report


def main():
    reports = []
    output_dir = Path("reports")
    output_dir.mkdir(parents=True, exist_ok=True)

    # 1. Platformer Real-Input Packaged Test
    platformer_exe = Path(r"E:\GameForge\projects\GFPlatformer\Packaged\Windows\GFPlatformer.exe")
    platformer_actions = [
        {"type": "tap_key", "key": "SPACE", "hold_s": 0.1},    # Jump
        {"type": "hold_key", "key": "W", "duration_s": 1.0},   # Walk forward
        {"type": "tap_key", "key": "SPACE", "hold_s": 0.15},   # Jump across platform
        {"type": "hold_key", "key": "D", "duration_s": 0.5},   # Strafe right
        {"type": "tap_key", "key": "R", "hold_s": 0.08},       # Restart / Respawn
    ]
    rep_platformer = test_game(platformer_exe, "GFPlatformer", platformer_actions)
    reports.append(rep_platformer)

    # 2. Arena Combat Real-Input Packaged Test
    arena_exe = Path(r"E:\GameForge\projects\GFArenaCombat\Packaged\Windows\GFArenaCombat.exe")
    arena_actions = [
        {"type": "hold_key", "key": "W", "duration_s": 0.8},   # Advance toward arena center
        {"type": "tap_key", "key": "SPACE", "hold_s": 0.1},    # Attack swing
        {"type": "click_fraction", "rel_x": 0.5, "rel_y": 0.5, "button": "left"}, # Left-click attack
        {"type": "hold_key", "key": "S", "duration_s": 0.4},   # Back step
        {"type": "tap_key", "key": "R", "hold_s": 0.08},       # Restart match
    ]
    rep_arena = test_game(arena_exe, "GFArenaCombat", arena_actions)
    reports.append(rep_arena)

    # 3. Card Battler Real-Input Packaged Test
    card_exe = Path(r"E:\GameForge\projects\GFCardBattler\Packaged\Windows\GFCardBattler.exe")
    card_actions = [
        {"type": "move_mouse", "rel_x": 0.3, "rel_y": 0.75},   # Hover card 0
        {"type": "click_fraction", "rel_x": 0.3, "rel_y": 0.75, "button": "left"}, # Select Card 0
        {"type": "move_mouse", "rel_x": 0.5, "rel_y": 0.5},    # Hover Lane 1
        {"type": "click_fraction", "rel_x": 0.5, "rel_y": 0.5, "button": "left"}, # Place in Lane 1
        {"type": "click_fraction", "rel_x": 0.85, "rel_y": 0.85, "button": "left"}, # Click End Turn button
    ]
    rep_card = test_game(card_exe, "GFCardBattler", card_actions)
    reports.append(rep_card)

    summary_path = output_dir / "packaged_real_input_summary.json"
    summary_path.write_text(json.dumps(reports, indent=2), encoding="utf-8")
    logger.info("Summary saved to %s", summary_path)

    all_ok = all(r.get("ok") for r in reports)
    print("\n" + "=" * 60)
    print(f"PACKAGED REAL-INPUT ACCEPTANCE: {'ALL PASSED' if all_ok else 'SOME FAILED'}")
    for r in reports:
        status = "PASS" if r.get("ok") else "FAIL"
        print(f"  [{status}] {r.get('game')}: {len(r.get('actions', []))} actions dispatched")
    print("=" * 60)
    return 0 if all_ok else 1


if __name__ == "__main__":
    sys.exit(main())
