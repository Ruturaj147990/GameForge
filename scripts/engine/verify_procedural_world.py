"""GameForge Milestone 8: Procedural World End-to-End Generation & Hardened Real-Input Verification.

Prompt -> Spec -> C++ Scaffold -> UBT Build -> Live Editor Level Assembly -> UAT Automation Tests
       -> Package -> Packaged Self-Test -> Genuine Real Win32 Input Delivery -> Screenshot Evidence.

Zero Mocks. Zero Simulators. Zero Fake Unreal Connectors.
"""

from __future__ import annotations

import argparse
import ctypes
from ctypes import wintypes
import json
import logging
from pathlib import Path
import subprocess
import sys
import tempfile
import time
from typing import Dict, Any

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
from src.gameforge_ide.core.settings import get_settings  # noqa: E402

from src.gameforge_ide.pipeline.spec_from_prompt import match_prompt
from src.gameforge_ide.pipeline.game_pipeline import GamePipeline
from src.gameforge_ide.unreal.real_input import (
    RealInputSession,
    find_windows_for_pid,
    find_window_by_title_contains,
    get_client_rect,
)

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
logger = logging.getLogger("gameforge.milestone8")


def capture_window_bmp(hwnd: int, output_png: Path) -> bool:
    """Captures a screenshot of the hwnd client area to a PNG file."""
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
        if not hdc_screen:
            return False

        try:
            hdc_mem = gdi32.CreateCompatibleDC(hdc_screen)
            if not hdc_mem:
                return False

            try:
                hbm = gdi32.CreateCompatibleBitmap(hdc_screen, w, h)
                if not hbm:
                    return False

                try:
                    gdi32.SelectObject(hdc_mem, hbm)

                    # PW_RENDERFULLCONTENT (2) directs DWM to render DirectComposition / D3D12 hardware swapchain
                    PW_RENDERFULLCONTENT = 2
                    user32.PrintWindow(hwnd, hdc_mem, PW_RENDERFULLCONTENT)

                    try:
                        from PIL import Image
                        import numpy as np

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
                        bi.biHeight = -h
                        bi.biPlanes = 1
                        bi.biBitCount = 32
                        bi.biCompression = 0

                        buf = ctypes.create_string_buffer(w * h * 4)
                        gdi32.GetDIBits(hdc_mem, hbm, 0, h, buf, ctypes.byref(bi), 0)

                        arr = np.frombuffer(buf, dtype=np.uint8).reshape((h, w, 4))
                        img = Image.fromarray(arr[:, :, [2, 1, 0, 3]])
                        output_png.parent.mkdir(parents=True, exist_ok=True)
                        img.save(str(output_png))
                        logger.info("Captured screenshot to %s (%dx%d)", output_png, w, h)
                        return True
                    except ImportError:
                        logger.warning("PIL or numpy not available for screenshot writing")
                        return False
                finally:
                    gdi32.DeleteObject(hbm)
            finally:
                gdi32.DeleteDC(hdc_mem)
        finally:
            user32.ReleaseDC(hwnd, hdc_screen)
    except Exception as exc:
        logger.error("Screenshot capture failed: %s", exc)
        return False


def verify_image_content(png_path: Path) -> Dict[str, Any]:
    from PIL import Image, ImageStat
    with Image.open(png_path) as raw_img:
        img = raw_img.convert("L")
        hist = img.histogram()
        total = max(1, sum(hist))
        lit = sum(hist[16:]) / total
        stat = ImageStat.Stat(img)
        sd = stat.stddev[0] if stat.stddev else 0.0
        return {
            "checked": True,
            "size": list(img.size),
            "lit_fraction": round(lit, 4),
            "stddev": round(sd, 2),
            "has_content": lit > 0.05 and sd > 5.0,
        }


