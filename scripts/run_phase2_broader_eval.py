"""Phase 2 Broader Deterministic Evaluation Suite (16 Tasks).

Evaluates game-development capabilities across 16 distinct domains:
1. Unreal Engine 5.7 C++ implementation
2. Unreal networking, RPC and authority
3. Gameplay Ability System (GAS)
4. Unreal performance optimization and tick avoidance
5. Unreal debugging and code repair
6. Blueprint workflow and visual scripting reasoning
7. Unity 6 C# gameplay
8. Unity 6 DOTS entities and baking
9. Godot 4 GDScript and gameplay logic
10. Game math, vectors and quaternion operations
11. AI/navigation and gameplay decision logic
12. Physics and collision behavior
13. Game architecture and maintainability
14. Multiplayer state synchronization
15. Cross-engine version-aware reasoning
16. Screenshot-based visual debugging

Outputs:
  reports/gameforge-27b-sft/phase2_evaluation_results.csv
  reports/gameforge-27b-sft/raw_outputs_phase2/
"""

import base64
import csv
import io
import json
import re
import time
import urllib.request
from pathlib import Path
from PIL import Image, ImageDraw

WORKSPACE_ROOT = Path("E:/gameforge_step1")
REPORTS_DIR = WORKSPACE_ROOT / "reports" / "gameforge-27b-sft"
MIRROR_REPORTS_DIR = Path("E:/GameForge/reports/gameforge-27b-sft")
RAW_OUTPUTS_DIR = REPORTS_DIR / "raw_outputs_phase2"
MIRROR_RAW_DIR = MIRROR_REPORTS_DIR / "raw_outputs_phase2"

for d in [REPORTS_DIR, MIRROR_REPORTS_DIR, RAW_OUTPUTS_DIR, MIRROR_RAW_DIR]:
    d.mkdir(parents=True, exist_ok=True)

OLLAMA_API = "http://127.0.0.1:11434/api/generate"

def generate_compiler_error_image() -> str:
    """Generates a high-contrast compiler error image and returns base64 PNG."""
    img = Image.new("RGB", (640, 140), color=(30, 30, 30))
    draw = ImageDraw.Draw(img)
    draw.rectangle([0, 0, 640, 28], fill=(60, 20, 20))
    draw.text((10, 6), "UnrealBuildTool — Visual C++ Compiler Error", fill=(255, 100, 100))
    draw.text((15, 40), "Source/MyGame/MyActor.cpp(42): error C2027: use of undefined type 'UStaticMesh'", fill=(240, 240, 240))
    draw.text((15, 65), "Engine/Source/Runtime/CoreUObject/... : note: see declaration of 'UStaticMesh'", fill=(180, 180, 180))
    draw.text((15, 95), "Fix required: Add the missing engine header include for UStaticMesh.", fill=(100, 200, 255))
    buf = io.BytesIO()
    img.save(buf, format="PNG")
    return base64.b64encode(buf.getvalue()).decode("utf-8")

COMPILER_IMAGE_B64 = generate_compiler_error_image()

