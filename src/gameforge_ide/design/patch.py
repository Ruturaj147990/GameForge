"""GDS JSON Patch implementation (RFC 6902 subset) for living projects (WI-8.1).

Supports `add`, `remove`, and `replace` operations on GameDesignSpec hierarchies.
Enforces protected paths, maintains schema validation, increments revisions,
and provides dry-run validation and natural language summary generation.
"""
from __future__ import annotations

import copy
import json
import re
from typing import Any, Callable, Dict, List, Literal, Optional, Tuple, Union

from pydantic import BaseModel, Field

from .gds import GameDesignSpec

PROTECTED_PATHS = {
    "/meta/gds_id",
    "/meta/created_at",
    "/meta/schema_version",
}


class PatchError(Exception):
    """Raised when a patch cannot be applied or results in an invalid spec."""

    def __init__(self, message: str, op_index: Optional[int] = None, path: Optional[str] = None):
        super().__init__(message)
        self.message = message
        self.op_index = op_index
        self.path = path

    def __str__(self) -> str:
        loc = f" (op {self.op_index} at {self.path})" if self.op_index is not None else ""
        return f"PatchError{loc}: {self.message}"


class ProposedPatch(BaseModel):
    """Result of patch generation from natural language or shortcut rules."""
    ops: List[Dict[str, Any]] = Field(default_factory=list)
    summary: str = ""
    questions: List[str] = Field(default_factory=list)
    status: Literal["OK", "NEEDS_INPUT"] = "OK"


def _unescape_token(token: str) -> str:
    return token.replace("~1", "/").replace("~0", "~")


def _parse_path(path: str) -> List[Union[str, int]]:
    """Parse RFC 6902 JSON Pointer into navigation tokens."""
    if not path.startswith("/"):
        raise ValueError(f"JSON Patch path must start with '/': {path}")
    raw_tokens = path[1:].split("/")
    tokens: List[Union[str, int]] = []
    for t in raw_tokens:
        tok = _unescape_token(t)
        if tok.isdigit():
            tokens.append(int(tok))
        else:
            tokens.append(tok)
    return tokens


def _is_protected(path: str) -> bool:
    for prot in PROTECTED_PATHS:
        if path == prot or path.startswith(f"{prot}/"):
            return True
    return False


def _navigate(root: Any, tokens: List[Union[str, int]]) -> Tuple[Any, Union[str, int]]:
    """Navigate to the parent container of the target token."""
    cur = root
    for t in tokens[:-1]:
        if isinstance(cur, dict):
            if str(t) not in cur:
                raise KeyError(f"Key {t!r} not found in dict")
            cur = cur[str(t)]
        elif isinstance(cur, list):
            if not isinstance(t, int) or t < 0 or t >= len(cur):
                raise IndexError(f"Index {t} out of range (len={len(cur)})")
            cur = cur[t]
        else:
            raise TypeError(f"Cannot navigate into scalar {type(cur).__name__}")
    return cur, tokens[-1]


