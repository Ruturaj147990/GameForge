"""Deterministic Short Before-and-After Evaluation Suite for GameForge 27B SFT.

Compares:
1. Baseline: gameforge-27b-sft:latest (Unaugmented Modelfile, no mmproj, generic prompt)
2. Candidate: gameforge-27b-sft-v2:latest (Code-first engine-aware system prompt, mmproj vision attached, ChatML parser)

Outputs:
  E:\\GameForge\\reports\\gameforge-27b-sft\\before_after_results.csv
  e:\\gameforge_step1\\reports\\gameforge-27b-sft\\before_after_results.csv
"""

import base64
import csv
import io
import json
import time
import urllib.request
from pathlib import Path
from PIL import Image, ImageDraw

REPORTS_DIR = Path("E:/GameForge/reports/gameforge-27b-sft")
MIRROR_REPORTS_DIR = (Path(__file__).resolve().parents[1] / r"reports/gameforge-27b-sft")
REPORTS_DIR.mkdir(parents=True, exist_ok=True)
MIRROR_REPORTS_DIR.mkdir(parents=True, exist_ok=True)

OLLAMA_API = "http://127.0.0.1:11434/api/generate"

MODELS = [
    "gameforge-27b-sft:latest",
    "gameforge-27b-sft-v2:latest"
]

def generate_compiler_error_image() -> str:
    """Generates a high-contrast compiler error image and returns base64 PNG."""
    img = Image.new("RGB", (640, 140), color=(30, 30, 30))
    draw = ImageDraw.Draw(img)
    # Header banner
    draw.rectangle([0, 0, 640, 28], fill=(60, 20, 20))
    draw.text((10, 6), "UnrealBuildTool — Visual C++ Compiler Error", fill=(255, 100, 100))
    # Error message
    draw.text((15, 40), "Source/MyGame/MyActor.cpp(42): error C2027: use of undefined type 'UStaticMesh'", fill=(240, 240, 240))
    draw.text((15, 65), "Engine/Source/Runtime/CoreUObject/... : note: see declaration of 'UStaticMesh'", fill=(180, 180, 180))
    draw.text((15, 95), "Fix required: Add the missing engine header include for UStaticMesh.", fill=(100, 200, 255))
    
    buf = io.BytesIO()
    img.save(buf, format="PNG")
    return base64.b64encode(buf.getvalue()).decode("utf-8")

COMPILER_IMAGE_B64 = generate_compiler_error_image()

TASKS = [
    {
        "id": "TASK-01",
        "domain": "Unreal Engine 5.7 C++",
        "title": "Replication & Authority",
        "prompt": "Write an Unreal Engine 5.7 C++ ActorComponent called UHealthComponent with replicated health, OnRep_Health, TakeDamage authority check, clamping between 0 and MaxHealth, and rejecting negative damage.",
        "rubrics": [("UCLASS(", 1), ("GENERATED_BODY()", 1), ("ReplicatedUsing", 2), ("HasAuthority()", 2), ("FMath::Clamp", 2), ("GetLifetimeReplicatedProps", 2)],
        "image": None
    },
    {
        "id": "TASK-02",
        "domain": "Unreal Engine 5.7 C++",
        "title": "Server RPC with Validation",
        "prompt": "In Unreal Engine 5.7 C++, declare and implement a server-reliable RPC called Server_FireWeapon with validation. Ensure it checks ammo count and has an authority check in implementation.",
        "rubrics": [("UFUNCTION(Server, Reliable, WithValidation)", 3), ("Server_FireWeapon_Validate", 3), ("Server_FireWeapon_Implementation", 3), ("bool", 1)],
        "image": None
    },
    {
        "id": "TASK-03",
        "domain": "Unreal Engine 5.7 C++",
        "title": "Gameplay Ability System (GAS)",
        "prompt": "Implement a Gameplay Ability System AttributeSet header in UE 5.7 with Health and MaxHealth using GAMEPLAYATTRIBUTE_PROPERTY_GETTER macros and replication callbacks.",
        "rubrics": [("ATTRIBUTE_ACCESSORS", 4), ("FGameplayAttributeData", 3), ("UAttributeSet", 3)],
        "image": None
    },
    {
        "id": "TASK-04",
        "domain": "Unreal Engine 5.7 C++",
        "title": "Performance & Tick Avoidance",
        "prompt": "Explain why Tick is harmful for performance in UE 5.7 and write code to disable Tick in constructor and replace it with a 0.2s FTimerHandle.",
        "rubrics": [("bCanEverTick = false", 3), ("GetWorldTimerManager", 4), ("SetTimer", 3)],
        "image": None
    },
    {
        "id": "TASK-05",
        "domain": "Unity 6 DOTS",
        "title": "Entities 1.3 Baker Authoring",
        "prompt": "In Unity 6 Entities 1.3, write a Baker class that bakes a GameObject with custom Authoring component into an Entity with IComponentData.",
        "rubrics": [("Baker<", 4), ("AddComponent(", 3), ("GetEntity(", 3)],
        "image": None
    },
    {
        "id": "TASK-06",
        "domain": "Godot 4 GDScript",
        "title": "Kinematic Character Locomotion",
        "prompt": "Write a Godot 4.3 GDScript CharacterBody3D script with gravity, jump, WASD movement, and move_and_slide().",
        "rubrics": [("CharacterBody3D", 3), ("move_and_slide()", 3), ("velocity", 2), ("is_on_floor()", 2)],
        "image": None
    },
    {
        "id": "TASK-07",
        "domain": "Game Mathematics",
        "title": "Quaternion SLERP",
        "prompt": "Implement Quaternion Spherical Linear Interpolation (SLERP) in C++ without engine dependencies, handling the negative dot product hemisphere flip.",
        "rubrics": [("dot", 3), ("< 0", 3), ("sin", 2), ("acos", 2)],
        "image": None
    },
    {
        "id": "TASK-08",
        "domain": "Multimodal Visual Debugging",
        "title": "Compiler Error Screenshot Diagnosis",
        "prompt": "Look at this compiler error screenshot. Diagnose the exact compilation error and state the required include header and code fix.",
        "rubrics": [("StaticMesh.h", 4), ("include", 3), ("UStaticMesh", 3)],
        "image": COMPILER_IMAGE_B64
    }
]

