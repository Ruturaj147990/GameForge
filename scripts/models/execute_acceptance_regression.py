import json
import time
import urllib.request
from pathlib import Path
from typing import Dict, List, Any

MODELS = ["gameforge-27b", "qwen3.8:27b-q4_K_M"]

REGRESSION_TASKS = [
    {
        "id": "REG-01",
        "category": "Unreal C++ Replication & Authority",
        "prompt": "Write Unreal Engine 5.7 C++ ActorComponent code for UHealthComponent with replicated health, OnRep_Health, and TakeDamage authority check. Output code only.",
        "rubrics": [
            ("UCLASS", 1),
            ("GENERATED_BODY()", 1),
            ("ReplicatedUsing", 2),
            ("OnRep_Health", 2),
            ("HasAuthority", 2),
            ("GetLifetimeReplicatedProps", 1),
            ("DOREPLIFETIME", 1)
        ],
        "deprecated_patterns": ["DOREPLIFETIME_WITH_CONDITION"]
    },
    {
        "id": "REG-02",
        "category": "Unreal RPC Validation & Security",
        "prompt": "In Unreal Engine 5.7 C++, declare and implement a server-reliable RPC called Server_FireWeapon with validation. Output code only.",
        "rubrics": [
            ("UFUNCTION(Server, Reliable, WithValidation)", 3),
            ("Server_FireWeapon_Validate", 3),
            ("Server_FireWeapon_Implementation", 3),
            ("bool", 1)
        ],
        "deprecated_patterns": []
    },
    {
        "id": "REG-03",
        "category": "Unreal Memory & TObjectPtr",
        "prompt": "In UE 5.7 C++, declare a UGameInstanceSubsystem with a TObjectPtr member to an inventory UDataAsset, explaining why TObjectPtr replaces raw pointers. Output code only.",
        "rubrics": [
            ("UGameInstanceSubsystem", 3),
            ("TObjectPtr<", 4),
            ("UPROPERTY(", 2),
            ("tracking", 1)
        ],
        "deprecated_patterns": []
    },
    {
        "id": "REG-04",
        "category": "Unreal Delegates & Events",
        "prompt": "Write a UE 5.7 dynamic multicast delegate declaration for OnPlayerDied taking AActor* Killer, exposed to Blueprints, and show broadcasting it. Output code only.",
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
        "prompt": "Provide the UE 5.7 C++ macro block (ATTRIBUTE_ACCESSORS) on an AttributeSet for a Health attribute. Output code only.",
        "rubrics": [
            ("ATTRIBUTE_ACCESSORS", 4),
            ("GAMEPLAYATTRIBUTE_VALUE_GETTER", 2),
            ("GAMEPLAYATTRIBUTE_VALUE_SETTER", 2),
            ("GAMEPLAYATTRIBUTE_PROPERTY_GETTER", 2)
        ],
        "deprecated_patterns": []
    },
    {
        "id": "REG-06",
        "category": "Collision & Sweep",
        "prompt": "Write a UE 5.7 C++ line trace function using LineTraceSingleByChannel on ECC_Visibility with FCollisionQueryParams ignoring self. Output code only.",
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
        "prompt": "Write a custom UBTTaskNode in UE 5.7 C++ executing an action and returning EBTNodeResult::Succeeded with bNotifyTick disabled. Output code only.",
        "rubrics": [
            ("UBTTaskNode", 3),
            ("ExecuteTask", 3),
            ("EBTNodeResult::Succeeded", 3),
            ("bNotifyTick", 1)
        ],
        "deprecated_patterns": []
    },
    {
        "id": "REG-08",
        "category": "Network Optimization",
        "prompt": "Implement GetLifetimeReplicatedProps in UE 5.7 for an Actor with SecretScore replicated COND_OwnerOnly, and Health replicated to all. Output code only.",
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
        "prompt": "Show how to bind an Enhanced Input Action (IA_Jump) in UE 5.7 Character C++ using UEnhancedInputComponent and ETriggerEvent::Triggered. Output code only.",
        "rubrics": [
            ("UEnhancedInputComponent", 4),
            ("BindAction", 3),
            ("ETriggerEvent::Triggered", 3)
        ],
        "deprecated_patterns": ["InputComponent->BindAction"]
    },
    {
        "id": "REG-10",
        "category": "Performance & Tick Avoidance",
        "prompt": "Show how to disable Tick in UE 5.7 C++ constructor and set up a 1.0s repeating timer via GetWorldTimerManager(). Output code only.",
        "rubrics": [
            ("PrimaryActorTick.bCanEverTick = false", 4),
            ("GetWorldTimerManager()", 3),
            ("SetTimer", 3)
        ],
        "deprecated_patterns": ["GetWorld()->GetTimerManager()"]
    },
    {
        "id": "REG-11",
        "category": "Godot 4 GDScript 2.0",
        "prompt": "Write a Godot 4 GDScript for a 3D CharacterBody3D implementing gravity, jump, velocity calculation, and move_and_slide(). Output code only.",
        "rubrics": [
            ("CharacterBody3D", 3),
            ("move_and_slide()", 3),
            ("is_on_floor()", 2),
            ("velocity", 2)
        ],
        "deprecated_patterns": ["move_and_slide(velocity)", "yield("]
    },
    {
        "id": "REG-12",
        "category": "Unity ECS / DOTS",
        "prompt": "Write a Unity 6 DOTS IJobEntity C# burst-compiled job modifying a Health component based on Damage. Output code only.",
        "rubrics": [
            ("IJobEntity", 3),
            ("BurstCompile", 3),
            ("Health", 2),
            ("Damage", 2)
        ],
        "deprecated_patterns": ["MonoBehaviour"]
    },
    {
        "id": "REG-13",
        "category": "UEFN Verse Concurrency",
        "prompt": "Write a UEFN Verse snippet using race or sync concurrency to wait for an elimination event or a 30.0s sleep timeout. Output code only.",
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
        "prompt": "Explain gimbal lock in Euler angles and write C++ pseudocode for Slerp interpolation between two quaternions. Output code and brief explanation.",
        "rubrics": [
            ("gimbal lock", 4),
            ("dot", 2),
            ("Slerp", 2),
            ("quaternion", 2)
        ],
        "deprecated_patterns": []
    },
    {
        "id": "REG-15",
        "category": "Game Mathematics - PID Controller",
        "prompt": "Implement a float PID controller in C++ with Proportional, Integral, and Derivative terms, anti-windup clamping, and dt. Output code only.",
        "rubrics": [
            ("error", 2),
            ("integral", 2),
            ("derivative", 2),
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
            "num_predict": 140
        }
    }
    req = urllib.request.Request(
        url,
        data=json.dumps(payload).encode("utf-8"),
        headers={"Content-Type": "application/json"}
    )
    t0 = time.time()
    try:
        with urllib.request.urlopen(req, timeout=90) as resp:
            data = json.loads(resp.read().decode("utf-8"))
        elapsed = time.time() - t0
        eval_count = data.get("eval_count", 0)
        eval_duration_ns = data.get("eval_duration", 1)
        prompt_eval_duration_ns = data.get("prompt_eval_duration", 0)
        tok_per_sec = eval_count / (eval_duration_ns / 1e9) if eval_duration_ns > 0 else 0
        ttft = prompt_eval_duration_ns / 1e9
        
        resp_text = data.get("response", "").strip()

        return {
            "success": True,
            "response": resp_text,
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

def main():
    print("=" * 80)
    print(" GAMEFORGE-27B INDEPENDENT ACCEPTANCE REGRESSION SUITE (15 TASKS)")
    print(f" Target Models: {MODELS} (think=False, direct streaming)")
    print("=" * 80)

    results = {
        "timestamp": time.time(),
        "total_tasks": len(REGRESSION_TASKS),
        "max_points_per_model": len(REGRESSION_TASKS) * 10,
        "models": {}
    }

    for model_name in MODELS:
        print(f"\n========================================================")
        print(f" RUNNING EVALUATION: {model_name}")
        print(f"========================================================")
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
                "response": res["response"]
            })

        if tok_rates:
            model_results["mean_tokens_per_sec"] = sum(tok_rates) / len(tok_rates)
            model_results["mean_ttft_seconds"] = sum(ttft_rates) / len(ttft_rates)

        results["models"][model_name] = model_results
        pct = (model_results["total_score"] / model_results["max_possible_score"]) * 100
        print(f"\n>>> {model_name} TOTAL: {model_results['total_score']}/{model_results['max_possible_score']} ({pct:.1f}%) | Avg Throughput: {model_results['mean_tokens_per_sec']:.1f} tps <<<")

    out_file = Path(r"E:\gameforge_step1\reports\gameforge-27b\acceptance\independent_regression_results.json")
    out_file.parent.mkdir(parents=True, exist_ok=True)
    out_file.write_text(json.dumps(results, indent=2))
    print(f"\nSaved regression results to {out_file}")

if __name__ == "__main__":
    main()
