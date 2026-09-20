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

### Method 1: Using Taskfile (Recommended)

From the repository root:

```bash
# Upload sourdough model bundle (dry-run)
task upload-model DRY_RUN=true

# Upload sourdough model bundle to default repo (<user>/esp32-s3-sourdough)
task upload-model

# Upload to custom Hugging Face repo
task upload-model REPO=nicholascwilde/esp32-s3-sourdough
```

### Method 2: Using the Project Python Uploader

From `model/` directory:

```bash
# Upload default bundle (model/tools/sourdough_q4.bin, tokenizer, metadata, model card)
uv run python upload_model_hf.py

# Upload with dry-run test
uv run python upload_model_hf.py --dry-run

# Upload custom model binary
uv run python upload_model_hf.py --path tools/sourdough_q4.bin --repo-id <username>/<custom-repo>
```

### Method 3: Using the Skill Script Runner

From the workspace root:

```bash
uv run python .agents/skills/upload-model-hf/scripts/upload_to_hf.py [--path <path>] [--repo-id <repo>] [--dry-run]
```

### Method 4: Using the Native `hf` CLI

```bash
# Upload model binary
uv run hf upload <repo_id> model/tools/sourdough_q4.bin sourdough_q4.bin

# Upload full folder
uv run hf upload <repo_id> ./model/tools . --include "*.bin,*.json,*.md"
```

## Uploaded Artifact Bundle

The tool automatically bundles and uploads 5 core artifacts:
1. **`README.md`**: Model Card containing YAML metadata tags, hardware requirements (ESP32-S3, 16MB Flash, 8MB PSRAM, `0x520000` flash offset), and `esptool` flashing commands.
2. **`LICENSE`**: The repository's Apache 2.0 license file.
3. **`metadata.json`**: Hardware, quantization, and model architecture metadata (e.g., layers, heads, dimensions, partition offset).
4. **`*.bin`**: The quantized or exported binary model weights (`stories15M_q4.bin`, `model.bin`).
5. **`tokenizer.json`**: BPE / SentencePiece tokenizer vocabulary file.

