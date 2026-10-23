# LLM Architecture and Model Engineering Skill
Activation: Use when inspecting, modifying, training, merging, converting, or analyzing an LLM.

## Behavioral Instructions
Understand Transformer models at tensor level.

Cover:
- embeddings
- attention
- MHA/MQA/GQA
- Q/K/V projections
- RoPE
- residual streams
- normalization
- MLP/FFN
- MoE
- logits
- tokenizer
- KV cache
- context length
- multimodal components

Always inspect the actual model configuration instead of guessing from the model name.

Record:
- architecture
- parameter count
- layers
- hidden size
- attention heads
- KV heads
- vocabulary size
- context length
- dtype
- quantization
- trainable modules

Understand PyTorch, Transformers, safetensors, GGUF, llama.cpp, and Ollama.

Never manually alter arbitrary tensors and describe that as legitimate model training or merging.
