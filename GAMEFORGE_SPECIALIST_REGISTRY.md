# GameForge Specialist Registry

Updated 2026-10-30T17:20Z (Claude Code). Rule: **one active canonical backend per capability**, no silent
substitution, and every NEURAL claim requires a measured local run on this host (Ryzen 5 7600X, 32 GB,
RX 7700 XT 12 GB, Windows 11). Adding or installing any backend requires user approval (AGENTS.md).

## Active canonical backends

| Capability | Backend (version) | Kind | Runs | Resources | License | Status |
|---|---|---|---|---|---|---|
| Fast reasoning | `gameforge-qwen3.5-4b:latest` (Ollama 91b2043beeee) | LLM | Local | ~3–4 GB VRAM | Qwen license (per model card) | PASS |
| Standard reasoning | `gameforge-qwen3.5-9b:latest` (278e024c31f7) | LLM | Local | ~7 GB | Qwen | PASS |
| Heavy reasoning | `gameforge-27b-sft:latest` (03d36e692be8) | LLM | Local, partial offload | 5.4 tok/s | Per base model | PASS |
| General | `llama3.1:8b` (46e0c10c039e) | LLM | Local | ~5 GB | Llama 3.1 Community | PASS |
| Vision review | gameforge-qwen3.5-4b + mmproj | VLM | Local | shares the 4B | Qwen | PASS (advisory only) |
| Character mesh + rig | `ProceduralSkinnedCharacterGenerator` (`backend/tools/character_generator.py`) | PROC | Local CPU | <1 s | Project-owned | PASS (prototype) |
| Motion | `ProceduralKinematicMotionSynthesizer` (`backend/tools/motion_generator.py`) | PROC | Local CPU | <1 s | Project-owned | PASS |
| Terrain/world | `UGameForgeLandscapeLibrary` + PCG | NATIVE/PROC | In-engine | Editor | Epic EULA | PASS (v1) |

## Planned canonical backends (to build; no installs needed)

| Capability | Backend | Why this one |
|---|---|---|
| Props/architecture meshes | UE Geometry Script (`GeometryScriptingCore`) | Native assets, UVs, booleans and simplification in-engine; no format conversion; deterministic |
| PBR textures | numpy procedural generator (albedo/normal/ORM) | Works on any GPU; tileable; exact channel control |
| SFX / ambience | numpy synth → WAV + MetaSound | Fully licensed by construction |
| VFX | Niagara engine templates + parameter overrides | Stable API; no neural option is better here |

## Neural candidates (evaluate one per capability, only after approval)

| Capability | Candidate | Blocker on this host | Next step |
|---|---|---|---|
| Image-to-3D | TripoSR (MIT) / Hunyuan3D-2 (Tencent community license, territory limits) | CUDA kernels; AMD Windows | Retest only if ROCm-on-Windows PyTorch or a DirectML/ONNX port is confirmed working. Output is a static unrigged mesh, so it would feed M12 props, not characters |
| Auto-rig | UniRig / RigNet | CUDA; research quality | Keep the procedural rig |
| Text-to-motion | MDM / MoMask (SMPL licence restricts commercial use) | CUDA + SMPL licence | Keep procedural |
| Texture image gen | SD-family via ONNX/DirectML | Not installed; licence varies by checkpoint | Request approval with a specific checkpoint + licence |
| Speech | Piper TTS (MIT engine; per-voice licences) | Not installed | Request approval; record the voice licence |
| Music | none chosen | Licence clarity | Procedural/MetaSound first |

Every entry above that has not been run locally is `[UNVERIFIED]`. Statements about licences and hardware come
from the M9/M10 investigations in `context.md` and must be re-checked against the model card before adoption.
