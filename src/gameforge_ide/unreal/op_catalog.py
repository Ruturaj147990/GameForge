"""Declarative catalogue of the in-editor operations exposed by ``gameforge_ops.py`` (roadmap AD-1).

Every ``@op`` in the editor dispatcher must have an entry here. Ops that change project or runtime state must
name a read-only ``readback_op`` that can confirm the change; ``tests/unit/test_op_catalog.py`` enforces both
rules, and ``scripts/gen_op_coverage.py`` renders the catalogue as Markdown.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from pathlib import Path

OPS_SOURCE = Path(__file__).parent / "GameForge" / "Content" / "Python" / "gameforge_ops.py"

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
    *_ops("level", "read", "actors_in_level"),
    *_ops("level", "project", "spawn_actor delete_actor set_actor_property new_level load_level", "actors_in_level"),
    *_ops("viewport", "artifact", "viewport_screenshot"),
    *_ops("viewport", "view", "set_viewport_camera"),
    *_ops("pie", "read", "pie_status pie_character_diagnostics"),
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
    *_ops("gameplay", "read", "gameplay_get_state"),
    *_ops("gameplay", "runtime", "gameplay_modify_state", "gameplay_get_state"),
    *_ops("world", "read", "procedural_world_inspect world_generation_digest"),
    *_ops("world", "project", "landscape_create spline_create_road foliage_scatter landmark_spawn",
          "procedural_world_inspect"),
    *_ops("pcg", "read", "pcg_inspect"),
    *_ops("pcg", "project", "pcg_scatter", "pcg_inspect", "PARTIAL", "Grid sampling only; no surface sampler yet."),
    *_ops("navigation", "read", "nav_find_path"),
    *_ops("navigation", "project", "nav_rebuild", "nav_find_path"),
    *_ops("character", "read", "character_inspect_skeletal_mesh character_measure_deformation"),
    *_ops("character", "project", "character_import_skeletal_mesh", "character_inspect_skeletal_mesh"),
    *_ops("character", "project", "character_spawn_preview", "actors_in_level"),
    *_ops("animation", "read", "anim_inspect_sequence anim_inspect_blueprint anim_sample_bone_pose "
          "anim_locomotion_test_result"),
    *_ops("animation", "project", "anim_create_locomotion_blueprint", "anim_inspect_blueprint"),
    *_ops("animation", "project", "anim_import_motion_clip", "anim_sample_bone_pose"),
    *_ops("animation", "project", "anim_ik_retarget", "anim_sample_bone_pose", "PARTIAL",
          "Genuine IK Retargeter path; per-bone track proof still owed (roadmap WP-A)."),
    *_ops("animation", "project", "anim_retarget_sequence", "anim_inspect_sequence", "LEGACY",
          "SetSkeleton copy, not a retarget; never cite as retarget evidence."),
    *_ops("animation", "runtime", "anim_start_locomotion_test", "anim_locomotion_test_result"),
]}


def discover_ops(source: Path = OPS_SOURCE) -> list[str]:
    """Names of all ``@op("...")`` functions declared in the editor dispatcher."""
    return re.findall(r'@op\("([^"]+)"', source.read_text(encoding="utf-8"))


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
