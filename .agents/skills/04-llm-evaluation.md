# LLM Evaluation Skill
Activation: Use when measuring model quality, comparing models, or validating GameForge.

## Behavioral Instructions
Prefer executable evaluation over subjective inspection.

Separate:
- training data
- validation data
- held-out test data
- benchmark data

Measure when applicable:
- accuracy
- pass rate
- code correctness
- compilation
- API correctness
- version correctness
- regression rate
- latency
- throughput
- TTFT
- output truncation

For generated game code, validate syntax, compilation, runtime behavior, APIs, and target engine version.

Never compare models using different generation budgets without reporting the difference.

Never claim improvement from contaminated or unreproducible benchmarks.

Never invent evaluation results.
