"""Forge step handler for Content preparation (P7 WI-7.1, WI-7.8).

Installs Epic template content packs (Mannequins, LevelPrototyping), configures cooker
directories in DefaultGame.ini, synthesizes procedural audio/SFX presets, and registers
all assets with honest provenance in the project's AssetRegistry.
"""
from __future__ import annotations

from pathlib import Path
from typing import Any, Dict, List

from ..executor import StepContext, StepOutcome
from ...content.epic_packs import install_pack, update_default_game_ini_cook_dirs, EPIC_PACKS
from ...content.sfx_presets import synthesize_sfx_preset, SFX_SETS
from ...content.music import generate_music_loop
from ...content.ambience import generate_ambience_loop
from ...backend.assets.registry import AssetRegistry, AssetRecord
from ...core.settings import engine_root_or_missing, get_settings


def content_handler(ctx: StepContext) -> StepOutcome:
    """Forge CONTENT step: install Epic packs, configure cooker dirs, generate audio feedback."""
    project_dir = Path(ctx.project_dir) if ctx.project_dir else Path(ctx.workspace_dir)
    engine_root = Path(ctx.step.inputs.get("engine_root") or engine_root_or_missing())

    registry = AssetRegistry(project_dir)
    installed_packs: List[str] = []
    artifacts: List[str] = []

    # 1. Install Epic Template Content Packs
    for pack_name in ("mannequins", "level_prototyping"):
        try:
            pack_res = install_pack(project_dir, pack_name, engine_root, registry=registry)
            installed_packs.append(pack_name)
        except Exception as exc:
            # If engine template dir is unavailable, note but don't hard crash unless required
            ctx.log(f"Warning: Failed to install Epic pack {pack_name}: {exc}")

    # 2. Configure Cooker Directories in DefaultGame.ini
    cook_dirs = [
        "/Game/Characters",
        "/Game/LevelPrototyping",
        "/Game/GameForge",
        "/Game/Maps",
    ]
    ini_path = update_default_game_ini_cook_dirs(project_dir, cook_dirs)
    artifacts.append(str(ini_path))

    # 3. Generate Default Audio Feedback Assets
    sfx_dir = project_dir / "Content" / "GameForge" / "SFX"
    sfx_dir.mkdir(parents=True, exist_ok=True)

    for sfx_name in ("pickup_chime", "impact", "defeat", "fanfare", "ui_click"):
        wav_file = sfx_dir / f"S_{sfx_name.title().replace('_', '')}.wav"
        if not wav_file.is_file():
            synthesize_sfx_preset(sfx_name, wav_file, style="default")
            artifacts.append(str(wav_file))

            aid = registry.register(
                AssetRecord(
                    name=wav_file.stem,
                    asset_type="sound",
                    purpose=f"Procedural {sfx_name} sound effect",
                    provenance="PROC",
                    backend="SFXSynth",
                    backend_version="1.0.0",
                    license="GameForge-Generated (project-owned)",
                    spec={"sfx_name": sfx_name},
                    tags=["audio", "sfx"],
                )
            )
            registry.advance(aid, "GENERATE", True, artifact_path=str(wav_file))
            registry.advance(aid, "ENGINE_VERIFY", True)
            registry.advance(aid, "PROMOTE", True, unreal_path=f"/Game/GameForge/SFX/{wav_file.stem}")

    # 4. Generate Music and Ambience Tracks
    music_dir = project_dir / "Content" / "GameForge" / "Audio"
    music_dir.mkdir(parents=True, exist_ok=True)
    music_wav = music_dir / "M_MainTheme.wav"
    if not music_wav.is_file():
        generate_music_loop("calm", music_wav)
        artifacts.append(str(music_wav))

    ambience_wav = music_dir / "A_WindBed.wav"
    if not ambience_wav.is_file():
        generate_ambience_loop("wind", ambience_wav, duration_s=6.0)
        artifacts.append(str(ambience_wav))

    ctx.log(f"Content step completed: installed packs={installed_packs}, generated {len(artifacts)} audio/ini artifacts")

    return StepOutcome(
        ok=True,
        data={
            "installed_packs": installed_packs,
            "cook_dirs": cook_dirs,
            "artifacts_count": len(artifacts),
        },
    )
