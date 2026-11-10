import argparse
import json
import sys
import tempfile
import time
import urllib.request
from pathlib import Path
from typing import Dict, Any

REPO_ROOT = Path(__file__).resolve().parents[2]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

REPORTS_DIR = Path(r"E:\GameForge\reports\gameforge-27b\acceptance")
REPO_REPORTS_DIR = REPO_ROOT / "reports" / "gameforge-27b" / "acceptance"

MODELS = ["qwen3.8:27b-q4_K_M", "gameforge-27b"]

REGRESSION_TASKS = [
    {
        "id": "REG-01",
        "category": "Unreal C++ Replication & Authority",
        "prompt": "Write a complete Unreal Engine 5.7 C++ ActorComponent called UHealthComponent with replicated health, OnRep_Health, TakeDamage authority check, clamping between 0 and MaxHealth, and rejecting negative damage.",
        "rubrics": [
            ("UCLASS(ClassGroup=", 1),
            ("GENERATED_BODY()", 1),
            ("ReplicatedUsing = OnRep_Health", 2),
            ("GetOwner()->HasAuthority()", 2),
            ("FMath::Clamp", 1),
            ("Damage <= 0", 1),
            ("GetLifetimeReplicatedProps", 1),
            ("DOREPLIFETIME", 1)
        ],
        "deprecated_patterns": ["DOREPLIFETIME_WITH_CONDITION", "bReplicateMovement = true in component"]
    },
    {
        "id": "REG-02",
        "category": "Unreal RPC Validation & Security",
        "prompt": "In Unreal Engine 5.7 C++, declare and implement a server-reliable RPC called Server_FireWeapon with validation. Ensure it checks ammo count and has an authority check in implementation.",
        "rubrics": [
            ("UFUNCTION(Server, Reliable, WithValidation)", 3),
            ("Server_FireWeapon_Validate", 3),
            ("Server_FireWeapon_Implementation", 3),
            ("bool", 1)
        ],
        "deprecated_patterns": ["UFUNCTION(Server, Reliable, WithValidation) void Server_FireWeapon_Implementation"]
    },
    {
        "id": "REG-03",
        "category": "Unreal Memory & TObjectPtr",
        "prompt": "Declare a UGameInstanceSubsystem in UE 5.7 C++ that caches player inventory UDataAsset objects. Use modern UE 5.7 TObjectPtr member pointers and explain why raw pointers are discouraged.",
        "rubrics": [
            ("UGameInstanceSubsystem", 3),
            ("TObjectPtr<", 4),
            ("UPROPERTY(", 2),
            ("access tracking", 1)
        ],
        "deprecated_patterns": ["UDataAsset* InventoryAsset;"]
    },
    {
        "id": "REG-04",
        "category": "Unreal Delegates & Events",
        "prompt": "Write a dynamic multicast delegate declaration in UE 5.7 for OnPlayerDied taking AActor* Killer as a parameter, exposed to Blueprints, and show broadcasting it.",
        "rubrics": [
            ("DECLARE_DYNAMIC_MULTICAST_DELEGATE_OneParam", 4),
            ("BlueprintAssignable", 3),
            (".Broadcast(", 3)
        ],
        "deprecated_patterns": []
    },
    {
        "id": "REG-05",
        "category": "Gameplay Ability System",
        "prompt": "Provide the UE 5.7 C++ macro block (ATTRIBUTE_ACCESSORS) on an AttributeSet for a Health attribute, and show PreAttributeChange clamping.",
        "rubrics": [
            ("ATTRIBUTE_ACCESSORS", 3),
            ("GAMEPLAYATTRIBUTE_VALUE_GETTER", 2),
            ("GAMEPLAYATTRIBUTE_VALUE_SETTER", 2),
            ("PreAttributeChange", 3)
        ],
        "deprecated_patterns": []
    },
    {
        "id": "REG-06",
        "category": "Collision & Sweep",
        "prompt": "Write a UE 5.7 C++ line trace function from camera forward vector that ignores the calling Actor and queries ECC_Visibility using FCollisionQueryParams.",
        "rubrics": [
            ("LineTraceSingleByChannel", 3),
            ("ECC_Visibility", 2),
            ("FCollisionQueryParams", 3),
            ("AddIgnoredActor", 2)
        ],
        "deprecated_patterns": []
    },
    {
        "id": "REG-07",
        "category": "AI & Behavior Trees",
        "prompt": "Write a custom UBTTaskNode in UE 5.7 C++ that executes an attack and returns EBTNodeResult::Succeeded, ensuring TickTask is disabled.",
        "rubrics": [
            ("UBTTaskNode", 3),
            ("ExecuteTask", 3),
            ("EBTNodeResult::Succeeded", 3),
            ("bNotifyTick = false", 1)
        ],
        "deprecated_patterns": []
    },
    {
        "id": "REG-08",
        "category": "Network Optimization",
        "prompt": "Implement GetLifetimeReplicatedProps in UE 5.7 for an Actor with two variables: SecretScore replicated COND_OwnerOnly, and Health replicated to all.",
        "rubrics": [
            ("GetLifetimeReplicatedProps", 3),
            ("DOREPLIFETIME_CONDITION", 3),
            ("COND_OwnerOnly", 2),
            ("DOREPLIFETIME", 2)
        ],
        "deprecated_patterns": []
    },
    {
        "id": "REG-09",
        "category": "Enhanced Input System",
        "prompt": "Show how to bind an Enhanced Input Action (IA_Jump) in UE 5.7 Character C++ using UEnhancedInputComponent and ETriggerEvent::Triggered.",
        "rubrics": [
            ("UEnhancedInputComponent", 3),
            ("BindAction", 3),
            ("ETriggerEvent::Triggered", 3),
            ("ETriggerEvent::Started", 1)
        ],
        "deprecated_patterns": ["InputComponent->BindAction"]
    },
    {
        "id": "REG-10",
        "category": "Performance & Tick Avoidance",
        "prompt": "Explain why disabling Tick is recommended in UE 5.7 C++ and show how to set up a recurring 1.0s timer using GetWorldTimerManager().",
        "rubrics": [
            ("PrimaryActorTick.bCanEverTick = false", 3),
            ("GetWorldTimerManager()", 4),
            ("SetTimer", 3)
        ],
        "deprecated_patterns": ["GetWorld()->GetTimerManager()"]
    },
    {
        "id": "REG-11",
        "category": "Godot 4 GDScript 2.0",
        "prompt": "Write a Godot 4 GDScript for a 3D CharacterBody3D implementing gravity, jump, velocity calculation, and move_and_slide(). Use modern Godot 4 syntax.",
        "rubrics": [
            ("extends CharacterBody3D", 3),
            ("move_and_slide()", 3),
            ("is_on_floor()", 2),
            ("velocity", 2)
        ],
        "deprecated_patterns": ["move_and_slide(velocity)", "yield("]
    },
    {
        "id": "REG-12",
        "category": "Unity ECS / DOTS",
        "prompt": "Write a Unity 6 DOTS IJobEntity C# burst-compiled job that modifies a Health component based on Damage.",
        "rubrics": [
            ("IJobEntity", 3),
            ("BurstCompile", 3),
            ("ref Health", 2),
            ("in Damage", 2)
        ],
        "deprecated_patterns": ["MonoBehaviour"]
    },
    {
        "id": "REG-13",
        "category": "UEFN Verse Concurrency",
        "prompt": "Write a UEFN Verse snippet using concurrency blocks (sync or race) to wait for either an elimination event or a 30-second timeout.",
        "rubrics": [
            ("race:", 4),
            ("block:", 2),
            ("Sleep(", 2),
            ("await", 2)
        ],
        "deprecated_patterns": []
    },
    {
        "id": "REG-14",
        "category": "Game Mathematics - Quaternions",
        "prompt": "Explain the difference between Euler angles and Quaternions in 3D game engines, and write C++ pseudocode for Slerp interpolation between two rotations.",
        "rubrics": [
            ("gimbal lock", 3),
            ("dot product", 2),
            ("Slerp", 3),
            ("quaternion", 2)
        ],
        "deprecated_patterns": []
    },
    {
        "id": "REG-15",
        "category": "Game Mathematics - PID Controller",
        "prompt": "Implement a float PID controller in C++ with Proportional, Integral, and Derivative terms, anti-windup clamping, and delta time.",
        "rubrics": [
            ("error = target - current", 2),
            ("integral +=", 2),
            ("derivative =", 2),
            ("clamp", 2),
            ("dt", 2)
        ],
        "deprecated_patterns": []
    }
]

