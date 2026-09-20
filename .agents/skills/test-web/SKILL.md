---
name: test-web
description: Test and inspect the ESP32-S3 Catppuccin Mocha Web UI, settings persistence, OTA update page, and on-device inference over WiFi.
---

# Test & Inspect Web UI (`test-web`)

When the user asks to test, inspect, or verify the ESP32-S3 web pages (Landing page, Settings page, OTA page), test parameter persistence across NVS, or check live on-device inference through the web interface, use this skill.

## Capabilities

1. **TCP Connectivity Verification**:
   - Verifies device IP and port (default `8080`) are reachable on the local network.
2. **Landing Page & Web Chat REPL (`GET /`)**:
   - Validates `200 OK` HTML response.
   - Verifies Catppuccin Mocha palette color tokens (`#1e1e2e`, `#181825`, `#313244`, `#cdd6f4`, `#cba6f7`, `#f5c2e7`, `#89b4fa`).
   - Extracts live telemetry badges (Wi-Fi SSID, RSSI dBm, Device IP, Free PSRAM, Free SRAM).
   - Validates in-browser Chat REPL container and navigation actions.
3. **Settings Page (`GET /settings`)**:
   - Validates `200 OK` HTML response.
   - Extracts current temperature, top-p, and sub-vocabulary cluster configuration.
   - Extracts hardware partition and memory telemetry table rows.
4. **Settings Persistence Test (`POST /settings/save`)**:
   - Submits parameter updates via HTTP form POST.
   - Verifies Catppuccin Mocha confirmation card (`✓ Settings Saved`).
   - Re-fetches `/settings` to verify that values were persisted in ESP32 `Preferences` flash memory.
5. **OTA Firmware Page (`GET /update`)**:
   - Validates `200 OK` HTML response.
   - Verifies drag-and-drop file upload zone and progress bar elements.
6. **Live Inference Over HTTP (`POST /v1/chat/completions`)**:
   - Sends a test sourdough query to the OpenAI-compatible endpoint.
   - Measures token throughput (`tok/s`), completion latency, and response content.

---

## Usage

### 1. Run Complete Web Suite via Taskfile

```bash
task test-web
```

### 2. Run Directly via Python Script

```bash
uv run python .agents/skills/test-web/scripts/test_web.py
```

### 3. Specify Target IP or Custom Prompt

```bash
uv run python .agents/skills/test-web/scripts/test_web.py --ip 192.168.1.240 --prompt "How do I feed my sourdough starter?"
```

### 4. Read-Only Mode (Skip Modifying Settings)

```bash
uv run python .agents/skills/test-web/scripts/test_web.py --no-save
```

### 5. Machine-Readable JSON Export

```bash
uv run python .agents/skills/test-web/scripts/test_web.py --json
```
