# LLM Training Skill
Activation: Use for causal-LM training, SFT, LoRA, QLoRA, checkpointing, and fine-tuning.

## Behavioral Instructions
Use genuine next-token language-model training.

Understand:
- input_ids
- attention_mask
- labels
- causal masking
- shifted logits
- shifted labels
- CrossEntropyLoss
- ignore_index
- response-only masking
- chat templates
- gradient accumulation
- optimizer states
- checkpointing
- LoRA
- QLoRA

For LoRA, inspect the actual architecture and target real attention/MLP projections such as q_proj, k_proj, v_proj, o_proj, gate_proj, up_proj, and down_proj when applicable.

Before a full run perform a real smoke test:
1. batch construction
2. forward pass
3. real causal-LM loss
4. backward pass
5. gradient inspection
6. optimizer step
7. parameter delta verification
8. checkpoint save
9. checkpoint reload
10. evaluation

Never substitute latent MSE, arbitrary vectors, sine/cosine targets, or normalization edits for causal-LM training.

Verify that adapter training actually changes trainable adapter parameters.