def query_ollama(model: str, prompt: str) -> Dict[str, Any]:
    url = "http://127.0.0.1:11434/api/generate"
    payload = {
        "model": model,
        "prompt": prompt,
        "stream": False,
        "think": False,
        "options": {
            "temperature": 0.2,
            "top_p": 0.9,
            "num_predict": 400
        }
    }
    req = urllib.request.Request(
        url,
        data=json.dumps(payload).encode("utf-8"),
        headers={"Content-Type": "application/json"}
    )
    t0 = time.time()
    try:
        with urllib.request.urlopen(req, timeout=180) as resp:
            data = json.loads(resp.read().decode("utf-8"))
        elapsed = time.time() - t0
        eval_count = data.get("eval_count", 0)
        eval_duration_ns = data.get("eval_duration", 1)
        prompt_eval_duration_ns = data.get("prompt_eval_duration", 0)
        tok_per_sec = eval_count / (eval_duration_ns / 1e9) if eval_duration_ns > 0 else 0
        ttft = prompt_eval_duration_ns / 1e9
        return {
            "success": True,
            "response": data.get("response", ""),
            "elapsed_seconds": elapsed,
            "eval_count": eval_count,
            "tokens_per_second": tok_per_sec,
            "ttft_seconds": ttft
        }
    except Exception as e:
        return {
            "success": False,
            "error": str(e),
            "elapsed_seconds": time.time() - t0
        }

