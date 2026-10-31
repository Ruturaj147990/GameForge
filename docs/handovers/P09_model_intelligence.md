# P9 — Model Intelligence (handover)

**Branch:** `phase/P9-models`. **Track:** runs in parallel from P1. WI-9.1 can start after P1 and the codegen evals
after P6. **Decisions:** AD-20, AD-5. **Resolves:** F-18, F-19, F-21. **Estimate:** 3–4 weeks.
**Read first:** `../07_CONTENT_AND_MODELS.md`, `../03_RESEARCH_2026-10-31.md` R13–R15.

**Approval gates:** WI-9.2 (hosted calls cost money and send data off the machine), WI-9.4 (training runs) and WI-9.5
(installing ROCm/PyTorch/Hunyuan3D/Piper) each need the **user's explicit approval in chat**. Without it, mark the item
`BLOCKED (needs approval: …)`.

## Objective

Choose and improve models by **measured performance on GameForge's own tasks**: drafting a design, patching a design,
writing a custom rule that compiles and passes its scenario, repairing a real compiler error, and judging screenshots.
Code-Q&A scores are not the measure.

---

## WI-9.1 The GameForge agentic eval suite (`src/gameforge_ide/evals/`)

```
evals/
  tasks/design_draft.jsonl      # 60 prompts: {"id","prompt","must_include":{"genre":..,"entities":{"pickup":">=1"},...}}
  tasks/gds_patch.jsonl         # 40: {"id","gds_fixture","request","expect":[{"path":"/entities/1/count","op":">","value":3}]}
  tasks/codegen_rule.jsonl      # 20: {"id","project_fixture","description","scenario"}  (needs P6)
  tasks/cpp_repair.jsonl        # 30: recorded real failures {"id","files":{...},"diagnostics":[...],"must_compile":true}
  tasks/vision_rubric.jsonl     # 30 labelled captures (from P7 WI-7.10)
  runner.py  metrics.py  adapters.py  report.py
```
- Sources: `design_draft` reuses the P1 fixture prompts plus 45 new ones across genres. `cpp_repair` is harvested from
  real Forge runs (build steps that failed and later succeeded after a repair; store the failing files and diagnostics),
  so it reflects real errors. The codegen tasks run in a reusable fixture project under
  `E:\GameForge\validation\P9_evalproj` (build once; each task swaps only the custom rule files, so incremental UBT
  builds take ~30–60 s).
- Metrics per task family: valid-JSON rate (first try / after repair), task pass rate (checklist, compile, scenario),
  median and p90 latency, tokens, and cost (hosted). Hosted-model results also record the spend from
  `spend.jsonl`.
- Adapters: Ollama (`complete_json`, `think:false`, explicit `num_ctx`) and hosted (`backend/providers/hosted.py`).
  Every run records the Ollama version (`/api/version`) or the provider model id, and the eval-suite git SHA.
- Output: `reports/P9/eval_<model>_<date>.json` and a Markdown summary table.

## WI-9.2 Hosted tier live validation (approval-gated)

1. The user creates a key and enters it in **Settings → Hosted providers** (Credential Manager), then opts the eval
   workspace in (`.gameforge/egress.json`). GameForge never asks for the key in chat.
2. Run the native tool self-test, then the eval suite subset (design_draft 20, gds_patch 20, codegen_rule 10,
   cpp_repair 10) with caps: per-day spend cap set by the user, per-task cap $0.50 by default.
