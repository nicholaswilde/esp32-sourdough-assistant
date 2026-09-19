---
name: verify-model-size
description: Verify model binary size and PSRAM/SRAM memory budgets for ESP32-S3-DevKitC-1-N16R8 before training or flashing.
---

# Verify Model Size (`verify-model-size`)

This skill verifies that model architecture parameters or compiled model binaries (`model.bin`) strictly fit within the physical memory and partition limits of the target hardware (**ESP32-S3-DevKitC-1-N16R8**) **before training or flashing**.

## Target Hardware Limits

| Resource | Boundary / Budget | Hardware Specs |
| :--- | :--- | :--- |
| **Model Flash Partition** | `0xEE0000` (**15,597,568 bytes** / ~14.88 MB) | At offset `0x110000` defined in `partitions.csv` |
| **Total Flash Size** | 16 MB (`board_upload.flash_size = 16MB`) | ESP32-S3 QIO Flash |
| **PSRAM Budget** | 8 MB (**8,388,608 bytes**) | Octal SPI PSRAM (staged weights + KV cache + logits) |
| **Internal SRAM** | ~327 KB available user SRAM | Scratch activation buffers + norm vectors |

---

## When to Use This Skill

1. **Before Training**: Prior to starting local or Google Colab training runs (e.g., `task train-full`, `task train-test`, `task colab-train-full`), verify that the proposed `--vocab`, `--d-model`, `--n-layers`, `--ple-dim`, or `--target-core` will produce a `.bin` file that fits on flash.
2. **Before Exporting / Flashing**: Verify an existing `.bin` or checkpoint against the `0xEE0000` partition limit.
3. **During Architecture Changes**: Check sizing impact when adjusting vocabularies or hidden dimensions.

---

## Usage

### 1. Pre-Training Sizing Verification

Run the verification tool with your proposed training hyperparameters:

```bash
# Verify standard PLE training config (e.g. 28.9M parameters)
uv run python .agents/skills/verify-model-size/scripts/verify_model_size.py \
  --vocab 32768 \
  --out-vocab 25353 \
  --d-model 96 \
  --n-layers 6 \
  --ple-dim 128 \
  --target-core 560000

# Verify custom run with specific FFN hidden dimension
uv run python .agents/skills/verify-model-size/scripts/verify_model_size.py \
  --vocab 32768 \
  --d-model 128 \
  --n-layers 6 \
  --ffn-hidden 256 \
  --ple-dim 64
```

### 2. Post-Training / Existing Binary Verification

Inspect an already exported binary file:

```bash
# Verify local model.bin
uv run python .agents/skills/verify-model-size/scripts/verify_model_size.py \
  --bin projects/s3-tiny-stories/pc_tools/model.bin

# Verify an exported checkpoint artifact
uv run python .agents/skills/verify-model-size/scripts/verify_model_size.py \
  --bin projects/s3-tiny-stories/artifacts/tinystories/model.bin
```

### 3. Using Taskfile

From workspace root:
```bash
task verify:s3-tiny-stories
```

---

## Sizing Formulas

### Flash Size (`model.bin`)
- **Header**: 56 bytes (`PLE\0` format v1).
- **Quantized INT4 Tensors**: For each tensor of shape `[rows, cols]`:
  $$\text{bytes} = 4 + \left(\text{rows} \times \left\lceil\frac{\text{cols}}{2}\right\rceil\right) + \left(\text{rows} \times \left\lceil\frac{\text{cols}}{\text{group}}\right\rceil \times 2\right)$$
- **FP32 Norm Vectors**: `numel * 4` bytes.

### PSRAM Footprint
- **Staged INT8 Weights**: Unpacked INT8 codes + FP32 scales in PSRAM:
  $$\text{bytes} = (\text{rows} \times \text{cols}) + \left(\text{rows} \times \left\lceil\frac{\text{cols}}{\text{group}}\right\rceil \times 4\right)$$
- **KV Cache**: $2 \times L \times S \times D \times 4$ bytes.
- **Logits**: $V_{\text{out}} \times 4$ bytes.