def unload_model(model: str) -> None:
    try:
        req = urllib.request.Request(
            "http://127.0.0.1:11434/api/generate",
            data=json.dumps({"model": model, "keep_alive": 0}).encode("utf-8"),
            headers={"Content-Type": "application/json"}
        )
        with urllib.request.urlopen(req, timeout=10) as _:
            pass
    except Exception:
        pass


def evaluate_response(response_text: str, task: Dict[str, Any]) -> Dict[str, Any]:
    score = 0
    rubric_results = []
    for pattern, pts in task["rubrics"]:
        found = pattern.lower() in response_text.lower()
        if found:
            score += pts
        rubric_results.append({
            "pattern": pattern,
            "points": pts,
            "matched": found
        })
    
    deprecated_matches = []
    for dep in task.get("deprecated_patterns", []):
        if dep.lower() in response_text.lower():
            deprecated_matches.append(dep)
            score = max(0, score - 2)

    return {
        "score": min(10, score),
        "max_score": 10,
        "rubric_results": rubric_results,
        "deprecated_matches": deprecated_matches
    }

def run_suite() -> int:
    print("=" * 80)
    print(" GAMEFORGE-27B INDEPENDENT REGRESSION SUITE (15 TASKS)")
    print(f" Target Models: {MODELS}")
    print("=" * 80)

    results = {
        "timestamp": time.time(),
        "total_tasks": len(REGRESSION_TASKS),
        "models": {}
    }

    for model_name in MODELS:
        print(f"\n>>> EVALUATING MODEL: {model_name} <<<")
        model_results = {
            "tasks": [],
            "total_score": 0,
            "max_possible_score": len(REGRESSION_TASKS) * 10,
            "mean_tokens_per_sec": 0.0,
            "mean_ttft_seconds": 0.0,
            "total_deprecated_detected": 0
        }
        tok_rates = []
        ttft_rates = []

        for task in REGRESSION_TASKS:
            t_id = task["id"]
            cat = task["category"]
            prompt = task["prompt"]
            print(f"  [{t_id}] {cat}...", end="", flush=True)

            res = query_ollama(model_name, prompt)
            if not res["success"]:
                print(f" FAILED: {res.get('error')}")
                continue

            eval_res = evaluate_response(res["response"], task)
            score = eval_res["score"]
            model_results["total_score"] += score
            model_results["total_deprecated_detected"] += len(eval_res["deprecated_matches"])
            tok_rates.append(res["tokens_per_second"])
            ttft_rates.append(res["ttft_seconds"])

            print(f" Score: {score}/10 | {res['tokens_per_second']:.1f} tps | TTFT: {res['ttft_seconds']:.2f}s")

            model_results["tasks"].append({
                "task_id": t_id,
                "category": cat,
                "score": score,
                "rubric_results": eval_res["rubric_results"],
                "deprecated_matches": eval_res["deprecated_matches"],
                "tokens_generated": res["eval_count"],
                "tokens_per_second": res["tokens_per_second"],
                "ttft_seconds": res["ttft_seconds"],
                "response_sample": res["response"][:300] + ("..." if len(res["response"]) > 300 else "")
            })

        if tok_rates:
            model_results["mean_tokens_per_sec"] = sum(tok_rates) / len(tok_rates)
            model_results["mean_ttft_seconds"] = sum(ttft_rates) / len(ttft_rates)

        results["models"][model_name] = model_results
        pct = (model_results["total_score"] / model_results["max_possible_score"]) * 100
        print(f"Model {model_name} Finished: {model_results['total_score']}/{model_results['max_possible_score']} ({pct:.1f}%) | Avg Throughput: {model_results['mean_tokens_per_sec']:.1f} tps")
        unload_model(model_name)

    target_reports = [REPORTS_DIR, REPO_REPORTS_DIR]
    for r_dir in target_reports:
        try:
            r_dir.mkdir(parents=True, exist_ok=True)
            out_file = r_dir / "independent_regression_results.json"
            temp_out = out_file.with_suffix(".tmp")
            temp_out.write_text(json.dumps(results, indent=2), encoding="utf-8")
            temp_out.replace(out_file)
            print(f"Saved regression results to {out_file}")
        except Exception as e:
            print(f"Warning: Failed to write results to {r_dir}: {e}", file=sys.stderr)

    return 0


def main() -> int:
    parser = argparse.ArgumentParser(description="GameForge 27B Independent Regression Suite")
    parser.add_argument("--dry-run", action="store_true", help="Validate tasks without querying models")
    args = parser.parse_args()

    if args.dry_run:
        print(f"Dry run passed: Loaded {len(REGRESSION_TASKS)} independent regression tasks.")
        return 0

    try:
        return run_suite()
    finally:
        for m in MODELS:
            unload_model(m)


if __name__ == "__main__":
    sys.exit(main())
