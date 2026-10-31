"""Declarative catalogue of the in-editor operations exposed by the ``gameforge_ops`` package (roadmap AD-1).

Every ``@op`` in the editor dispatcher must have an entry here. Ops that change project or runtime state must
name a read-only ``readback_op`` that can confirm the change; ``tests/unit/test_op_catalog.py`` enforces both
rules, and ``scripts/gen_op_coverage.py`` renders the catalogue as Markdown.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from pathlib import Path

OPS_SOURCE = Path(__file__).parent / "GameForge" / "Content" / "Python" / "gameforge_ops"


def op_sources(root: Path = OPS_SOURCE) -> list[Path]:
    """The op package's module files (a single file is accepted for older layouts)."""
    return [root] if root.is_file() else sorted(root.glob("*.py"))

# effect: "read" (no state change), "artifact" (writes a file outside the project, e.g. a screenshot),
# "view" (editor camera only), "lifecycle" (editor session), "runtime" (PIE/session state),
# "project" (persistent asset/level change).
EFFECTS = ("read", "artifact", "view", "lifecycle", "runtime", "project")
STATUSES = ("PASS", "PARTIAL", "EXPERIMENTAL", "DIAGNOSTIC", "LEGACY")


@dataclass(frozen=True)
class OpSpec:
    name: str
    domain: str
    effect: str
    readback_op: str | None = None
    status: str = "PASS"
    note: str = ""

    @property
    def mutates(self) -> bool:
        return self.effect in ("runtime", "project")


def _ops(domain: str, effect: str, names: str, readback: str | None = None, status: str = "PASS",
         note: str = "") -> list[OpSpec]:
    return [OpSpec(n, domain, effect, readback, status, note) for n in names.split()]