TASKS = [
    {
        "id": "PH2-01",
        "domain": "UE 5.7 C++ Core",
        "title": "ActorComponent with Delegate & Distance Check",
        "prompt": "In Unreal Engine 5.7 C++, implement an ActorComponent named UInteractableComponent with a delegate FOnInteractedSignature, an interact method Interact(APawn* InstigatorPawn), and an interaction distance check using FVector::DistSquared. Use modern TObjectPtr for any actor/component references.",
        "rubrics": [("DECLARE_DYNAMIC_MULTICAST_DELEGATE", 3), ("DistSquared", 3), ("TObjectPtr", 2), ("UInteractableComponent", 2)],
        "image": None,
        "is_multimodal": False
    },
    {
        "id": "PH2-02",
        "domain": "UE 5.7 Networking",
        "title": "Reliable Server RPC with Validation",
        "prompt": "Write an Unreal Engine 5.7 C++ character method and RPC pair for picking up an item: AttemptPickup(AItem* Item) called on client that invokes Server_PickupItem(AItem* Item). Ensure Server_PickupItem is a reliable Server RPC with validation checking item validity and distance, and an authority check in _Implementation.",
        "rubrics": [("UFUNCTION(Server, Reliable, WithValidation)", 3), ("Server_PickupItem_Validate", 3), ("Server_PickupItem_Implementation", 2), ("HasAuthority()", 2)],
        "image": None,
        "is_multimodal": False
    },
    {
        "id": "PH2-03",
        "domain": "UE 5.7 GAS",
        "title": "GameplayAbility Lifecycle & Tag Checks",
        "prompt": "Implement a modern UE 5.7 C++ GameplayAbility subclass UGA_FireWeapon that checks if the character has the gameplay tag State.Weapon.Ready, commits ability cost with CommitAbility, spawns a projectile actor, and ends the ability with EndAbility(Handle, ActorInfo, ActivationInfo, true, false).",
        "rubrics": [("CommitAbility", 3), ("EndAbility", 3), ("UGameplayAbility", 2), ("GameplayTag", 2)],
        "image": None,
        "is_multimodal": False
    },
    {
        "id": "PH2-04",
        "domain": "UE 5.7 Performance",
        "title": "Tick Avoidance & Timer Subsystem",
        "prompt": "Write code to optimize an Unreal Engine 5.7 C++ sensor component: disable Tick completely in the constructor (bCanEverTick = false), and instead initialize an FTimerHandle in BeginPlay running a PollSensors method at 5 Hz (every 0.2 seconds) using GetWorld()->GetTimerManager().SetTimer.",
        "rubrics": [("bCanEverTick = false", 3), ("SetTimer", 3), ("TimerManager", 2), ("0.2", 2)],
        "image": None,
        "is_multimodal": False
    },
    {
        "id": "PH2-05",
        "domain": "UE 5.7 Code Repair",
        "title": "Safe Array Removal & Pointer Validation",
        "prompt": "Fix the following buggy UE 5.7 C++ snippet that causes a crash and compiler error:\n```cpp\nvoid UInventoryComponent::DropItem(int32 SlotIndex) {\n    AItem* Item = Items[SlotIndex];\n    Item->Destroy();\n    Items.RemoveAt(SlotIndex);\n}\n```\nProvide the corrected method with bounds checking (IsValidIndex), pointer validation (IsValid), and proper null handling before destruction.",
        "rubrics": [("IsValidIndex", 4), ("IsValid", 3), ("RemoveAt", 3)],
        "image": None,
        "is_multimodal": False
    },
    {
        "id": "PH2-06",
        "domain": "Blueprint Workflow",
        "title": "Event Dispatcher & Damage Handling",
        "prompt": "Explain the exact node sequence and logic required in an Unreal Engine 5 Blueprint graph to implement an Event Dispatcher call for OnPlayerDeath. Specify which nodes handle Event AnyDamage, health calculation, branch condition (Health <= 0), and calling the Dispatcher.",
        "rubrics": [("Event AnyDamage", 3), ("Branch", 3), ("OnPlayerDeath", 4)],
        "image": None,
        "is_multimodal": False
    },
    {
        "id": "PH2-07",
        "domain": "Unity 6 Gameplay",
        "title": "Player Stamina Regeneration MonoBehaviour",
        "prompt": "In Unity 6 C#, write a MonoBehaviour script PlayerStamina that regenerates stamina over time after a cooldown delay. Include UseStamina(float amount) returning a bool, regeneration in Update(), and clamp stamina between 0 and maxStamina using Mathf.Clamp.",
        "rubrics": [("Mathf.Clamp", 3), ("UseStamina", 3), ("Time.deltaTime", 2), ("MonoBehaviour", 2)],
        "image": None,
        "is_multimodal": False
    },
    {
        "id": "PH2-08",
        "domain": "Unity 6 DOTS",
        "title": "Entities 1.3 Baker & Dynamic Usage Flags",
        "prompt": "In Unity 6 Entities 1.3 (DOTS), declare an IComponentData struct MoveSpeed with a float value, and write an authoring MonoBehaviour MoveSpeedAuthoring with a Baker class MoveSpeedBaker : Baker<MoveSpeedAuthoring> that adds the component using AddComponent(GetEntity(TransformUsageFlags.Dynamic), ...).",
        "rubrics": [("IComponentData", 3), ("Baker<", 3), ("AddComponent", 2), ("TransformUsageFlags", 2)],
        "image": None,
        "is_multimodal": False
    },
    {
        "id": "PH2-09",
        "domain": "Godot 4 GDScript",
        "title": "Typed Signals & Health Component",
        "prompt": "In Godot 4.3 GDScript, write a complete health component HealthComponent extending Node. Declare typed signals health_changed(current: float, max: float) and died, export max_health, implement take_damage(amount: float) that clamps health and emits signals using .emit().",
        "rubrics": [("signal health_changed", 3), ("signal died", 2), ("clamp", 2), (".emit(", 3)],
        "image": None,
        "is_multimodal": False
    },
    {
        "id": "PH2-10",
        "domain": "Game Mathematics",
        "title": "Surface Normal Vector Reflection",
        "prompt": "In C++, implement a function FVector ReflectVector(const FVector& Velocity, const FVector& SurfaceNormal) that computes the bounce reflection vector of a projectile hitting a surface normal, ensuring the normal is normalized and using the formula R = V - 2 * (V . N) * N.",
        "rubrics": [("DotProduct", 3), ("2", 2), ("GetSafeNormal", 3), ("-", 2)],
        "image": None,
        "is_multimodal": False
    },
    {
        "id": "PH2-11",
        "domain": "AI Navigation",
        "title": "BTTask Random Reachable Point",
        "prompt": "In Unreal Engine 5.7 C++, write a custom Behavior Tree Task node UBTTask_FindPatrolLocation derived from UBTTaskNode. Override ExecuteTask(UBehaviorTreeComponent& OwnerComp, uint8* NodeMemory), obtain the UNavigationSystemV1, find a random reachable point in radius using GetRandomReachablePointInRadius, store it in the Blackboard, and return EBTNodeResult::Succeeded.",
        "rubrics": [("UBTTaskNode", 2), ("ExecuteTask", 3), ("GetRandomReachablePointInRadius", 3), ("EBTNodeResult::Succeeded", 2)],
        "image": None,
        "is_multimodal": False
    },
    {
        "id": "PH2-12",
        "domain": "Godot 4 Physics",
        "title": "Area3D Projectile Collision Callback",
        "prompt": "In Godot 4.3 GDScript, write a script for a projectile using Area3D. Connect the body_entered signal to _on_body_entered(body: Node3D). If the body has a take_damage method, call it with 25 damage, spawn a hit particle or effect, and destroy the projectile with queue_free().",
        "rubrics": [("body_entered", 3), ("take_damage", 3), ("queue_free()", 4)],
        "image": None,
        "is_multimodal": False
    },
    {
        "id": "PH2-13",
        "domain": "Game Architecture",
        "title": "GameInstance Subsystem for Save State",
        "prompt": "Design an Unreal Engine 5.7 C++ UGameInstanceSubsystem called UGameSaveSubsystem for managing player save data across level transitions. Show class declaration inheriting UGameInstanceSubsystem, override Initialize and Deinitialize, and declare SaveGameToSlot and LoadGameFromSlot methods.",
        "rubrics": [("UGameInstanceSubsystem", 3), ("Initialize", 3), ("Deinitialize", 2), ("SaveGameToSlot", 2)],
        "image": None,
        "is_multimodal": False
    },
    {
        "id": "PH2-14",
        "domain": "Multiplayer Sync",
        "title": "RepNotify Callback & DOREPLIFETIME",
        "prompt": "In Unreal Engine 5.7 C++, implement variable replication with a RepNotify callback: declare a replicated enum EPlayerTeam with UPROPERTY(ReplicatedUsing = OnRep_PlayerTeam), write GetLifetimeReplicatedProps using DOREPLIFETIME, and implement the OnRep_PlayerTeam callback function.",
        "rubrics": [("ReplicatedUsing", 3), ("OnRep_PlayerTeam", 3), ("GetLifetimeReplicatedProps", 2), ("DOREPLIFETIME", 2)],
        "image": None,
        "is_multimodal": False
    },
    {
        "id": "PH2-15",
        "domain": "Cross-Engine Reasoning",
        "title": "Unity 2022.3 vs Unity 6 DOTS Evolution",
        "prompt": "Compare the entity authoring and baking pipeline between Unity 2022.3 (Entities 1.0/Classic DOTS) and Unity 6 (Entities 1.3). Specifically describe the deprecation of GameObjectConversionSystem in favor of Baker<T>, how TransformUsageFlags replaced legacy authoring flags, and provide the correct Unity 6 Baker syntax.",
        "rubrics": [("GameObjectConversionSystem", 3), ("Baker<", 3), ("TransformUsageFlags", 4)],
        "image": None,
        "is_multimodal": False
    },
    {
        "id": "PH2-16",
        "domain": "Visual Debugging",
        "title": "Compiler Error Screenshot Diagnosis",
        "prompt": "Look at this compiler error screenshot. Diagnose the exact compilation error and state the required include header and code fix.",
        "rubrics": [("StaticMesh.h", 4), ("include", 3), ("UStaticMesh", 3)],
        "image": COMPILER_IMAGE_B64,
        "is_multimodal": True
    }
]

