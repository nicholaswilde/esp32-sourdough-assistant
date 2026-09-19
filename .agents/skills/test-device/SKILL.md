---
name: test-device
description: Reset, monitor boot logs, and interactively test on-device LLM/REPL firmware over serial on connected ESP32 devices.
---

# Test & Monitor Device (`test-device`)

When the user asks to reset the connected ESP32 device, check its serial output, inspect bootloader logs, or interact with its on-device LLM REPL to evaluate generation quality and speed, use this skill.

## Capabilities

1. **Hardware Reset**: Pulses the RTS/DTR lines via USB-UART to trigger a clean hardware reboot (`rst:0x15 (USB_UART_CHIP_RESET)`).
2. **Boot Diagnostics**: Captures ROM bootloader, partition table mount, memory allocation stats (SRAM / PSRAM), and model architecture banner.
3. **Automated Batch Testing**: Sends test prompt questions, extracts assistant responses, and computes latency and throughput (`tok/s`).
4. **Interactive REPL**: Opens a persistent terminal chat session directly with the on-device model.
5. **Machine-Readable Benchmarks**: Exports structured JSON containing boot logs, emitted tokens, elapsed seconds, and throughput.

## Prerequisites

- **Python Environment**: Run via `uv run --with pyserial python ...` (no persistent pip install required).
- **Device Connection**: ESP32-S3 connected via USB (`/dev/ttyACM0`, `/dev/ttyUSB0`).

## Usage

### 1. Reset and Run Default Benchmark Queries

Auto-detects the connected device port, triggers a hardware reset, prints the boot banner, and sends 3 standard domain queries:

```bash
uv run --with pyserial python .agents/skills/test-device/scripts/test_device.py
```

### 2. Test Specific Questions

```bash
uv run --with pyserial python .agents/skills/test-device/scripts/test_device.py \
  --query "Why is there liquid on top of my sourdough starter?" \
  --query "Why is my bread gummy?"
```

### 3. Connect Without Resetting (Existing Session)

To inspect or query a device that is already booted and waiting at the prompt:

```bash
uv run --with pyserial python .agents/skills/test-device/scripts/test_device.py \
  --no-reset \
  --query "What is hooch?"
```

### 4. Interactive REPL Mode

Launch a live interactive terminal session:

```bash
uv run --with pyserial python .agents/skills/test-device/scripts/test_device.py --interactive
```

### 5. Export JSON Benchmark Results

Produces structured JSON with latency and token-per-second statistics:

```bash
uv run --with pyserial python .agents/skills/test-device/scripts/test_device.py \
  --query "How do I feed my starter?" \
  --json
```

Sample JSON output:
```json
{
  "port": "/dev/ttyACM0",
  "baud": 115200,
  "boot_log": "...",
  "results": [
    {
      "prompt": "How do I feed my starter?",
      "answer": "warm, or 1 to is a a for to until.",
      "tokens": 12,
      "time_s": 1.09,
      "tok_per_sec": 11.0
    }
  ]
}
```

### 6. Specifying Custom Port and Baud Rate

```bash
uv run --with pyserial python .agents/skills/test-device/scripts/test_device.py \
  --port /dev/ttyACM1 \
  --baud 115200
```

## Troubleshooting

- **`Permission denied: '/dev/ttyACM0'`**: Ensure user is in `dialout` group (`sudo usermod -a -G dialout $USER`) or check device permissions.
- **Port Busy / `Resource temporarily unavailable`**: Close any active `pio device monitor`, `minicom`, or `screen` instances holding the serial device.
- **Garbled Boot Output**: Ensure `monitor_speed = 115200` in `platformio.ini` matches the script's default baud rate.