def apply_op(root: Dict[str, Any], op: Dict[str, Any], op_index: int = 0) -> None:
    """Apply a single JSON Patch operation (`add`, `remove`, `replace`) in-place."""
    action = op.get("op")
    path = op.get("path", "")
    if not isinstance(path, str) or not path.startswith("/"):
        raise PatchError(f"Invalid path {path!r}", op_index=op_index, path=path)

    if _is_protected(path):
        raise PatchError(f"Path {path!r} is protected and cannot be modified", op_index=op_index, path=path)

    tokens = _parse_path(path)
    if not tokens:
        raise PatchError("Cannot modify root document directly", op_index=op_index, path=path)

    try:
        parent, target = _navigate(root, tokens)
    except (KeyError, IndexError, TypeError) as err:
        raise PatchError(f"Navigation failed for path {path!r}: {err}", op_index=op_index, path=path) from err

    if action == "add":
        val = copy.deepcopy(op.get("value"))
        if isinstance(parent, dict):
            parent[str(target)] = val
        elif isinstance(parent, list):
            if target == "-" or target == len(parent):
                parent.append(val)
            elif isinstance(target, int) and 0 <= target <= len(parent):
                parent.insert(target, val)
            else:
                raise PatchError(f"Invalid list index {target} for add (len={len(parent)})", op_index=op_index, path=path)
        else:
            raise PatchError(f"Parent at {path} is not a container", op_index=op_index, path=path)

    elif action == "remove":
        if isinstance(parent, dict):
            key = str(target)
            if key not in parent:
                raise PatchError(f"Key {key!r} does not exist for remove", op_index=op_index, path=path)
            del parent[key]
        elif isinstance(parent, list):
            if not isinstance(target, int) or target < 0 or target >= len(parent):
                raise PatchError(f"Index {target} out of range for remove (len={len(parent)})", op_index=op_index, path=path)
            del parent[target]
        else:
            raise PatchError(f"Parent at {path} is not a container", op_index=op_index, path=path)

    elif action == "replace":
        val = copy.deepcopy(op.get("value"))
        if isinstance(parent, dict):
            key = str(target)
            parent[key] = val
        elif isinstance(parent, list):
            if not isinstance(target, int) or target < 0 or target >= len(parent):
                raise PatchError(f"Index {target} out of range for replace (len={len(parent)})", op_index=op_index, path=path)
            parent[target] = val
        else:
            raise PatchError(f"Parent at {path} is not a container", op_index=op_index, path=path)
    else:
        raise PatchError(f"Unsupported operation {action!r} (supported: add, remove, replace)", op_index=op_index, path=path)


def apply_patch(gds: GameDesignSpec, ops: List[Dict[str, Any]]) -> GameDesignSpec:
    """Apply a sequence of JSON Patch operations to a GameDesignSpec.

    Returns a new validated GameDesignSpec with bumped revision and generator="patch".
    Raises PatchError on any failure.
    """
    data = copy.deepcopy(gds.model_dump())
    for idx, op in enumerate(ops):
        apply_op(data, op, op_index=idx)

    # Bump revision and set generator
    curr_rev = gds.meta.revision or 1
    data["meta"]["revision"] = curr_rev + 1
    data["meta"]["generator"] = "patch"

    try:
        patched = GameDesignSpec.model_validate(data)
    except Exception as exc:
        raise PatchError(f"Patched GDS failed schema validation: {exc}", op_index=len(ops) - 1) from exc

    return patched


def summarize_patch(gds: GameDesignSpec, ops: List[Dict[str, Any]]) -> List[str]:
    """Generate human-readable sentences describing the effect of ops on the GDS."""
    sentences: List[str] = []
    gds_data = gds.model_dump()

    for op in ops:
        action = op.get("op")
        path = op.get("path", "")
        val = op.get("value")

        # Speed scaling summary
        m_speed = re.search(r"/entities/(\d+)/props/(move_speed|patrol_speed|speed)", path)
        if m_speed:
            idx = int(m_speed.group(1))
            prop = m_speed.group(2)
            if idx < len(gds.entities):
                ent = gds.entities[idx]
                old_val = getattr(ent.props, prop, None) or (ent.props.model_dump().get(prop) if hasattr(ent.props, "model_dump") else ent.props.get(prop))
                sentences.append(f"{ent.entity_id.capitalize()}: {prop} {old_val} -> {val}")
                continue

        # Lighting
        if path == "/scene/lighting":
            old_light = gds.scene.lighting.value if hasattr(gds.scene.lighting, "value") else str(gds.scene.lighting)
            sentences.append(f"Lighting: changed from {old_light} to {val}")
            continue

        # Title
        if path == "/overview/title":
            sentences.append(f"Title: renamed from '{gds.overview.title}' to '{val}'")
            continue

        # Entities add/remove
        if path == "/entities/-" or (path.startswith("/entities/") and action == "add"):
            ent_id = val.get("entity_id", "entity") if isinstance(val, dict) else "entity"
            kind = val.get("kind", "") if isinstance(val, dict) else ""
            sentences.append(f"Added {kind or 'entity'} '{ent_id}'")
            continue

        if path.startswith("/entities/") and action == "remove":
            parts = _parse_path(path)
            if len(parts) == 2 and isinstance(parts[1], int) and parts[1] < len(gds.entities):
                ent = gds.entities[parts[1]]
                sentences.append(f"Removed {ent.kind.value} '{ent.entity_id}'")
                continue

        # Levels add
        if path == "/scene/levels/-" or (path.startswith("/scene/levels/") and action == "add"):
            lvl_id = val.get("level_id", "level") if isinstance(val, dict) else "level"
            sentences.append(f"Added level '{lvl_id}'")
            continue

        # Generic fallback
        sentences.append(f"{action.capitalize()} {path}")

    return sentences


