# GameForge IDE Performance Report

**Updated:** 2026-10-24T17:37:05+05:30  
**Status:** One local model API smoke measurement captured; repeatable product performance benchmarks remain unmeasured.

## Environment

The canonical project context reports Windows 11 Pro, Ryzen 5 7600X, 32 GB DDR5, and Radeon RX 7700 XT 12 GB. These hardware values are context-file evidence, not re-probed in this measurement pass. Python observed: 3.14.6. Unreal `Build.version` observed: 5.7.4.

## Measured in this pass

| Measurement | Result | Method / limits |
|---|---:|---|
| Focused runtime + desktop tests | 42 passed in 3.56 s | pytest wall time; not an app responsiveness benchmark |
| Protected graders | 45 passed in 0.05 s | pytest wall time |
| Unit discovery | 195 collected in 0.95 s | Current inventory |
| Non-API unit suite | 183 passed in 16.71 s | Historical run excluding API tests; superseded by full suite below |
| Full unit suite | 195 passed in 17.82 s | Python 3.14.6, local socket permission enabled, process temp paths redirected; includes the API tests; 2 upstream deprecation warnings |
| Ollama provider stream | 1 exact-output response in ~15 s wall time | `OllamaProvider.stream_chat`, canonical model, `think: false`, short prompt/response; one run only |
| Unreal plugin package build | 48.0 s | UE 5.7.4 AutomationTool/UBT, Win64, 8 actions, UBT reported up to 6 worker processes; build duration only, not editor startup or inference performance |
| Latest Unreal plugin package build | 36.04 s | UE 5.7.4 AutomationTool/UBT, Win64; 10 output files. Build time only. |
| Direct Ollama smoke | 17.37 s total; 13.99 s model load; 625 prompt / 5 output tokens | One `gameforge-27b-sft:latest` `/api/chat` request with `think: false`, `num_predict: 16`; exact output `GAMEFORGE_OK`. Single sample, not an IDE/provider/UI benchmark. |
| Estimated system prompt | 2,281 tokens | UTF-8 byte count divided by 3 and rounded up; conservative heuristic, not model tokenizer usage |
| Default input allowance | 2,944 estimated tokens | 4,096 context minus 1,024 output reservation and 128 safety tokens |
| Current history budget after system prompt | 663 estimated tokens | Derived from above; active prompt is never truncated |

## Not measured

Cold/warm desktop startup, repeatable time-to-first-token, stream throughput, UI token-update responsiveness, explorer scan latency on a large Unreal project, CPU/RAM/VRAM under inference, build resource pressure, cancellation latency, and hosted load capacity. The two single-shot local inference checks prove connectivity/function only, not sustained performance. No capacity guarantee is made.

## Measurement plan

Use a repeatable fixture and record OS/Python/GPU driver/model/engine versions, at least five warm and cold repetitions, median and p95, process CPU and private working set, GPU VRAM/compute, and request token counts where the provider reports them. Keep model inference, UI startup, file indexing, and Unreal compilation as separate scenarios. Define scheduler limits only after this evidence exists.