CATALOG: dict[str, OpSpec] = {spec.name: spec for spec in [
    *_ops("session", "read", "handshake log_tail"),
    *_ops("session", "lifecycle", "quit_editor"),
    *_ops("assets", "read", "asset_exists list_assets asset_dependencies"),
    *_ops("assets", "project", "import_asset rename_asset delete_asset save_all create_material", "asset_exists"),
    *_ops("level", "read", "actors_in_level scene_get_exposure"),
    *_ops("level", "project", "scene_set_manual_exposure", "scene_get_exposure"),
    *_ops("level", "project", "spawn_actor delete_actor set_actor_property new_level load_level", "actors_in_level"),
    *_ops("viewport", "artifact", "viewport_screenshot"),
    *_ops("viewport", "view", "set_viewport_camera"),
    *_ops("pie", "read", "pie_status pie_character_diagnostics pie_actor_state"),
    *_ops("pie", "runtime", "pie_start pie_stop", "pie_status"),
    *_ops("pie", "runtime", "pie_view_from pie_move_player_to", "pie_character_diagnostics"),
    *_ops("blueprint", "read", "blueprint_inspect blueprint_readback_graph"),
    *_ops("blueprint", "project", "create_blueprint compile_blueprint", "blueprint_inspect"),
    *_ops("blueprint", "project", "blueprint_create_node blueprint_set_pin_default blueprint_connect_pins "
          "blueprint_disconnect_pins blueprint_delete_node blueprint_compile blueprint_save",
          "blueprint_readback_graph"),
    *_ops("umg", "read", "widget_inspect widget_readback_tree widget_inspect_events widget_runtime_state"),
    *_ops("umg", "project", "widget_create_blueprint widget_create widget_set_property widget_set_slot_property "
          "widget_remove widget_compile widget_save", "widget_readback_tree"),
    *_ops("umg", "project", "widget_bind_event", "widget_inspect_events"),
    *_ops("umg", "runtime", "widget_display_in_game widget_click_button", "widget_runtime_state"),
    *_ops("umg", "runtime", "widget_trigger_delegate_diagnostic", "widget_runtime_state", "DIAGNOSTIC",
          "Direct delegate broadcast; never acceptance evidence (use widget_click_button)."),
    *_ops("gameplay", "read", "gameplay_get_state gameplay_objectives"),
    *_ops("gameplay", "runtime", "gameplay_modify_state", "gameplay_get_state"),
    *_ops("world", "read", "procedural_world_inspect world_generation_digest landscape_inspect_layers "
          "landscape_height_at"),
    *_ops("world", "project", "world_clear_generated", "actors_in_level", "PASS",
          "Label-prefix ownership (AD-7 interim): reports/m8v2_village_demo.json"),
    *_ops("world", "project", "landscape_create spline_create_road foliage_scatter landmark_spawn",
          "procedural_world_inspect"),
    *_ops("world", "read", "datalayer_list_actors"),
    *_ops("world", "project", "datalayer_ensure datalayer_add_actors", "datalayer_list_actors", "PASS",
          "WP Data Layers own generated content; membership read from actor descriptors (covers unloaded actors): reports/m8v2_datalayers_demo.json."),
    *_ops("pcg", "read", "pcg_inspect pcg_verify_authenticity"),
    *_ops("pcg", "project", "pcg_build_graph", "pcg_verify_authenticity", "PASS",
          "Surface-sampled PCG: reports/m8v2_pcg_demo.json; tag-based exclusion (Difference): reports/m8v2_village_demo.json"),
    *_ops("pcg", "project", "pcg_scatter", "pcg_verify_authenticity", "PARTIAL",
          "Real UPCGGraph (WP-A re-verify 2026-10-30: 400 instances in a PCG-tagged ISM); grid sampling only."),
    *_ops("materials", "read", "texture_inspect material_readback_graph material_instance_inspect actor_get_materials "
          "material_function_inspect"),
    *_ops("materials", "project", "material_function_build", "material_function_inspect", "PASS",
          "M11 demo: reports/m11_material_demo.json"),
    *_ops("materials", "project", "texture_import", "texture_inspect", "PASS", "M11 demo: reports/m11_material_demo.json"),
    *_ops("materials", "project", "material_build_graph", "material_readback_graph", "PASS",
          "M11 demo: reports/m11_material_demo.json"),
    *_ops("materials", "project", "material_instance_create", "material_instance_inspect", "PASS",
          "M11 demo: reports/m11_material_demo.json"),
    *_ops("session", "read", "api_introspect"),
    *_ops("mesh", "read", "static_mesh_inspect"),
    *_ops("mesh", "project", "mesh_generate_prop static_mesh_configure", "static_mesh_inspect", "PASS",
          "M12 Geometry Script demo: reports/m12_asset_demo.json"),
    *_ops("vfx", "read", "vfx_inspect_system vfx_particle_counts"),
    *_ops("vfx", "project", "vfx_create_system", "vfx_inspect_system", "PARTIAL",
          "Template-system duplication PASS; template_emitters path unsupported in 5.7 Python (empty system)."),
    *_ops("vfx", "runtime", "vfx_spawn", "vfx_particle_counts", "PASS",
          "M13 demo: reports/m13_vfx_demo.json; gameplay-triggered path (AGameForgeVFXPickup): reports/m13_gameplay_vfx_demo.json"),
    *_ops("audio", "read", "audio_inspect audio_inspect_attenuation audio_status"),
    *_ops("audio", "project", "audio_import", "audio_inspect", "PASS", "M14 demo: reports/m14_audio_demo.json"),
    *_ops("audio", "project", "audio_create_attenuation", "audio_inspect_attenuation", "PASS", "M14 demo"),
    *_ops("audio", "runtime", "audio_play_at", "audio_status", "PASS",
          "Fixed 2026-10-31: loads via unreal.load_asset (EditorAssetLibrary refuses during PIE). reports/m14_audio_demo.json."),
    *_ops("audio", "read", "metasound_inspect"),
    *_ops("audio", "project", "metasound_build_source", "metasound_inspect", "PASS",
          "Builder graph -> MetaSoundSource; graph-driven OnFinished verified in PIE: reports/m14_metasound_demo.json."),
    *_ops("audio", "runtime", "audio_diagnose_spawn", "audio_status", "DIAGNOSTIC",
          "Tries spawn variants/context objects to locate the audio_play_at failure; never acceptance evidence."),
    *_ops("audio", "project", "audio_place_ambient", "actors_in_level", "PASS", "M14 demo"),
    *_ops("audio", "runtime", "audio_play_actor", "audio_status", "PASS", "M14 demo (needs launch(no_sound=False))"),
    *_ops("cinematics", "read", "sequence_inspect sequence_evaluate sequence_render_status"),
    *_ops("cinematics", "project", "sequence_build", "sequence_inspect", "PASS", "reports/m16_sequence_demo.json"),
    *_ops("cinematics", "artifact", "sequence_render", None, "PASS",
          "Lit/unlit MRQ PNG frames; cuts verified in reports/m16_sequence_demo.json. Demo lights must face the cameras."),
    *_ops("profiling", "read", "perf_list_csv"),
    *_ops("profiling", "runtime", "perf_console", "perf_list_csv", "PASS",
          "Allow-listed csvprofile/stat commands only; reports/m19_perf_village.json"),
    *_ops("navigation", "read", "nav_find_path"),
    *_ops("navigation", "project", "nav_rebuild", "nav_find_path"),
    *_ops("character", "read", "character_inspect_skeletal_mesh character_measure_deformation"),
    *_ops("character", "project", "character_import_skeletal_mesh", "character_inspect_skeletal_mesh"),
    *_ops("character", "project", "character_spawn_preview", "actors_in_level"),
    *_ops("animation", "read", "anim_inspect_sequence anim_inspect_blueprint anim_sample_bone_pose anim_sample_world_pose "
          "anim_locomotion_test_result"),
    *_ops("animation", "project", "anim_create_locomotion_blueprint", "anim_inspect_blueprint", "PASS",
          "Optional blend_space drives Idle/Walk/Run by speed: reports/m10v2_blend_drive_demo.json."),
    *_ops("animation", "read", "anim_inspect_blendspace"),
    *_ops("animation", "project", "anim_create_blendspace_1d", "anim_inspect_blendspace", "PASS",
          "Rebuilds runtime segments natively (plugin m10v2+); reports/m10v2_blend_drive_demo.json."),
    *_ops("animation", "project", "anim_import_motion_clip", "anim_sample_bone_pose"),
    *_ops("animation", "project", "anim_ik_retarget", "anim_sample_world_pose", "PASS",
          "Genuine IK retarget: world-space chain proof in reports/wpa_reverify_20261031.json."),
    *_ops("animation", "project", "anim_retarget_sequence", "anim_inspect_sequence", "LEGACY",
          "SetSkeleton copy, not a retarget; never cite as retarget evidence."),
    *_ops("animation", "runtime", "anim_start_locomotion_test", "anim_locomotion_test_result"),
]}