def propose_patch(
    gds: GameDesignSpec,
    request: str,
    complete_json: bool = False,
    model_caller: Optional[Callable[[str, str], str]] = None,
) -> ProposedPatch:
    """Propose a patch from a user request.

    Tries deterministic rules first. If no rule matches and a model caller is
    provided, delegates to the model with dry-run verification.
    """
    from .patch_rules import match_deterministic_rule

    # 1. Deterministic shortcuts
    shortcut = match_deterministic_rule(gds, request)
    if shortcut is not None:
        # Dry-run apply
        try:
            apply_patch(gds, shortcut.ops)
            return shortcut
        except PatchError as pe:
            return ProposedPatch(
                ops=[],
                summary=f"Rule generated invalid patch: {pe}",
                questions=["Please specify the exact parameters for this change."],
                status="NEEDS_INPUT",
            )

    # 2. Model delegation if available
    if model_caller is not None:
        trimmed_gds = _select_relevant_sections(gds, request)
        prompt = (
            f"Current GDS section:\n{json.dumps(trimmed_gds, indent=2)}\n\n"
            f"User request: {request}\n"
            "Return JSON format:\n"
            '{"ops": [{"op": "add|remove|replace", "path": "/...", "value": ...}], "summary": "...", "questions": []}'
        )
        try:
            resp_str = model_caller("design", prompt)
            parsed = json.loads(resp_str)
            ops = parsed.get("ops", [])
            summary = parsed.get("summary", "")
            questions = parsed.get("questions", [])
            # Dry-run apply
            apply_patch(gds, ops)
            return ProposedPatch(ops=ops, summary=summary, questions=questions, status="OK")
        except Exception as exc:
            return ProposedPatch(
                ops=[],
                summary=f"Model proposed patch failed verification: {exc}",
                questions=["Could not apply the requested change safely. Please refine your request."],
                status="NEEDS_INPUT",
            )

    return ProposedPatch(
        ops=[],
        summary=f"Could not automatically interpret change request: {request!r}",
        questions=["What specific entity, rule, or setting would you like to change?"],
        status="NEEDS_INPUT",
    )


def _select_relevant_sections(gds: GameDesignSpec, request: str) -> Dict[str, Any]:
    """Trim GDS to sections relevant to keywords in the user request."""
    req_lower = request.lower()
    full = gds.model_dump()
    result: Dict[str, Any] = {"meta": full.get("meta", {})}

    if any(k in req_lower for k in ("guard", "speed", "enemy", "pickup", "relic", "player", "actor", "entity", "hazard", "door", "key")):
        result["entities"] = full.get("entities", [])
        result["rules"] = full.get("rules", [])
        result["goals"] = full.get("goals", {})

    if any(k in req_lower for k in ("light", "night", "day", "dusk", "fog", "level", "scene", "biome")):
        result["scene"] = full.get("scene", {})

    if any(k in req_lower for k in ("win", "lose", "goal", "objective")):
        result["goals"] = full.get("goals", {})
        result["rules"] = full.get("rules", [])

    if len(result) == 1:
        # Default compact overview + entities
        result["overview"] = full.get("overview", {})
        result["entities"] = full.get("entities", [])

    return result