3. For Anthropic, use current model ids (for example `claude-opus-5-5` or `claude-sonnet-5-5`; confirm the ids
   against the provider's model list at run time, not from this document). The Anthropic adapter in `hosted.py` must
   send tool schemas in the Messages API format and handle `tool_use` blocks. It was tested only against the mock so far,
   so expect fixes: they are part of this item.
4. A full free-form game (P6 adventure prompt) built with hosted `design` and `codegen` roles: evidence
   `reports/P9/hosted_game.json` (spend, time, result).

## WI-9.3 Routing from evidence

`scripts/models/gen_routing.py` reads the latest eval reports and writes
`src/gameforge_ide/config/model_routing.json`:
- For each role, pick the best-scoring **enabled** model that meets the latency budget (design ≤ 60 s p90, codegen ≤
  120 s p90, fast ≤ 5 s, vision ≤ 20 s) and, for hosted models, whose cost per task is under the user's cap.
- Hosted models are chosen only if the workspace opted in. Otherwise the best local model is used and a note says that
  a hosted model would score X.
- The file records `"source": {"reports": [paths + sha256], "generated_at": …}`. A unit test checks that every model
  named exists in the 4-model roster or in an enabled hosted profile.

## WI-9.4 Local fine-tune flywheel (approval-gated)

- **Capture** (opt-in setting, default off; local only): accepted designs (prompt → final GDS after user edits),
  accepted patches, and compile repairs that passed are appended to
  `E:\GameForge\datasets\flywheel\<yyyymm>.jsonl`, each with a provenance record (user-owned, workspace id, timestamp).
- **Training** reuses the existing DirectML LoRA scripts (`scripts/models/train_and_deploy_qwen35_9b.py` pattern)
  to produce new tags (`gameforge-qwen3.5-9b-fw<N>`). **Never overwrite** existing tags or Modelfiles: keep the rollback
  Modelfiles (training-lineage rules in AGENTS.md).
- **Promotion:** the new tag must beat its parent on the eval suite (design_draft + gds_patch + cpp_repair) by ≥ 3
  points with no family regressing more than 2 points. Otherwise it is discarded and the reason recorded.
- The model roster stays at four LLMs (D-044): a promoted fine-tune *replaces* its parent tag only after the user
  approves, with the parent's GGUF kept for rollback.

## WI-9.5 Neural content spikes (approval-gated installs, all on E:)

| Spike | Install (needs approval) | Measure | Pass |
|---|---|---|---|
| ROCm on Windows | AMD HIP SDK 7.2 + PyTorch ROCm wheels for gfx1101 in a venv at `E:\GameForge\envs\rocm` | `torch.cuda.is_available()` (HIP), a 4k×4k matmul timing, VRAM reported | works on RX 7700 XT |
| Hunyuan3D-2.1 shape-only | repo + weights to `E:\GameForge\models\hunyuan3d21` (licence: Tencent Hunyuan community licence, territory limits recorded in `LicenseRegistry`) | 10 prop prompts/images: time, peak VRAM (≤ 12 GB?), mesh validity (manifold, tris) | ≥ 7/10 valid meshes under 12 GB |
| Post-process | Geometry Script remesh + XAtlas UVs + GameForge material (M12 path) | import, LOD, collision, registry `NEURAL` provenance | prop passes the M12 lifecycle |
| Piper TTS | Piper (MIT) + one voice with a recorded licence to `E:\GameForge\models\piper` | 10 NPC lines: RTF on CPU, WAV import | audible lines play in a scenario capture |

Every spike writes `reports/P9/spike_<name>.json` with PASS, FAIL or BLOCKED and numbers. A PASS spike adds a backend
entry in `07_CONTENT_AND_MODELS.md` as `EXPERIMENTAL`, selectable only when the user enables it in Settings. **Never**
label a procedural asset as neural (the TRELLIS.2 mislabel lesson).

## WI-9.6 Structured-output robustness

- Startup: run the native tool self-test per configured model in the background (exists) and record the Ollama version.
  If the version changed since the last eval report, the Systems pill shows "Models changed since last evaluation".
- The JSON repair statistics from `prompt_to_gds`/`propose_patch`/codegen are logged to `.gameforge/model_stats.jsonl`
  and shown in Settings → Models.
- The `unreal_editor` native tool schema: for hosted models, a `oneOf` per op (generated from `op_schemas`). For local
  models, the compact description plus gateway validation (P2 WI-2.8). The eval measures both styles on the hosted
  model and keeps the better one.

## Phase exit gate
1. Eval reports for all four local models. Hosted models included if WI-9.2 was approved.
2. `model_routing.json` generated from the reports, and the IDE uses it (Settings shows the source report).
3. Every spike recorded. The flywheel capture works (opt-in) with a sample file. A fine-tune is optional and needs
   approval.
4. `docs/07_CONTENT_AND_MODELS.md` updated with measured numbers.

## Progress
| WI | Status | Started | Finished | Evidence |
|---|---|---|---|---|
| 9.1 | TODO | | | |
| 9.2 | TODO (needs approval) | | | |
| 9.3 | TODO | | | |
| 9.4 | TODO (needs approval) | | | |
| 9.5 | TODO (needs approval) | | | |
| 9.6 | TODO | | | |

## Review log (Claude)
_empty_

## Revisions
- 2026-10-31: created (Claude).
