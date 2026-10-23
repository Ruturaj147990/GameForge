# Local LLM Deployment Skill
Activation: Use when exporting, quantizing, registering, or optimizing local models.

## Behavioral Instructions
Understand:
- GGUF
- Q4_K_M
- Q5_K_M
- Q8_0
- F16
- llama.cpp
- Ollama
- Vulkan
- AMD GPU offloading
- CPU/GPU hybrid inference
- KV cache

After model export verify:
- file size
- architecture
- parameter count
- tensor count
- metadata
- quantization type
- SHA-256
- actual inference

For Ollama verify:
- model registration
- model identity
- Modelfile
- blob identity
- actual generation

For AMD hardware measure:
- VRAM usage
- RAM usage
- cold-start time
- warm TTFT
- sustained tokens/sec

Never report peak burst throughput as sustained throughput.

Never overwrite an existing GameForge model without explicit authorization.
