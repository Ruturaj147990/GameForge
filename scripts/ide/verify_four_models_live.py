import urllib.request
import json
import time

models = [
    "llama3.1:8b",
    "gameforge-27b-sft:latest",
    "gameforge-qwen3.5-4b:latest",
    "gameforge-qwen3.5-9b:latest"
]

print("=" * 70)
print(" VERIFYING LIVE INFERENCE ON FOUR CANONICAL ROSTER MODELS")
print("=" * 70)

for m in models:
    t0 = time.time()
    payload = {
        "model": m,
        "prompt": "Hello! Please identify your system role and confirm you are operational.",
        "stream": False,
        "think": False,
        "options": {
            "num_predict": 40,
            "temperature": 0.2
        }
    }
    data = json.dumps(payload).encode("utf-8")
    req = urllib.request.Request("http://127.0.0.1:11434/api/generate", data=data, headers={"Content-Type": "application/json"})
    try:
        with urllib.request.urlopen(req, timeout=90) as resp:
            res = json.loads(resp.read().decode("utf-8"))
            elapsed = time.time() - t0
            resp_txt = res.get("response", "").strip().replace("\n", " ")
            eval_count = res.get("eval_count", 0)
            eval_dur = res.get("eval_duration", 1) / 1e9
            tps = eval_count / eval_dur if eval_dur > 0 else 0
            print(f"[OK] {m:30s} | {tps:5.1f} tok/s | Latency: {elapsed:4.1f}s | Response: {resp_txt[:60]}...")
    except Exception as e:
        print(f"[FAIL] {m:30s} | Error: {e}")

print("=" * 70)