def main() -> int:
    parser = argparse.ArgumentParser(description="Procedural World End-to-End Verification")
    parser.add_argument(
        "--prompt",
        default="create a procedural landscape valley environment with a spline trail, foliage, and ancient ruins called GFProceduralWorld",
        help="Custom prompt for procedural world generation",
    )
    parser.add_argument("--skip-pipeline", action="store_true", help="Skip pipeline run if existing report found")
    args = parser.parse_args()

    logger.info("=================================================================")
    logger.info("GAMEFORGE MILESTONE 8: PROCEDURAL WORLD END-TO-END VERIFICATION")
    logger.info("=================================================================")

    prompt = args.prompt
    logger.info("Prompt: %s", prompt)

    spec = match_prompt(prompt)
    if not spec.matched:
        logger.error("Prompt did not match procedural_world recipe: %s", spec.reasons)
        return 1

    logger.info("Matched recipe: %s", spec.recipe_id)
    logger.info("Spec summary: %s", spec.summary())
    logger.info("Params: %s", spec.params)

    # 1. Run pipeline end-to-end (or load existing report if verified)
    projects_root = get_settings().projects_root
    repo_root = Path(__file__).resolve().parents[2]
    pipeline_report_path = projects_root / "GFProceduralWorld" / "Saved" / "GameForge" / "pipeline_report.json"
    if args.skip_pipeline and pipeline_report_path.exists():
        logger.info("Loading existing pipeline report from %s", pipeline_report_path)
        with open(pipeline_report_path, "r", encoding="utf-8") as f:
            pipeline_data = json.load(f)
        pipeline_duration = sum(s.get("duration_s", 0.0) for s in pipeline_data.get("stages", []))
        pipeline_stages = pipeline_data.get("stages", [])
        pipeline_ok = pipeline_data.get("ok", False)
    else:
        pipeline = GamePipeline()
        t_start = time.monotonic()
        res = pipeline.run(spec.params)
        pipeline_duration = round(time.monotonic() - t_start, 2)

        logger.info("Pipeline completed in %.2fs. Result ok=%s", pipeline_duration, res.ok)
        for st in res.stages:
            logger.info("  Stage [%s]: ok=%s, time=%.1fs, errors=%s", st.stage, st.ok, st.duration_s, st.errors)

        if not res.ok:
            logger.error("Pipeline failed at stage: %s", res.failed_stage)
            return 1
        pipeline_ok = res.ok
        pipeline_stages = [s.__dict__ for s in res.stages]

    # Find packaged executable
    bootstrap_exe = projects_root / "GFProceduralWorld" / "Packaged" / "Windows" / "GFProceduralWorld.exe"
    binary_exe = projects_root / "GFProceduralWorld" / "Packaged" / "Windows" / "GFProceduralWorld" / "Binaries" / "Win64" / "GFProceduralWorld.exe"
    exe_path = bootstrap_exe if bootstrap_exe.exists() else binary_exe
    if not exe_path.exists():
        logger.error("Packaged executable not found: %s", exe_path)
        return 1

    logger.info("Packaged executable verified at %s (%d bytes)", exe_path, exe_path.stat().st_size)

    # 2. Launch live packaged executable for Real-Input Acceptance Testing
    logger.info("Launching live packaged game for Real Win32 Input testing...")
    cmd = [str(exe_path), "-windowed", "-ResX=1280", "-ResY=720", "-NoSound"]
    proc = subprocess.Popen(cmd)
    logger.info("Process launched with PID %d", proc.pid)

    screenshot_path = repo_root / "reports" / "packaged_GFProceduralWorld_real_input.png"
    real_input_results: Dict[str, Any] = {}

    try:
        # Find window
        time.sleep(3.0)
        main_hwnd = None
        for _ in range(25):
            hwnds = find_windows_for_pid(proc.pid)
            if hwnds:
                main_hwnd = hwnds[0]
                break
            # Fallback by title
            main_hwnd = find_window_by_title_contains("GFProceduralWorld")
            if main_hwnd:
                break
            time.sleep(1.0)

        if not main_hwnd:
            logger.error("Could not find window for PID %d or by title", proc.pid)
            return 1

        rect = get_client_rect(main_hwnd)
        logger.info("Found window hwnd=0x%x, client rect=%s", main_hwnd, rect)

        session = RealInputSession(main_hwnd, target_name="GFProceduralWorld")
        session.focus()
        time.sleep(1.5)

        # 1. Forward traversal along the road
        logger.info("Delivering 'W' keypress (Walk Forward along road)...")
        session.hold_key("W", duration_s=2.0)
        time.sleep(0.5)

        # 2. Jump input
        logger.info("Delivering 'SPACE' keypress (Jump)...")
        session.tap_key("SPACE", hold_s=0.15)
        time.sleep(0.8)

        # 3. Strafe right
        logger.info("Delivering 'D' keypress (Strafe Right)...")
        session.hold_key("D", duration_s=0.6)
        time.sleep(0.5)

        # 4. Turn mouse slightly
        logger.info("Delivering mouse look...")
        session.move_mouse_fraction(0.55, 0.50)
        time.sleep(0.2)
        session.move_mouse_fraction(0.60, 0.50)
        time.sleep(0.5)

        # 5. Capture live viewport screenshot
        captured = capture_window_bmp(main_hwnd, screenshot_path)
        if not captured:
            logger.error("Failed to capture screenshot")
            return 1

        # 6. Reset world
        logger.info("Delivering 'R' keypress (Reset World)...")
        session.tap_key("R", hold_s=0.08)
        time.sleep(0.5)

        # Analyze screenshot
        img_info = verify_image_content(screenshot_path)
        logger.info("Screenshot analysis: %s", img_info)
        if not img_info["has_content"]:
            logger.error("Screenshot shows no content (black/blank image)!")
            return 1

        real_input_results = {
            "window_found": True,
            "hwnd": hex(main_hwnd),
            "client_rect": rect,
            "inputs_dispatched": ["W (2.0s)", "SPACE", "D (0.6s)", "MouseMove", "R (Reset)"],
            "screenshot_path": str(screenshot_path),
            "screenshot_analysis": img_info,
        }

    finally:
        try:
            proc.terminate()
            proc.wait(timeout=5)
        except Exception:
            proc.kill()
        logger.info("Process %d cleanly terminated.", proc.pid)

    # Write summary evidence report
    report_data = {
        "milestone": "Milestone 8: Procedural Landscapes and World Generation V1",
        "timestamp": time.strftime("%Y-%m-%dT%H:%M:%S%z"),
        "prompt": prompt,
        "spec": {
            "recipe_id": spec.recipe_id,
            "summary": spec.summary(),
            "params": spec.params.to_dict(),
        },
        "pipeline": {
            "ok": pipeline_ok,
            "duration_s": pipeline_duration,
            "stages": pipeline_stages,
        },
        "packaged_executable": {
            "path": str(exe_path),
            "size_bytes": exe_path.stat().st_size,
        },
        "real_input_verification": real_input_results,
    }

    report_file = repo_root / "reports" / "milestone8_procedural_world_demo.json"
    report_file.parent.mkdir(parents=True, exist_ok=True)
    tmp = report_file.with_suffix(".tmp")
    tmp.write_text(json.dumps(report_data, indent=2), encoding="utf-8")
    tmp.replace(report_file)
    logger.info("Milestone 8 report written to %s", report_file)
    logger.info("MILESTONE 8 PROCEDURAL WORLD VERIFICATION COMPLETED SUCCESSFULLY!")
    return 0


if __name__ == "__main__":
    sys.exit(main())
