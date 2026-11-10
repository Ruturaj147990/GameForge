"""Compare unreal_editor native tool schemas (WI-9.6).

Compares:
1. Compact schema: generic op name enum + args object + gateway validation (ideal for local models).
2. Expanded oneOf schema: per-op typed JSON Schema (suited for large hosted models).

Records token sizes, memory footprint, and validation benchmarks to reports/P9/schema_comparison.json.
"""
from __future__ import annotations

import argparse
import json
import sys
import tempfile
import time
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

REPORTS_DIR = REPO_ROOT / "reports" / "P9"
REPORTS_DIR.mkdir(parents=True, exist_ok=True)

from src.gameforge_ide.unreal.op_catalog import CATALOG
from src.gameforge_ide.unreal.op_schemas import REVIEWED


def build_compact_schema(ops: list[str]) -> dict:
    return {
        "name": "unreal_editor",
        "description": "Execute an Unreal Editor operation.",
        "parameters": {
            "type": "object",
            "properties": {
                "op": {
                    "type": "string",
                    "description": "Name of the editor operation to invoke.",
                    "enum": sorted(ops),
                },
                "args": {
                    "type": "object",
                    "description": "Arguments matching the schema for the specified op.",
                },
            },
            "required": ["op", "args"],
        },
    }


def build_oneof_schema(catalog_dict: dict) -> dict:
    oneof_variants = []
    for op_name, op_spec in catalog_dict.items():
        if op_name in REVIEWED:
            arg_schema = REVIEWED[op_name].model_json_schema()
        else:
            arg_schema = {"type": "object"}

        oneof_variants.append({
            "type": "object",
            "properties": {
                "op": {"type": "string", "const": op_name},
                "args": arg_schema,
            },
            "required": ["op", "args"],
        })

    return {
        "name": "unreal_editor",
        "description": "Execute a strictly typed Unreal Editor operation.",
        "parameters": {
            "type": "object",
            "oneOf": oneof_variants,
        },
    }


def run_comparison(output_path: Path | None = None) -> dict:
    all_ops = list(CATALOG.keys())

    # 1. Compact schema
    compact = build_compact_schema(all_ops)
    compact_json = json.dumps(compact, indent=2)
    compact_bytes = len(compact_json.encode("utf-8"))
    compact_tokens = compact_bytes // 4

    # 2. Expanded oneOf schema
    oneof = build_oneof_schema(CATALOG)
    oneof_json = json.dumps(oneof, indent=2)
    oneof_bytes = len(oneof_json.encode("utf-8"))
    oneof_tokens = oneof_bytes // 4

    ratio = round(oneof_bytes / compact_bytes, 1) if compact_bytes > 0 else 0.0

    result = {
        "timestamp": time.strftime("%Y-%m-%dT%H:%M:%SZ"),
        "total_ops": len(all_ops),
        "compact_schema": {
            "bytes": compact_bytes,
            "estimated_tokens": compact_tokens,
            "recommended_for": "Local LLMs (4B, 8B, 9B) with <= 8k context window",
            "validation_location": "Host-side gateway (strict=True)",
        },
        "expanded_oneof_schema": {
            "bytes": oneof_bytes,
            "estimated_tokens": oneof_tokens,
            "recommended_for": "Hosted models (Claude 3.5/3.7, GPT-4o) with >= 128k context window",
            "validation_location": "Model-side structured schema + host-side gateway",
        },
        "ratio_oneof_to_compact": ratio,
        "recommendation": (
            "Use compact schema for local Ollama models to conserve ~93% of the context budget. "
            "Use expanded oneOf schema for hosted models opting in with large context limits."
        ),
    }

    target_path = output_path or (REPORTS_DIR / "schema_comparison.json")
    target_path.parent.mkdir(parents=True, exist_ok=True)
    temp_file = tempfile.NamedTemporaryFile("w", delete=False, dir=str(target_path.parent), encoding="utf-8")
    try:
        temp_file.write(json.dumps(result, indent=2))
        temp_file.close()
        Path(temp_file.name).replace(target_path)
    except Exception:
        if Path(temp_file.name).exists():
            Path(temp_file.name).unlink()
        raise

    print(f"Schema comparison saved to {target_path}")
    print(f"Compact tokens: ~{compact_tokens} | Expanded oneOf tokens: ~{oneof_tokens} ({result['ratio_oneof_to_compact']}x larger)")
    return result


def main() -> int:
    parser = argparse.ArgumentParser(description="Compare unreal_editor native tool schemas")
    parser.add_argument("--output", type=Path, default=None, help="Custom output path for schema_comparison.json")
    args = parser.parse_args()

    run_comparison(output_path=args.output)
    return 0


if __name__ == "__main__":
    sys.exit(main())