AGENT_HIDDEN_STATUSES = ("DIAGNOSTIC", "LEGACY")


def agent_ops() -> list[str]:
    """Ops the agent may call: everything catalogued except diagnostics and legacy ops (never evidence)."""
    return sorted(n for n, s in CATALOG.items() if s.status not in AGENT_HIDDEN_STATUSES)


def read_only_ops() -> frozenset[str]:
    """Ops with no state change; the tool gateway runs these without an approval card."""
    return frozenset(n for n, s in CATALOG.items() if s.effect == "read" and s.status not in AGENT_HIDDEN_STATUSES)


def describe_for_agent() -> str:
    """Compact per-domain op list for the tool description shown to the model."""
    domains: dict[str, list[str]] = {}
    for name in agent_ops():
        domains.setdefault(CATALOG[name].domain, []).append(name)
    return "; ".join(f"{d}: {', '.join(ops)}" for d, ops in sorted(domains.items()))


def discover_ops(source: Path = OPS_SOURCE) -> list[str]:
    """Names of all ``@op("...")`` functions declared in the editor dispatcher."""
    return [n for f in op_sources(source) for n in re.findall(r'@op\("([^"]+)"', f.read_text(encoding="utf-8"))]


def catalog_problems(discovered: list[str] | None = None) -> list[str]:
    """Rule violations; an empty list means the catalogue and the dispatcher agree."""
    names = discover_ops() if discovered is None else discovered
    problems = [f"op '{n}' has no catalogue entry" for n in names if n not in CATALOG]
    problems += [f"catalogue entry '{n}' has no @op" for n in CATALOG if n not in names]
    for spec in CATALOG.values():
        if spec.effect not in EFFECTS:
            problems.append(f"'{spec.name}': unknown effect {spec.effect}")
        if spec.status not in STATUSES:
            problems.append(f"'{spec.name}': unknown status {spec.status}")
        if spec.mutates and not spec.readback_op:
            problems.append(f"'{spec.name}' mutates state but declares no readback_op")
        if spec.readback_op and CATALOG.get(spec.readback_op, OpSpec("", "", "project")).effect != "read":
            problems.append(f"'{spec.name}': readback_op '{spec.readback_op}' is not a read op")
    return problems


def render_markdown() -> str:
    lines = ["| Op | Domain | Effect | Read-back | Status | Note |", "|---|---|---|---|---|---|"]
    for spec in sorted(CATALOG.values(), key=lambda s: (s.domain, s.name)):
        lines.append(f"| `{spec.name}` | {spec.domain} | {spec.effect} | {spec.readback_op or ''} | "
                     f"{spec.status} | {spec.note} |")
    return "\n".join(lines)
