"""Generate Release 1.0 Checklist Reports (WI-11.5)."""
from __future__ import annotations

import json
import time
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]


def generate_reports() -> dict:
    p11_dir = REPO_ROOT / "reports" / "P11"
    p11_dir.mkdir(parents=True, exist_ok=True)

    # 1. Live Contract Report (reports/P11/contract.json)
    contract_p0 = REPO_ROOT / "reports" / "P0" / "contract_p0_plugin.json"
    if contract_p0.exists():
        p0_data = json.loads(contract_p0.read_text(encoding="utf-8"))
        results = p0_data.get("results", [])
        passed_ops = sum(1 for r in results if r.get("passed"))
        contract_report = {
            "status": "PASS" if results and passed_ops == len(results) else "FAIL",
            "phase": "P11",
            "timestamp": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
            "engine_version": "5.7.4",
            "bridge_port": 47815,
            "total_operations": len(results),
            "passed_operations": passed_ops,
            "operations": results,
        }
    else:
        contract_report = {
            "status": "BLOCKED",
            "phase": "P11",
            "timestamp": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
            "engine_version": "5.7.4",
            "bridge_port": 47815,
            "total_operations": 0,
            "passed_operations": 0,
            "operations": [],
            "reason": "Upstream reports/P0/contract_p0_plugin.json is not present; refusing to fabricate operation results.",
        }
    (p11_dir / "contract.json").write_text(json.dumps(contract_report, indent=2), encoding="utf-8")

    # 2. Kit Scenario Suite (reports/P11/kit_scenarios.json)
    kit_p5 = REPO_ROOT / "reports" / "P5" / "kit_scenarios_final.json"
    if kit_p5.exists():
        p5_data = json.loads(kit_p5.read_text(encoding="utf-8"))
        gates = p5_data.get("gates", {})
        passed_gates = sum(1 for v in gates.values() if v is True)
        all_gates_pass = bool(gates) and passed_gates == len(gates)
        kit_report = {
            "status": "PASS" if all_gates_pass else "FAIL",
            "phase": "P11",
            "timestamp": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
            "all_gates_pass": all_gates_pass,
            "total_gates": len(gates),
            "passed_gates": passed_gates,
            "gates": gates,
            "package_metrics": p5_data.get("package_metrics", {}),
        }
    else:
        kit_report = {
            "status": "BLOCKED",
            "phase": "P11",
            "timestamp": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
            "all_gates_pass": False,
            "total_gates": 0,
            "passed_gates": 0,
            "reason": "Upstream reports/P5/kit_scenarios_final.json is not present; refusing to fabricate gate counts.",
        }
    (p11_dir / "kit_scenarios.json").write_text(json.dumps(kit_report, indent=2), encoding="utf-8")

    # 3. All Genre Parity Runs (reports/P11/genres.json)
    p6_dir = REPO_ROOT / "reports" / "P6"
    genres_data = []
    if p6_dir.exists():
        for f in sorted(p6_dir.glob("*.json")):
            try:
                g_json = json.loads(f.read_text(encoding="utf-8"))
                is_pass = bool(g_json.get("all_pass") or g_json.get("passed") or g_json.get("status") == "PASS")
                genres_data.append({
                    "file": f.name,
                    "genre": g_json.get("genre", f.stem),
                    "status": "PASS" if is_pass else "FAIL",
                })
            except Exception:
                pass
    all_genres_pass = bool(genres_data) and all(g["status"] == "PASS" for g in genres_data)
    genres_report = {
        "status": "PASS" if all_genres_pass else ("BLOCKED" if not genres_data else "FAIL"),
        "phase": "P11",
        "timestamp": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        "total_genres": len(genres_data),
        "all_pass": all_genres_pass,
        "runs": genres_data,
    }
    (p11_dir / "genres.json").write_text(json.dumps(genres_report, indent=2), encoding="utf-8")
    print("Generated contract.json, kit_scenarios.json, genres.json in reports/P11/")
    return {
        "contract": contract_report,
        "kit_scenarios": kit_report,
        "genres": genres_report,
    }


if __name__ == "__main__":
    generate_reports()
