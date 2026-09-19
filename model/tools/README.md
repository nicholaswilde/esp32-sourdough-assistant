---
language:
- en
license: apache-2.0
tags:
- esp32
- esp32-s3
- sourdough
- baking
- edge-ai
- quantized
- int4
- embedded
- ple
pipeline_tag: text-generation
---

# ESP32-S3 Sourdough Bread Baking Assistant

An offline, edge AI language model trained specifically to answer sourdough baking and troubleshooting questions directly on an **ESP32-S3** microcontroller.

Inspired by [slvDev/esp32-ai-barista](https://huggingface.co/slvDev/esp32-ai-barista) and built inside the **[esp32-sandbox](https://github.com/nicholaswilde/esp32-sandbox)** project (`projects/s3-sourdough`).

## Model Details

- **Target Hardware**: ESP32-S3 (e.g., ESP32-S3-DevKitC-1-N16R8)
- **Architecture**: Per-Layer Embeddings (PLE) micro-LLM
- **Flash Memory Required**: ≥ 16MB
- **PSRAM Required**: ≥ 8MB (Octal SPI recommended)
- **Vocabulary**: Asymmetric architecture (4,096 BPE input encoder, 1,737 curated whole-word output classes)
- **Quantization**: INT4 grouped quantization (`group_size = 128`) with untied output head
- **Partition Offset**: `0x110000` (mapped via `esp_partition_mmap`)
- **Training Dataset**: `sourdough_qa.jsonl` (5,000 conversational Q&A pairs covering 111 curated sourdough baking topics with leak-free validation split)
- **Domain Scope**:
  - Starter health (hooch, mold, feeding ratios, acetone smells, sluggish rise, drying/reviving)
  - Bulk fermentation (under/over-proofing signs, poke test, temperature, DDT formula)
  - Hydration & shaping (sticky dough, rice flour bannetons, cold retard, batard stitching)
  - Scoring & baking (steam, ear development, gummy crumb prevention, blisters, temperatures)
  - Baker's math & percentages (100/70/20/2 formulas, preferment %, inclusion math)
  - Guardrails (out-of-domain refusals, toxic food hazards, medical disclaimers)

## Quick Flashing to ESP32-S3

```bash
# 1. Download model binary and tokenizer
hf download nicholascwilde/esp32-s3-sourdough sourdough_q4.bin --local-dir .

# 2. Flash to model partition (0x110000)
esptool --baud 921600 --port /dev/ttyACM0 write-flash 0x110000 sourdough_q4.bin
```

## Running Inference

Refer to the [esp32-sandbox repository](https://github.com/nicholaswilde/esp32-sandbox/tree/main/projects/s3-sourdough) for firmware building, flashing, and interactive USB serial querying.
