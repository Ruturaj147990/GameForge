"""Build and verify GameForge 1.0 portable distribution and smoke test on fresh profile (WI-11.2)."""
from __future__ import annotations

import json
import os
import shutil
import subprocess
import sys
import time
import zipfile
from pathlib import Path
from typing import Optional

REPO_ROOT = Path(__file__).resolve().parents[2]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from src.gameforge_ide.core.settings import PACKAGE_ROOT, get_settings


def build_distribution(output_root: Optional[Path] = None) -> dict:
    s = get_settings()
    base_release_dir = output_root or (s.data_root / "release")
    dest_dir = base_release_dir / "GameForge-1.0.0-win64"
    zip_path = base_release_dir / "GameForge-1.0.0-win64.zip"

    dest_dir.parent.mkdir(parents=True, exist_ok=True)
    if dest_dir.exists():
        shutil.rmtree(dest_dir)
    dest_dir.mkdir(parents=True, exist_ok=True)

    # 1. Copy gameforge_ide package into src/gameforge_ide so `from src.gameforge_ide...` and `-m src.gameforge_ide.launcher` work
    dest_src = dest_dir / "src"
    dest_src.mkdir(parents=True, exist_ok=True)
    (dest_src / "__init__.py").write_text("", encoding="utf-8")
    dest_pkg = dest_src / "gameforge_ide"
    shutil.copytree(
        PACKAGE_ROOT,
        dest_pkg,
        ignore=shutil.ignore_patterns("__pycache__", "*.pyc", "*.pdb", "scratch*"),
    )

    # 2. Copy canonical launcher, installer, icon from release/
    shutil.copy2(REPO_ROOT / "release" / "GameForge.bat", dest_dir / "GameForge.bat")
    shutil.copy2(REPO_ROOT / "release" / "Install-GameForge.ps1", dest_dir / "Install-GameForge.ps1")
    shutil.copy2(REPO_ROOT / "release" / "gameforge.ico", dest_dir / "gameforge.ico")

    # 3. Calculate directory footprint
    total_bytes = 0
    file_count = 0
    for root, _, files in os.walk(dest_dir):
        for f in files:
            fp = Path(root) / f
            total_bytes += fp.stat().st_size
            file_count += 1

    footprint_mb = round(total_bytes / (1024 * 1024), 2)
    assert footprint_mb <= 250.0, f"Footprint {footprint_mb} MB exceeds 250 MB budget!"

    # 4. Create ZIP archive
    if zip_path.exists():
        zip_path.unlink()
    with zipfile.ZipFile(zip_path, "w", zipfile.ZIP_DEFLATED, compresslevel=6) as zf:
        for root, _, files in os.walk(dest_dir):
            for f in files:
                abs_p = Path(root) / f
                rel_p = abs_p.relative_to(dest_dir)
                zf.write(abs_p, arcname=str(rel_p))

    zip_size_mb = round(zip_path.stat().st_size / (1024 * 1024), 2)

    # 5. Smoke test on a fresh settings profile
    smoke_settings_file = dest_dir / "fresh_user_settings.json"
    smoke_settings_file.write_text("{}", encoding="utf-8")

    smoke_script = f"""
import os
import sys
import time

os.environ["GAMEFORGE_USER_SETTINGS"] = r"{smoke_settings_file}"
os.environ.pop("GAMEFORGE_HOST_PROFILE", None)

from src.gameforge_ide.core.settings import get_settings
from src.gameforge_ide.core.systems import probe_all
from src.gameforge_ide.design.presets import PRESETS
from src.gameforge_ide.composer import compose

# Fresh settings load
s = get_settings()
assert s.bridge_port == 47815, "Default port mismatch"
assert s.engine_channel == "pinned", "Default engine channel mismatch"

# Systems probe
snapshot = probe_all()
rows = {{r.key: r for r in snapshot.rows}}
assert "disk" in rows, "Disk detection missing"

# Preset game creation
preset_fn = PRESETS["platformer"]
gds = preset_fn(title="SmokePlatformer")
comp = compose(gds)
assert len(comp.levels) >= 1, "Level composition failed"
assert comp.project_name == "SmokePlatformer"

print("SMOKE_PASS")
"""

    env = dict(os.environ)
    env["PYTHONPATH"] = str(dest_dir)
    env["GAMEFORGE_USER_SETTINGS"] = str(smoke_settings_file)
    env.pop("GAMEFORGE_HOST_PROFILE", None)

    t0 = time.time()
    res = subprocess.run([sys.executable, "-c", smoke_script], env=env, capture_output=True, text=True)
    smoke_duration = round(time.time() - t0, 2)
    assert res.returncode == 0 and "SMOKE_PASS" in res.stdout, f"Smoke test failed: {res.stderr}\n{res.stdout}"

    # Remove temporary smoke settings file after smoke test
    if smoke_settings_file.exists():
        smoke_settings_file.unlink()

    # 6. Record reports
    smoke_report = {
        "status": "PASS",
        "package_dir": str(dest_dir),
        "zip_path": str(zip_path),
        "install_footprint_mb": footprint_mb,
        "zip_archive_mb": zip_size_mb,
        "files_packaged": file_count,
        "budget_mb": 250.0,
        "budget_met": footprint_mb <= 250.0,
        "fresh_profile_smoke": {
            "onboarding_ready": True,
            "preset_composed": True,
            "duration_s": smoke_duration,
        },
    }

    out_dir = REPO_ROOT / "reports" / "P11"
    out_dir.mkdir(parents=True, exist_ok=True)
    (out_dir / "packaged_ide_smoke.json").write_text(json.dumps(smoke_report, indent=2), encoding="utf-8")

    return smoke_report


if __name__ == "__main__":
    rep = build_distribution()
    print(f"Distribution build: {rep['status']}")
    print(f"Footprint: {rep['install_footprint_mb']} MB (budget: {rep['budget_mb']} MB)")
    print(f"ZIP Archive: {rep['zip_archive_mb']} MB")
    print(f"Fresh Profile Smoke: {'PASS' if rep['fresh_profile_smoke']['onboarding_ready'] else 'FAIL'}")
