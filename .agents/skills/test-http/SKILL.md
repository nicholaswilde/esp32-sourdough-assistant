---
name: test-http
description: Run on-device HTTP API tests via task test-http, evaluate OpenAI-compatible response quality and throughput, and diagnose/fix issues.
---

# Test & Evaluate HTTP API (`test-http`)

When the user asks to test or verify the ESP32-S3 over WiFi via `task test-http`, evaluate response quality, diagnose network or generation anomalies (such as word salad, repetition loops, or connection errors), or automatically fix device configuration issues, use this skill.

## Capabilities

1. **Automated Health & Latency Checks**: Tests `/v1/models` and `/v1/chat/completions` on port `8080`.
2. **OpenAI Schema Validation**: Validates JSON structure (`id`, `object`, `choices[0].message.content`, `usage`).
3. **Response Quality & Coherence Scoring**:
   - Detects **Word Salad**: High-entropy disconnected words from corrupted or undertrained weights.
   - Detects **Mode Collapse**: Infinite repetition loops (e.g. repeated `, and, and, and`).
   - Detects **Truncation**: Premature end-of-sequence or incomplete sentences.
   - Evaluates **Domain Keyword Coverage**: Matches expected sourdough concepts (e.g., cooling times, internal temperature `205°F-210°F`, hooch, feeding ratios `1:1:1`).
4. **Hardware Diagnostic Engine**:
   - Validates `.env` IP and TCP port reachability.
   - Verifies local model binary checksum against the canonical verified weights (`da71c27d...`).
   - Checks flash partition offset alignment in `firmware/partitions.csv` (`0x520000`).
5. **Actionable Fix & Remediation**: Automatically downloads canonical weights or guides USB/OTA reflashing.

---

## Prerequisites

- **Device IP**: Configured in `.env` (copied from `.env.example`).
- **Python Environment**: Run via `uv run python ...`.

---

## Usage

### 1. Run Standard Evaluation Suite

Queries the device with standard sourdough troubleshooting questions and evaluates quality:

```bash
uv run python .agents/skills/test-http/scripts/test_http.py
```

### 2. Test a Custom Prompt

```bash
uv run python .agents/skills/test-http/scripts/test_http.py --prompt "Why is my bread gummy?"
```

### 3. Run Full System Diagnostics

Inspects device connectivity, model binary MD5 checksum, and partition table offsets:

```bash
uv run python .agents/skills/test-http/scripts/test_http.py --diagnose
```

### 4. Run Automated Fixes

If model weights mismatch or configuration issues are detected, `--fix` attempts automatic remediation:

```bash
uv run python .agents/skills/test-http/scripts/test_http.py --fix
```

### 5. Machine-Readable JSON Export

Outputs full telemetry, latency, token throughput, and diagnostic findings as JSON:

```bash
uv run python .agents/skills/test-http/scripts/test_http.py --json
```

---

## Troubleshooting & Remediation Guide

| Issue Code | Symptoms | Root Cause | Remediation Steps |
| :--- | :--- | :--- | :--- |
| **`NETWORK_UNREACHABLE`** | `curl: (7) Failed to connect`, connection timed out, HTTP -1 | 1. ESP32 assigned a new DHCP IP.<br>2. Device offline / rebooting.<br>3. WiFi credentials mismatch. | 1. Check active IP via serial monitor: `task monitor` or `task test-device`.<br>2. Update `DEVICE_IP` in `.env`.<br>3. Verify WiFi SSID/password in `firmware/src/secrets.h`. |
| **`WORD_SALAD`** | Emits random sourdough words ("float last reaction sides water cool...") | Model weights in flash partition are corrupted or undertrained. | 1. Run `uv run python .agents/skills/test-http/scripts/test_http.py --diagnose`.<br>2. Restore verified weights from HF: `task download-model`.<br>3. Flash model binary to device: `task flash-model`. |
| **`MODE_COLLAPSE`** | Repeating phrase over and over (`", and, and, and"`) | Repetition penalty disabled or logits saturation. | 1. Query interactive serial prompt: `/config`.<br>2. Ensure temperature is between `0.70` - `0.85`.<br>3. Verify repetition window (`RECENT_WINDOW = 32`). |
| **`PARTITION_OFFSET_MISMATCH`** | Device crashes on boot or loads garbage memory | `partitions.csv` offset doesn't match `write-flash` address (`0x520000`). | 1. Check `firmware/partitions.csv` has `model` at `0x520000`.<br>2. Flash partition table and model: `task flash-model && task flash`. |
| **`MALFORMED_JSON` / `HTTP 400`** | `{"error":"invalid json"}` or `{"error":"no user message"}` | Payload missing `messages` array or malformed JSON. | 1. Ensure JSON payload follows OpenAI format: `{"model":"esp32-sourdough","messages":[{"role":"user","content":"..."}]}`. |
