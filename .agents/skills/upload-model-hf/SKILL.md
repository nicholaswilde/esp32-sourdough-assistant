---
name: upload-model-hf
description: Upload trained or quantized model binaries, tokenizers, and model cards to Hugging Face Hub for ESP32 projects.
---

# Upload Model to Hugging Face (`upload-model-hf`)

When the user asks to upload, publish, or share trained or quantized model binaries (`.bin`), tokenizers, or model artifacts to Hugging Face Hub, use this skill.

## Prerequisites

- **Hugging Face Authentication**: The environment must have an active Hugging Face token (via `hf auth login` or `HF_TOKEN` environment variable).
- **Tooling**: `uv` and `huggingface-hub`.

## Execution Methods

### Method 1: Using Taskfile (Recommended for `s3-tiny-stories`)

Inside `projects/s3-tiny-stories/`:

```bash
# Upload pre-quantized 15M INT4 model (stories15M_q4.bin) and tokenizer.json
task upload-model

# Upload custom PLE trained model directory from artifacts/
task upload-custom DIR=artifacts/tinystories/ple-v32768_c1500000-s0
```

### Method 2: Using the Project Python Uploader

Inside `projects/s3-tiny-stories/`:

```bash
# Upload to default repo (<user>/esp32-s3-tinystories)
uv run python upload_model_hf.py --path pc_tools/stories15M_q4.bin

# Upload to custom repository with dry-run test
uv run python upload_model_hf.py --path pc_tools/stories15M_q4.bin --repo-id <username>/<custom-repo> --dry-run

# Upload full directory with custom commit message
uv run python upload_model_hf.py --path artifacts/tinystories/my-run --repo-id <username>/<repo> -m "Add v1.0 trained checkpoint"
```

### Method 3: Using the Skill Script Runner

From the workspace root:

```bash
python3 .agents/skills/upload-model-hf/scripts/upload_to_hf.py [--path <path>] [--repo-id <repo>] [--dry-run]
```

### Method 4: Using the Native `hf` CLI

```bash
# Upload single model binary
uv run hf upload <repo_id> pc_tools/stories15M_q4.bin stories15M_q4.bin

# Upload full folder
uv run hf upload <repo_id> ./pc_tools . --include "*.bin,*.json"
```

## Uploaded Artifact Bundle

The tool automatically bundles and uploads 5 core artifacts:
1. **`README.md`**: Model Card containing YAML metadata tags, hardware requirements (ESP32-S3, 16MB Flash, 8MB PSRAM, `0x110000` flash offset), and `esptool` flashing commands.
2. **`LICENSE`**: The repository's Apache 2.0 license file.
3. **`metadata.json`**: Hardware, quantization, and model architecture metadata (e.g., layers, heads, dimensions, partition offset).
4. **`*.bin`**: The quantized or exported binary model weights (`stories15M_q4.bin`, `model.bin`).
5. **`tokenizer.json`**: BPE / SentencePiece tokenizer vocabulary file.

