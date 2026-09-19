# ESP32-S3 Sourdough Baker Assistant - Firmware

This directory contains the PlatformIO C++ firmware project for the **ESP32-S3-DevKitC-1-N16R8** microcontroller.

> [!IMPORTANT]
> **Hardware Compatibility**: This firmware is strictly configured for the **ESP32-S3 N16R8** (16MB Flash, 8MB Octal PSRAM). Smaller variants (N4, N8, R2, or non-PSRAM boards) will fail due to flash partition size constraints (`0xAE0000` model partition) and runtime PSRAM memory requirements. Non-S3 chips lack the Xtensa LX7 SIMD instruction set.

---

## 📁 Directory Layout

```
firmware/
├── platformio.ini         # PlatformIO build configuration
├── partitions.csv         # Flash partition table (dual OTA app banks, model at 0x520000)
├── pyproject.toml         # Minimal Python dependencies (huggingface-hub, pyserial)
├── Taskfile.yml           # Firmware automation tasks
├── download_model_hf.py   # Download model weights from Hugging Face Hub
├── src/                   # C++ firmware source code
│   ├── main.cpp           # App entry point, HTTP REST API, CLI REPL
│   ├── llm.h              # INT4 PLE transformer inference engine
│   ├── bpe_tokenizer.h    # ByteLevel BPE tokenizer
│   ├── simd_dotp.S        # Hand-optimized Xtensa LX7 SIMD assembly
│   ├── secrets.h.example  # WiFi credentials template
│   └── generated/         # Pre-compiled C headers for vocabulary & layout
├── models/                # Downloaded quantized model binary (sourdough_q4.bin)
├── runs/                  # Historical on-device benchmark JSON records
└── test/                  # Host-native unit tests
```

---

## 🚀 Quick Start

### 1. Configure WiFi (Optional)
Copy the template and edit your WiFi SSID and password:
```bash
cp src/secrets.h.example src/secrets.h
```

### 2. Download Pre-trained Model
Download the quantized model binary and configuration directly from Hugging Face:
```bash
task download-model
```
*(Optionally specify a custom repo: `task download-model REPO=username/repo`)*

### 3. Build & Test
Run host-native unit tests:
```bash
task test
```

Build the ESP32-S3 firmware:
```bash
task build
```

### 4. Flash to ESP32-S3
Flash the compiled model binary to the flash partition (`0x520000`):
```bash
task flash-model
```

Flash the firmware program over USB:
```bash
task flash
```

Or perform an Over-The-Air (OTA) firmware update over WiFi:
```bash
task ota
```

Open the serial monitor:
```bash
task monitor
```

---

## 📊 Benchmarking & Device Testing

### Serial Testing & Benchmarks
Test on-device inference over USB serial:
```bash
task test-device
task test-device PROMPT="Why is my bread gummy?"
```

Record and compare hardware benchmark metrics against baseline:
```bash
task benchmark
task benchmark RUN=true NAME=my_new_run
```

### WiFi HTTP API Testing & Evaluation
Configure device IP in `.env` (copied from `.env.example` in repo root):
```bash
task models-http
task test-http PROMPT="Why is my bread gummy?"
```

Run automated HTTP health check, response quality evaluation, and diagnostic checks:
```bash
task eval-http
task eval-http PROMPT="Why is my bread gummy?" DIAGNOSE=true
```