def query_model(model: str, prompt: str, image_b64: str = None, max_tokens: int = 250) -> dict:
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
        with urllib.request.urlopen(req, timeout=90) as resp:
            data = json.loads(resp.read().decode("utf-8"))
            dur = time.time() - t0
            resp_text = data.get("response", "")
            eval_count = data.get("eval_count", len(resp_text.split()))
            eval_dur_ns = data.get("eval_duration", 1)
            tps = (eval_count / (eval_dur_ns / 1e9)) if eval_dur_ns > 0 else (eval_count / dur)
            return {
                "text": resp_text,
                "latency_sec": round(dur, 2),
                "tps": round(tps, 2),
                "eval_count": eval_count,
                "is_truncated": eval_count >= (max_tokens - 2),
                "error": None
            }
    except Exception as e:
        return {
            "text": f"ERROR: {e}",
            "latency_sec": round(time.time() - t0, 2),
            "tps": 0.0,
            "eval_count": 0,
            "is_truncated": False,
            "error": str(e)
        }

def score_response(text: str, rubrics: list) -> tuple:
    score = 0
    matched = []
    text_l = text.lower()
    for kw, pts in rubrics:
        if kw.lower() in text_l:
            score += pts
            matched.append(kw)
    return score, matched

def main():
    print("=" * 80)
    print(" GAMEFORGE 27B SFT — SHORT BEFORE-AND-AFTER TEST HARNESS")
    print(" Baseline : gameforge-27b-sft:latest")
    print(" Candidate: gameforge-27b-sft-v2:latest")
    print("=" * 80)

    rows = []
    totals = {m: 0 for m in MODELS}

    for model in MODELS:
        print(f"\n>>> Running Evaluation for: {model} <<<")
        for idx, task in enumerate(TASKS, 1):
            tid = task["id"]
            title = task["title"]
            prompt = task["prompt"]
            rubrics = task["rubrics"]
            image = task.get("image")
            max_s = sum(p for _, p in rubrics)

            res = query_model(model, prompt, image_b64=image, max_tokens=250)
            score, matched = score_response(res["text"], rubrics)
            totals[model] += score

            row = {
                "model": model,
                "task_id": tid,
                "title": title,
                "domain": task["domain"],
                "score": score,
                "max_score": max_s,
                "percentage": round((score / max_s) * 100, 1),
                "tokens": res["eval_count"],
                "tps": res["tps"],
                "latency_sec": res["latency_sec"],
                "is_truncated": res["is_truncated"],
                "matched_keywords": "; ".join(matched),
                "error": res["error"] or "None",
                "preview": res["text"][:120].replace("\n", " ") + "..."
            }
            rows.append(row)
            status_flag = "TRUNC" if res["is_truncated"] else "OK"
            print(f"  [{idx:02d}/08] [{tid}] {title:32s} -> Score: {score:02d}/{max_s:02d} | Tok: {res['eval_count']:03d} [{status_flag}] | Speed: {res['tps']:4.1f} tps")

    print("\n" + "=" * 80)
    print(" FINAL SHORT-TEST COMPARATIVE RESULTS")
    print("=" * 80)
    for model in MODELS:
        pct = (totals[model] / 80.0) * 100
        print(f"  {model:30s}: {totals[model]:02d} / 80 points ({pct:.1f}%)")

    # Write CSV
    csv_fields = [
        "model", "task_id", "title", "domain", "score", "max_score",
        "percentage", "tokens", "tps", "latency_sec", "is_truncated",
        "matched_keywords", "error", "preview"
    ]
    csv_path_e = REPORTS_DIR / "before_after_results.csv"
    csv_path_m = MIRROR_REPORTS_DIR / "before_after_results.csv"

    for cp in [csv_path_e, csv_path_m]:
        with open(cp, "w", newline="", encoding="utf-8") as f:
            writer = csv.DictWriter(f, fieldnames=csv_fields)
            writer.writeheader()
            writer.writerows(rows)

    print(f"\nResults successfully saved to {csv_path_e} and {csv_path_m}")

if __name__ == "__main__":
    main()
