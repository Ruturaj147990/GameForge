"""Phase 2 Targeted Retest and Holdout Evaluation Harness.

Evaluates:
1. Targeted Tasks (3 tasks where baseline lost points):
   - PH2-02: UE 5.7 Server RPC with Validation and HasAuthority
   - PH2-03: UE 5.7 GameplayAbility with CommitAbility and EndAbility
   - PH2-11: UE 5.7 BTTaskNode with NavigationSystem and EBTNodeResult::Succeeded
2. Holdout Validation Tasks (4 unseen tasks):
   - HOLD-01: UE 5.7 C++ LineTraceSingleByChannel with FCollisionQueryParams
   - HOLD-02: Unity 6 C# Event-Driven OnDamageTaken delegate and Audio subscriber
   - HOLD-03: Godot 4.3 GDScript Camera3D Lerp Follow
   - HOLD-04: Game Math Euler to Quaternion half-angle conversion

Outputs:
  reports/gameforge-27b-sft/phase2_holdout_results.csv
"""

import csv
import json
import re
import time
import urllib.request
from pathlib import Path

WORKSPACE_ROOT = Path(__file__).resolve().parents[1]
REPORTS_DIR = WORKSPACE_ROOT / "reports" / "gameforge-27b-sft"
MIRROR_REPORTS_DIR = Path("E:/GameForge/reports/gameforge-27b-sft")

for d in [REPORTS_DIR, MIRROR_REPORTS_DIR]:
    d.mkdir(parents=True, exist_ok=True)

OLLAMA_API = "http://127.0.0.1:11434/api/generate"

MODELS = [
    "gameforge-27b-sft:latest",
    "gameforge-27b-sft-candidate:latest"
]

TEST_TASKS = [
    # Targeted Retest
    {
        "id": "PH2-02",
        "category": "Targeted Retest",
        "title": "Reliable Server RPC with Validation",
        "prompt": "Write an Unreal Engine 5.7 C++ character method and RPC pair for picking up an item: AttemptPickup(AItem* Item) called on client that invokes Server_PickupItem(AItem* Item). Ensure Server_PickupItem is a reliable Server RPC with validation checking item validity and distance, and an authority check using HasAuthority() in _Implementation.",
        "rubrics": [("UFUNCTION(Server, Reliable, WithValidation)", 3), ("Server_PickupItem_Validate", 3), ("Server_PickupItem_Implementation", 2), ("HasAuthority()", 2)]
    },
    {
        "id": "PH2-03",
        "category": "Targeted Retest",
        "title": "GameplayAbility Lifecycle & Tag Checks",
        "prompt": "In Unreal Engine 5.7 C++, write the ActivateAbility method for UGA_FireWeapon: check for the gameplay tag State.Weapon.Ready, invoke CommitAbility early, spawn a projectile actor, and conclude with EndAbility(Handle, ActorInfo, ActivationInfo, true, false). Keep output focused on the method implementation.",
        "rubrics": [("CommitAbility", 3), ("EndAbility", 3), ("GameplayTag", 2), ("ActivateAbility", 2)]
    },
    {
        "id": "PH2-11",
        "category": "Targeted Retest",
        "title": "BTTask Random Reachable Point",
        "prompt": "In Unreal Engine 5.7 C++, implement UBTTask_FindPatrolLocation::ExecuteTask: obtain UNavigationSystemV1, find a random reachable point in radius using GetRandomReachablePointInRadius, store it in Blackboard, and return EBTNodeResult::Succeeded. Keep output focused on the ExecuteTask implementation.",
        "rubrics": [("ExecuteTask", 3), ("GetRandomReachablePointInRadius", 3), ("EBTNodeResult::Succeeded", 4)]
    },
    # Holdout Tasks
    {
        "id": "HOLD-01",
        "category": "Holdout Validation",
        "title": "UE 5.7 Weapon Line Trace Single",
        "prompt": "In Unreal Engine 5.7 C++, write a weapon raycast function bool FireLineTrace(APawn* ShooterPawn, float Range, FHitResult& OutHit) that executes LineTraceSingleByChannel, configures FCollisionQueryParams with AddIgnoredActor, and returns true if a blocking hit occurred.",
        "rubrics": [("LineTraceSingleByChannel", 4), ("FCollisionQueryParams", 3), ("AddIgnoredActor", 3)]
    },
    {
        "id": "HOLD-02",
        "category": "Holdout Validation",
        "title": "Unity 6 Event-Driven Health & Audio Subscriber",
        "prompt": "In Unity 6 C#, write an event-driven damage system: declare a public delegate void DamageEventHandler(float amount, GameObject attacker) and public event DamageEventHandler OnDamageTaken in a Health component, and write a separate AudioDamagePlayer script that subscribes in OnEnable and unsubscribes in OnDisable.",
        "rubrics": [("delegate void", 3), ("event DamageEventHandler", 3), ("OnEnable", 2), ("OnDisable", 2)]
    },
    {
        "id": "HOLD-03",
        "category": "Holdout Validation",
        "title": "Godot 4.3 Camera3D Smooth Lerp Follow",
        "prompt": "In Godot 4.3 GDScript, write a Camera3D script CameraFollow extending Camera3D with an @export var target: Node3D, smooth follow using global_position.lerp(target_pos, delta * speed) in _physics_process, and look_at(target.global_position).",
        "rubrics": [("Camera3D", 2), ("lerp", 3), ("_physics_process", 2), ("look_at", 3)]
    },
    {
        "id": "HOLD-04",
        "category": "Holdout Validation",
        "title": "Game Math Euler to Quaternion Trigonometric Conversion",
        "prompt": "In C++, implement a function FQuat EulerDegreesToQuat(float PitchDeg, float YawDeg, float RollDeg) that converts Euler angles in degrees into a normalized quaternion using half-angle trigonometric formulas (sin, cos of half angles) and FMath::DegreesToRadians.",
        "rubrics": [("DegreesToRadians", 3), ("cos", 3), ("sin", 2), ("FQuat", 2)]
    }
]