def query_model(model: str, prompt: str, image_b64: str = None, max_tokens: int = 512) -> dict:
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
    if image_b64:
        payload["images"] = [image_b64]

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

def check_syntax_balance(code: str) -> bool:
    stack = []
    pairs = {"{": "}", "[": "]", "(": ")"}
    for char in code:
        if char in pairs:
            stack.append(pairs[char])
        elif char in pairs.values():
            if not stack or stack.pop() != char:
                return False
    return len(stack) == 0

def run_evaluation(model_name: str):
    print("=" * 80)
    print(f" PHASE 2 BROADER DETERMINISTIC EVALUATION (16 TASKS) — {model_name}")
    print(" Generation budget: 512 tokens (bounded retry to 768 if truncated)")
    print("=" * 80)

    rows = []
    total_score = 0
    max_total = sum(sum(pts for _, pts in t["rubrics"]) for t in TASKS)

    for idx, task in enumerate(TASKS, 1):
        tid = task["id"]
        title = task["title"]
        prompt = task["prompt"]
        rubrics = task["rubrics"]
        image = task.get("image")
        is_mm = task.get("is_multimodal", False)
        max_s = sum(p for _, p in rubrics)

        # Initial run with 512 tokens
        res = query_model(model_name, prompt, image_b64=image, max_tokens=512)
        initial_truncated = res["is_truncated"]
        retried = False

        # If truncated, execute bounded retry once at 768 tokens
        if res["is_truncated"] and not is_mm:
            print(f"  [Task {tid}] Initial run hit 512-token limit. Executing bounded retry at 768 tokens...")
            retry_res = query_model(model_name, prompt, image_b64=image, max_tokens=768)
            if not retry_res["error"]:
                res = retry_res
                retried = True

        score, matched = score_response(res["text"], rubrics)
        syntax_ok = check_syntax_balance(res["text"])
        total_score += score

        # Save raw output
        raw_filename = f"{tid}_{model_name.replace(':', '_')}.txt"
        (RAW_OUTPUTS_DIR / raw_filename).write_text(res["text"], encoding="utf-8")
        (MIRROR_RAW_DIR / raw_filename).write_text(res["text"], encoding="utf-8")

        status_flag = "TRUNC" if res["is_truncated"] else "COMPLETE"
        if initial_truncated and retried and not res["is_truncated"]:
            status_flag = "RETRY_RESOLVED"

        print(f"  [{idx:02d}/16] [{tid}] {title:35s} -> Score: {score:02d}/{max_s:02d} | Tokens: {res['eval_count']:03d} [{status_flag}] | SyntaxBalanced: {syntax_ok} | Speed: {res['tps']:4.1f} tps")

        rows.append({
            "model": model_name,
            "task_id": tid,
            "title": title,
            "domain": task["domain"],
            "score": score,
            "max_score": max_s,
            "percentage": round((score / max_s) * 100, 1),
            "tokens": res["eval_count"],
            "tps": res["tps"],
            "latency_sec": res["latency_sec"],
            "initial_truncated": initial_truncated,
            "final_truncated": res["is_truncated"],
            "retried": retried,
            "syntax_balanced": syntax_ok,
            "is_multimodal": is_mm,
            "matched_rubrics": "; ".join(matched),
            "error": res["error"] or "None",
            "raw_output_path": f"raw_outputs_phase2/{raw_filename}",
            "preview": res["text"][:100].replace("\n", " ") + "..."
        })

    pct = round((total_score / max_total) * 100, 2)
    print("\n" + "=" * 80)
    print(f" TOTAL SCORE: {total_score} / {max_total} ({pct}%)")
    print("=" * 80)

    # Write CSV
    csv_fields = [
        "model", "task_id", "title", "domain", "score", "max_score",
        "percentage", "tokens", "tps", "latency_sec", "initial_truncated",
        "final_truncated", "retried", "syntax_balanced", "is_multimodal",
        "matched_rubrics", "error", "raw_output_path", "preview"
    ]
    csv_path_w = REPORTS_DIR / "phase2_evaluation_results.csv"
    csv_path_m = MIRROR_REPORTS_DIR / "phase2_evaluation_results.csv"

    for cp in [csv_path_w, csv_path_m]:
        with open(cp, "w", newline="", encoding="utf-8") as f:
            writer = csv.DictWriter(f, fieldnames=csv_fields)
            writer.writeheader()
            writer.writerows(rows)

    print(f"Results saved to {csv_path_w} and {csv_path_m}")
    return total_score, max_total, rows

if __name__ == "__main__":
    import sys
    target = sys.argv[1] if len(sys.argv) > 1 else "gameforge-27b-sft:latest"
    run_evaluation(target)
