# :bread: ESP32-S3 Sourdough Baker Assistant :robot:
[![task](https://img.shields.io/badge/Task-Enabled-brightgreen?style=for-the-badge&logo=task&logoColor=white)](https://taskfile.dev/#/)
[![Hugging Face](https://img.shields.io/badge/Hugging%20Face-nicholascwilde%2Fesp32--s3--sourdough-ffd21e?style=for-the-badge&logo=huggingface)](https://huggingface.co/nicholascwilde/esp32-s3-sourdough)

An offline, on-device AI assistant for sourdough bread baking and troubleshooting that runs locally on an **ESP32-S3** microcontroller.

Inspired by [slvDev/esp32-ai-barista](https://huggingface.co/slvDev/esp32-ai-barista), this model uses a lightweight **Per-Layer Embeddings (PLE)** architecture and a compact 2,048-token vocabulary to fit entirely into flash and PSRAM without requiring internet access or external APIs. Pre-trained weights, tokenizer, and dataset bundle are published at [nicholascwilde/esp32-s3-sourdough](https://huggingface.co/nicholascwilde/esp32-s3-sourdough).

> [!WARNING]
> This project is currently in a `v0.X.X` development stage. Features and configurations are subject to change, and breaking changes may be introduced at any time.

> [!IMPORTANT]
> **Strict Hardware Target — ESP32-S3 N16R8 Only**:
> This project is specifically slated and configured for the **ESP32-S3 N16R8** variant (e.g. `ESP32-S3-DevKitC-1-N16R8` with 16MB Flash and 8MB Octal PSRAM). **Other variations will NOT work**:
> - **Flash Size (N16 required)**: The model partition table requires ~14.88 MB (`0xEE0000`) allocated at `0x110000`. Boards with 4MB (N4) or 8MB (N8) flash cannot fit the partition table.
> - **PSRAM Size & Mode (R8 Octal required)**: Runtime weights staging, KV cache, and activation buffers demand 8MB Octal PSRAM configured for `qio_opi`. Variants with no PSRAM or 2MB Quad PSRAM (R2) will crash with out-of-memory errors on boot.
> - **Core Architecture (ESP32-S3 required)**: The firmware utilizes custom Xtensa LX7 dual-core PIE 128-bit vector SIMD assembly (`simd_dotp.S`). Non-S3 chips (original ESP32, S2, C3, C6, etc.) are unsupported.

---

## :sparkles: Features

*   **Architecture**: Per-Layer Embeddings (PLE) micro-LLM ($L=6$ layers, $D=160$ hidden dim, $F=448$ FFN dim, ~7.8M total params, ~2.28M core params).
*   **Target Hardware**: Strictly **ESP32-S3-DevKitC-1-N16R8** (16MB Flash, 8MB Octal PSRAM). Smaller flash/PSRAM variants will not work.
*   **Memory Footprint**: ~3.49 MB PSRAM total (~2.55 MB staged weights, ~0.94 MB KV cache, ~7 KB logits), leaving > 4.5 MB headroom on 8 MB PSRAM; and ~34.25 KB internal SRAM, well below the 327 KB internal SRAM ceiling.
*   **Vocabulary**: Asymmetric untied-head vocabulary (4,096 base BPE tokens, 6,106 input embeddings with PLE, 2,197 active output word classes) tailored for baking terms.
*   **Quantization**: INT4 grouped quantization (`group_size = 128`) mapped directly from flash via `esp_partition_mmap` at offset `0x110000`.
*   **Troubleshooting Domains**:
    1.  **Starter Health**: Hooch, sluggish rising, acetone/nail polish smell, mold detection, feeding ratios (1:1:1 vs 1:5:5), refrigeration, stiff starters (50-60%), discard shelf life, tap water/chlorine effects, flour selection.
    2.  **Bulk Fermentation**: Volume rise indicators, under-fermentation (fool's crumb), over-fermentation, poke test, stretch & folds, coil folds, dough temperature, aliquot jars, dough acidity & gluten breakdown.
    3.  **Hydration & Shaping**: Sticky dough handling, banneton sticking (rice flour), cold retard benefits, autolyse vs fermentolyse, beginner hydrations, flour protein content (AP vs Bread flour), whole grain hydration adjustments, batard vs boule shaping, inclusions (cheese, jalapeño), sandwich loaf pans.
    4.  **Scoring & Baking**: Blade angle (30–45° for ears), steam importance, Dutch oven temps & times, gummy crumb prevention, burnt bottom deflection, open bakes with lava rocks/baking steel, ice cubes in Dutch oven, micro-blisters, bread storage.
    5.  **Baker's Math**: Baker's percentages, standard 100/70/20/2 sourdough formula, salt functions, recipe scaling for 2 loaves, total hydration calculations including starter.
    6.  **Guardrails**: Polite rejection for out-of-domain / non-baking queries.

---

## :clipboard: Prerequisites

Ensure you have the following tools installed:
*   [PlatformIO Core (CLI)](https://docs.platformio.org/en/latest/core/index.html)
*   [go-task](https://taskfile.dev/)
*   [uv](https://github.com/astral-sh/uv) (Python dependency manager)
*   [huggingface-hub](https://huggingface.co/docs/huggingface_hub/en/guides/cli) (`hf` CLI)
*   [esptool.py](https://docs.espressif.com/projects/esptool/en/latest/esp32/)

---

## 🏗️ Repository Architecture

This repository is organized as a monorepo separating **firmware development** from **model training and development**:

| Component | Directory | Description | Environment |
| :--- | :--- | :--- | :--- |
| **Firmware** | [`firmware/`](firmware/) | PlatformIO ESP32-S3 C++ sketch, WebServer, HTTP API, REPL, tests | PlatformIO, minimal Python (`huggingface-hub`, `pyserial`) |
| **Model** | [`model/`](model/) | PyTorch PLE architecture, dataset generator, INT4 quantization, Colab runners, HF upload | PyTorch, transformers, tokenizers, numpy |

* **Firmware Developers** only need PlatformIO and `task download-model` to download pre-trained weights and flash the ESP32-S3 without needing PyTorch.
* **Model Developers** can train, quantize, evaluate, and publish models inside [`model/`](model/).
* **Top-Level Tasks**: The root `Taskfile.yml` seamlessly delegates commands to both subprojects.

---

## :gear: Setup & Training Workflow

### 0. Quick Start & Prerequisites
Clone and navigate to the project repository:
```bash
git clone git@github.com:nicholaswilde/esp32-sourdough-assistant.git
cd esp32-sourdough-assistant
```

### 1. Generate the Q&A Dataset
Expands the 104 curated sourdough troubleshooting topics into 5,000 conversational Q&A training pairs with varied prefixes, phrasings, paraphrased answers, and leak-free validation splits:
```bash
task generate
```
Outputs in `model/data/sourdough/raw/`:
* `sourdough_qa.jsonl` (Structured JSON lines dataset tagged with train/val splits)
* `sourdough_corpus.txt` (Text corpus formatted with `<|endoftext|>` delimiters, ~225k words)

### 2. Build Vocabulary, Layout, and Encode Dataset
Trains the BPE tokenizer, builds the frozen output dictionary, and encodes the asymmetric token mappings:
```bash
task vocab
task layout
task prepare
```
Outputs in `model/data/sourdough/`:
* `vocab.json` (Curated frozen output vocabulary, 2,197 classes)
* `layout.json` (Asymmetric out2in projection mappings)
* `tokenizer.json` (BPE vocabulary and merge table)
* `asymmetric/train.bin` (Training token split)
* `asymmetric/val.bin` (Validation token split)

### 2.5. Test and Validate the Dataset (Without Training)
Verify tokenizer roundtrip fidelity, context lengths, token distributions, or query the dataset directly before training:
```bash
# Run integrity checks (sequence length <= 128, round-trip decode, ID bounds):
task validate-dataset

# Query the dataset directly to see matched Q&A pairs:
task query-dataset QUERY="Why is the inside of my bread gummy?"
task query-dataset QUERY="My dough is too sticky to shape"
```

### 3. Train the Model
Trains the **Per-Layer Embeddings (PLE)** micro-LLM (~2.3M parameters):
```bash
# Standard training (1,200 steps)
task train

# Extended training (2,000 steps)
task train-full
```
*   **Speed**: ~4–6 minutes on CPU (or seconds on CUDA GPU / Colab T4).
*   **Metrics**: Logs training loss, validation loss, and perplexity (PPL) every 100 steps.
*   **Checkpoint**: Saved to `model/runs/sourdough/ple-sourdough-v1-s0.pt`.

*Advanced Options:*
```bash
# Train for additional steps or custom learning rates:
uv run python -m research.sourdough.train --steps 1000 --eval-every 100 --arm ple --lr 1e-3
```

### 4. Interactive Test (Prompt Sampling)
Query the trained model with baking troubleshooting questions directly in your terminal:
```bash
# Question 1: Starter liquid / hooch
task sample PROMPT="Why is there liquid on top of my sourdough starter?"

# Question 2: Scoring & ears
task sample PROMPT="Why didn't my sourdough bread develop an ear?"

# Question 3: Gummy crumb
task sample PROMPT="Why is the inside of my loaf gummy?"

# Question 4: Fermentation timing
task sample PROMPT="How do I know when bulk fermentation is finished?"

# Question 5: Sticky dough
task sample PROMPT="My dough is too sticky to shape. What should I do?"
```

### 5. Run Native Host Firmware Tests
Verify the C++ firmware compilation and unit tests against Unity:
```bash
task test
# or: pio test -e native
```

---

## :cloud: Google Colab Training (Free Tier)

For faster cloud GPU training using Google Colab's Free Tier (T4 GPU):

```bash
# Verify authentication
task colab-auth

# Run standard training (1,200 steps)
task colab-train

# Or run fast smoke test (50 steps)
task colab-train-test

# Or extended training (2,000 steps)
task colab-train-full
```

Model checkpoints (`model/runs/sourdough/*.pt`) and tokenizer (`model/data/sourdough/tokenizer.json`) are automatically downloaded back to your local repository.


---

## :cloud: Hugging Face Model Hub

The complete model bundle (weights, tokenizer, C export configs, and dataset) is hosted on Hugging Face Hub at **[nicholascwilde/esp32-s3-sourdough](https://huggingface.co/nicholascwilde/esp32-s3-sourdough)**.

Upload the trained weights, dataset, and the bundle (`README.md`, `LICENSE`, `metadata.json`, `*.bin`, `tokenizer.json`, `sourdough_qa.jsonl`) to Hugging Face Hub:

```bash
# Upload to your Hugging Face account (nicholascwilde/esp32-s3-sourdough)
task upload-model

# Or preview upload files and sizes without pushing (Dry Run)
task model:upload-model PATH="tools/" --dry-run
```

### Download Pre-built Model from Hugging Face
To download pre-trained weights and tokenizer without training locally:

```bash
# Download from default repository (nicholascwilde/esp32-s3-sourdough)
task download-model

# Or download from a specific Hugging Face repository
task download-model REPO="<username>/esp32-s3-sourdough"
```
The download script automatically saves `sourdough_q4.bin`, `tokenizer.json`, and `metadata.json` to `firmware/models/`, ready to flash immediately.

---

## :zap: Flashing & Interacting on the ESP32-S3

### 1. Export & Quantize Model (INT4)
Exports the model weights into packed INT4 binary format and generates C headers:
```bash
task quantize
task headers
```
Artifacts generated:
* `model/tools/sourdough_q4.bin` (~4.1 MB INT4 packed model binary)
* `firmware/src/generated/vocab.h` (UTF-8 token strings table for on-device decoding)
* `firmware/src/generated/tokenizer_asset.h` (Compact BTK1 BPE tokenizer asset)
* `firmware/src/generated/sourdough_words.h` (Output class mapping table)
* `firmware/src/generated/sourdough_out2in.h` (Output to input projection IDs)
* `firmware/src/generated/sourdough_subvocab.h` (Centroid clusters for SIMD acceleration)

### 2. Flash Model Weights Partition (`0x110000`)
Writes the packed model binary to flash offset `0x110000`:
```bash
task flash-model
```

### 3. Compile and Upload Firmware
Builds the C++ inference engine and uploads it to the ESP32-S3:
```bash
task build
task flash
```

### 4. Interactive USB-Serial REPL
Open the serial monitor at 115200 baud to converse directly with the assistant:
```bash
task monitor
# or: pio device monitor -b 115200
```

#### Example Terminal Session
```text
=======================================================
  🥖 ESP32-S3 Sourdough Baker Assistant (PLE INT4)    
=======================================================
[s3-sourdough] Tokenizer ready: vocab=2048, merges=1791
[s3-sourdough] Model loaded: vocab=2048, dim=128, layers=4, heads=4, ffn=350, ple_dim=128
[s3-sourdough] Copied 18 RMSNorm vectors to SRAM
[s3-sourdough] Staged 43/43 core tensors to int8 in PSRAM
[s3-sourdough] Dual-core acceleration enabled (Core 0 + Core 1)
[s3-sourdough] Free SRAM: 284.1 KB | Free PSRAM: 6.88 MB

Ready! Enter your sourdough question below:

User: Why is my bread gummy inside?
Assistant: A gummy crumb occurs when bread is sliced while still hot, or if under-baked. Let your loaf cool completely on a wire rack for at least 2 hours. Internal temperature should reach 205°F to 210°F (96°C to 99°C).

[41 tokens in 1.84 s, 22.3 tok/s]

User: 
```

Simply type your question and press **Enter**.

#### Runtime Sampling & Acceleration Controls

The on-device firmware supports dynamic adjustment of decoding and acceleration parameters directly from the serial prompt:
* `/temp <val>`: Set softmax temperature between `0.0` and `2.0` (default: `0.75`).
* `/topp <val>`: Set nucleus top-p probability threshold between `0.0` and `1.0` (default: `0.90`).
* `/subvocab [on|off|<n>]`: Enable, disable, or adjust active sub-vocabulary clusters (`1`-`16`, default: `off`). Full-head SIMD is active by default for 100% domain accuracy at ~14.5 tok/s. Set to `on` or `4` for experimental maximum throughput (~16.5 tok/s).
* `/simd`: Query status of ESP32-S3 PIE (Processor Instruction Extensions) 128-bit SIMD vector engine.
* `/config`: Inspect active temperature, top-p, repetition window, sub-vocab clustering, and SIMD status.

In addition, the autoregressive generation loop includes:
* **ESP32-S3 PIE 128-bit SIMD Acceleration**: Computes INT8 dot products at 16 parallel multiply-accumulations per cycle using custom Xtensa LX7 PIE vector instructions (`ee.zero.accx`, `ee.vld.128.ip`, `ee.vmulas.s8.accx.ld.ip`, `rur.accx_0`).
* **Sub-Vocabulary Prediction (Hierarchical Softmax)**: Token embeddings are pre-clustered into 16 spherical clusters with INT8 centroids. At inference, cluster centroids are scored first via SIMD, evaluating only candidate tokens in top-predicted clusters plus guaranteed specials (~233 tokens vs 1,882 tokens, an 86.8% reduction in dot products).
* **Distance-Weighted Repetition Penalty**: Evaluates a rolling 32-token window, applying stronger suppression to recently emitted tokens (`factor = 0.80 + 0.15 * d / 32`).
* **Adaptive Sentence Wrap-up**: Smoothly boosts `<eos>` and punctuation (`.`, `?`) logits as generation nears the token budget to avoid abruptly truncated sentences.

### 5. OpenAI-Compatible WiFi HTTP API & Open WebUI

The firmware exposes an OpenAI-compatible HTTP server directly on port `8080` over WiFi.

#### 1. Configure WiFi Credentials
Copy `firmware/src/secrets.h.example` to `firmware/src/secrets.h` and enter your network credentials:
```cpp
// firmware/src/secrets.h (gitignored)
#pragma once
#define WIFI_SSID     "YourNetworkName"
#define WIFI_PASSWORD "YourPassword"
```

#### 2. Configure Device IP & Test via Taskfile
Copy `.env.example` to `.env` and enter your device's local IP address:
```bash
cp .env.example .env
# Edit DEVICE_IP in .env (e.g. DEVICE_IP=192.168.1.100)
```

Test the on-device HTTP server directly with `task`:
```bash
# Check available model endpoint
task models-http

# Query chat completions
task test-http PROMPT="Why is my bread gummy?"
```

#### 3. Connect via `curl`
```bash
curl -X POST http://<device-ip>:8080/v1/chat/completions \
  -H "Content-Type: application/json" \
  -d '{"model":"esp32-sourdough","messages":[{"role":"user","content":"Why is my bread gummy?"}]}'
```

#### 4. Connect via Open WebUI
In Open WebUI → **Settings → Connections → OpenAI API**:
* **Base URL**: `http://<device-ip>:8080/v1`
* **API Key**: `anything` (ignored by device)
* **Model**: `esp32-sourdough`

---

## :bar_chart: On-Device Benchmark & Performance

To verify throughput and generation quality against recorded baselines:
```bash
task test-device
```

### Performance & Scaling Comparison Across Benchmark Runs (ESP32-S3 @ 240 MHz)

| Parameter / Metric | Run 1: Baseline (4L, $D=128$) | Run 2: Configured (4L, $D=128$) | Run 3: Scaled (6L, $D=160$) | Run 4: Optimized Default (6L, SIMD Full Head) | Run 5: Expanded Vocab (6L, SIMD Full Head) | Sub-Vocab Mode (6L, SIMD+SubVocab) |
| :--- | :--- | :--- | :--- | :--- | :--- | :--- |
| **Model Size (INT4)** | ~2.5 MB | ~2.5 MB | 3.87 MB | 3.95 MB | 3.95 MB | 3.87 MB |
| **Layers ($L$)** | 4 | 4 | 6 | 6 | 6 | 6 |
| **Hidden Dim ($D$)** | 128 | 128 | 160 | 160 | 160 | 160 |
| **FFN Dim ($D_{ffn}$)** | 351 | 351 | 448 | 448 | 448 | 448 |
| **Attention Heads** | 4 | 4 | 4 | 4 | 4 | 4 |
| **Vocabulary Size** | 4096 (5655 PLE total) | 4096 (5655 PLE total) | 4096 (5796 PLE total) | 4096 (5796 PLE total) | **4096 (6106 PLE total)** | 4096 (5796 PLE total) |
| **Output Head Method** | Full head (1,737 classes) | Full head (1,737 classes) | Full head (1,882 classes) | **Full head (1,882 classes, 100% exact)** | **Full head (2,197 classes, +315 words)** | **Sub-Vocab (top 4/16 clusters, ~233 classes)** |
| **SIMD Vector Engine** | Scalar C-loop | Scalar C-loop | Scalar C-loop | **ESP32-S3 PIE 128-bit SIMD (`ee.vmulas.s8`)** | **ESP32-S3 PIE 128-bit SIMD (`ee.vmulas.s8`)** | **ESP32-S3 PIE 128-bit SIMD (`ee.vmulas.s8`)** |
| **Staged PSRAM Tensors** | 30 | 30 | 44 | 44 | 44 | 44 |
| **Free SRAM** | 320.7 KB | 320.7 KB | 310.5 KB | 306.4 KB | 306.4 KB | 306.4 KB |
| **Free PSRAM** | 6.28 MB | 6.28 MB | 4.49 MB | 4.47 MB | **4.41 MB** | 4.47 MB |
| **Sampling Mode** | Greedy (argmax) | Top-$p$ ($p=0.9, T=0.75$) | Top-$p$ ($p=0.9, T=0.75$, rep=32) | Top-$p$ ($p=0.9, T=0.75$, rep=32) | Top-$p$ ($p=0.9, T=0.75$, rep=32) | Top-$p$ ($p=0.9, T=0.75$, rep=32) |
| **Average Throughput** | **14.1 tok/s** (71 ms/tok) | **12.9 tok/s** (77.5 ms/tok) | **6.6 tok/s** (151.5 ms/tok) | **14.5 tok/s** (69.2 ms/tok) | **13.9 tok/s** (72.1 ms/tok) | **16.5 tok/s** (60.6 ms/tok) |
| **Generation Fidelity** | High | High | High (flawless domain accuracy) | **High (flawless domain accuracy)** | **High (+315 expanded baking classes)** | Experimental (coherence trade-off) |
| **Speedup vs Run 3** | — | — | Baseline (1.00×) | **+119.7% (2.20× speedup)** | **+110.6% (2.11× speedup)** | **+150.0% (2.50× speedup)** |

---

## :link: References

*   [slvDev/esp32-ai-barista](https://huggingface.co/slvDev/esp32-ai-barista) - Dedicated espresso troubleshooting LLM for ESP32
*   [karpathy/llama2.c](https://github.com/karpathy/llama2.c) - Minimalist C inference engine

## :balance_scale: License

[Apache License 2.0](LICENSE)

## :writing_hand: Author

This project was started in 2026 by [Nicholas Wilde](https://github.com/nicholaswilde/).