def query_model(model: str, prompt: str, max_tokens: int = 512) -> dict:
    payload = {
        "model": model,
        "prompt": prompt,
        "stream": False,
        "think": False,
        "options": {
            "temperature": 0.2,
            "top_p": 0.9,
            "num_predict": max_tokens,
            "stop": ["<|im_end|>", "<|endoftext|>", "### Input", "### Instruction"]
        }
    }

    t0 = time.time()
    try:
        req = urllib.request.Request(
            OLLAMA_API,
            data=json.dumps(payload).encode("utf-8"),
            headers={"Content-Type": "application/json"}
        )
        with urllib.request.urlopen(req, timeout=120) as resp:
            data = json.loads(resp.read().decode("utf-8"))
            dur = time.time() - t0
            resp_text = data.get("response", "")
            eval_count = data.get("eval_count", len(resp_text.split()))
            eval_dur_ns = data.get("eval_duration", 1)
            tps = (eval_count / (eval_dur_ns / 1e9)) if eval_dur_ns > 0 else (eval_count / dur)
            done_reason = data.get("done_reason", "unknown")
            is_truncated = done_reason == "length" or eval_count >= (max_tokens - 2)
            return {
                "text": resp_text,
                "latency_sec": round(dur, 2),
                "tps": round(tps, 2),
                "eval_count": eval_count,
                "done_reason": done_reason,
                "is_truncated": is_truncated,
                "error": None
            }
    except Exception as e:
        return {
            "text": f"ERROR: {e}",
            "latency_sec": round(time.time() - t0, 2),
            "tps": 0.0,
            "eval_count": 0,
            "done_reason": "error",
            "is_truncated": False,
            "error": str(e)
        }

def match_rubric_normalized(text: str, rubric_item: str) -> bool:
    tokens = re.findall(r"\w+|[^\w\s]", rubric_item.lower())
    if not tokens:
        return False
    pattern = r"\s*".join(re.escape(token) for token in tokens)
    return bool(re.search(pattern, text.lower()))

def score_response(text: str, rubrics: list) -> tuple:
    score = 0
    matched = []
    for kw, pts in rubrics:
        if match_rubric_normalized(text, kw):
            score += pts
            matched.append(kw)
    return score, matched

def main():
    print("=" * 80)
    print(" PHASE 2 TARGETED RETEST & HOLDOUT VALIDATION")
    print(f" Models under test: {', '.join(MODELS)}")
    print("=" * 80)

    all_rows = []
    summary_by_model = {m: {"targeted": 0, "holdout": 0, "total": 0} for m in MODELS}

    for model in MODELS:
        print(f"\n>>> Running Evaluation for: {model} <<<")
        for idx, task in enumerate(TEST_TASKS, 1):
            tid = task["id"]
            cat = task["category"]
            title = task["title"]
            prompt = task["prompt"]
            rubrics = task["rubrics"]
            max_s = sum(p for _, p in rubrics)

            res = query_model(model, prompt, max_tokens=512)
            score, matched = score_response(res["text"], rubrics)

            summary_by_model[model]["total"] += score
            if cat == "Targeted Retest":
                summary_by_model[model]["targeted"] += score
            else:
                summary_by_model[model]["holdout"] += score

            status_flag = "TRUNC" if res["is_truncated"] else "COMPLETE"
            print(f"  [{idx:02d}/07] [{tid}] ({cat[:8]}) {title:38s} -> Score: {score:02d}/{max_s:02d} | Tokens: {res['eval_count']:03d} [{status_flag}] | Speed: {res['tps']:4.1f} tps")

            all_rows.append({
                "model": model,
                "task_id": tid,
                "category": cat,
                "title": title,
                "score": score,
                "max_score": max_s,
                "percentage": round((score / max_s) * 100, 1),
                "tokens": res["eval_count"],
                "tps": res["tps"],
                "latency_sec": res["latency_sec"],
                "is_truncated": res["is_truncated"],
                "matched_rubrics": "; ".join(matched),
                "preview": res["text"][:120].replace("\n", " ") + "..."
            })

    print("\n" + "=" * 80)
    print(" SUMMARY COMPARISON")
    print("=" * 80)
    for model in MODELS:
        t_score = summary_by_model[model]["targeted"]
        h_score = summary_by_model[model]["holdout"]
        tot = summary_by_model[model]["total"]
        print(f"  {model:36s} -> Targeted: {t_score:02d}/30 | Holdout: {h_score:02d}/40 | Overall: {tot:02d}/70 ({(tot/70)*100:.1f}%)")

    # Save to CSV
    csv_fields = [
        "model", "task_id", "category", "title", "score", "max_score",
        "percentage", "tokens", "tps", "latency_sec", "is_truncated",
        "matched_rubrics", "preview"
    ]
    csv_path_w = REPORTS_DIR / "phase2_holdout_results.csv"
    csv_path_m = MIRROR_REPORTS_DIR / "phase2_holdout_results.csv"

    for cp in [csv_path_w, csv_path_m]:
        with open(cp, "w", newline="", encoding="utf-8") as f:
            writer = csv.DictWriter(f, fieldnames=csv_fields)
            writer.writeheader()
            writer.writerows(all_rows)

    print(f"\nResults successfully saved to {csv_path_w} and {csv_path_m}")

if __name__ == "__main__":
    main()
