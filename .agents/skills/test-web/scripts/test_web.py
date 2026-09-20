#!/usr/bin/env python3
"""Web UI and Device Test Suite for ESP32 Sourdough Assistant.

Performs automated end-to-end testing of the on-device Catppuccin Mocha Web UI:
  1. Network connectivity and TCP port verification
  2. Landing Page (GET /): Status, Catppuccin Mocha styling, live memory & Wi-Fi badges
  3. Settings Page (GET /settings): Sliders, subvocab options, telemetry table
  4. Settings Save & Persistence (POST /settings/save): Live parameter updates and NVS persistence
  5. OTA Firmware Page (GET /update): Drag-and-drop elements & progress bar
  6. Live Inference API (POST /v1/chat/completions): End-to-end token generation, latency, throughput

Usage:
  uv run python .agents/skills/test-web/scripts/test_web.py [OPTIONS]
"""

import argparse
import json
import os
import re
import socket
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

# Catppuccin Mocha essential color tokens
MOCHA_TOKENS = {
    "Base": "#1e1e2e",
    "Mantle": "#181825",
    "Crust": "#11111b",
    "Surface0": "#313244",
    "Text": "#cdd6f4",
    "Subtext0": "#a6adc8",
    "Mauve": "#cba6f7",
    "Pink": "#f5c2e7",
    "Blue": "#89b4fa",
    "Green": "#a6e3a1",
}


def find_repo_root() -> Path:
    """Find repository root directory."""
    curr = Path(__file__).resolve()
    for parent in [curr] + list(curr.parents):
        if (parent / ".git").exists() or (parent / "Taskfile.yml").exists():
            return parent
    return Path.cwd()


def load_env_config(repo_root: Path) -> Tuple[str, int]:
    """Read DEVICE_IP and DEVICE_PORT from .env file or default to standard IP."""
    env_file = repo_root / ".env"
    ip = "192.168.1.240"
    port = 8080

    if env_file.exists():
        for line in env_file.read_text(encoding="utf-8").splitlines():
            line = line.strip()
            if not line or line.startswith("#"):
                continue
            if "=" in line:
                k, v = line.split("=", 1)
                k = k.strip()
                v = v.strip().strip('"').strip("'")
                if k == "DEVICE_IP" and v:
                    ip = v
                elif k == "DEVICE_PORT" and v:
                    try:
                        port = int(v)
                    except ValueError:
                        pass
    return ip, port


def check_tcp_port(ip: str, port: int, timeout: float = 2.5) -> bool:
    """Check if TCP port is open and accepting connections."""
    s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    s.settimeout(timeout)
    try:
        s.connect((ip, port))
        s.close()
        return True
    except Exception:
        return False


def http_request(
    url: str,
    method: str = "GET",
    headers: Optional[Dict[str, str]] = None,
    data: Optional[bytes] = None,
    timeout: float = 10.0,
) -> Tuple[int, Dict[str, str], str, float]:
    """Perform HTTP request and return (status, headers, body_str, elapsed_sec)."""
    req_headers = {"User-Agent": "test-web-suite/1.0"}
    if headers:
        req_headers.update(headers)

    t0 = time.time()
    try:
        req = urllib.request.Request(url, data=data, headers=req_headers, method=method)
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            body = resp.read().decode("utf-8", errors="replace")
            elapsed = time.time() - t0
            resp_headers = {k.lower(): v for k, v in resp.headers.items()}
            return resp.status, resp_headers, body, elapsed
    except urllib.error.HTTPError as e:
        elapsed = time.time() - t0
        body = e.read().decode("utf-8", errors="replace")
        resp_headers = {k.lower(): v for k, v in e.headers.items()}
        return e.code, resp_headers, body, elapsed
    except Exception as e:
        elapsed = time.time() - t0
        return -1, {}, str(e), elapsed


class WebTester:
    def __init__(self, ip: str, port: int, verbose: bool = False):
        self.ip = ip
        self.port = port
        self.base_url = f"http://{ip}:{port}"
        self.verbose = verbose
        self.results: Dict[str, Any] = {}

    def run_all(self, prompt: str = "Why is my bread gummy?", test_save: bool = True) -> bool:
        print(f"\n=======================================================")
        print(f"  🍞 ESP32-S3 Sourdough Assistant Web UI Test Suite   ")
        print(f"  Target: {self.base_url}                             ")
        print(f"=======================================================\n")

        # 1. Connectivity Check
        print(f"[*] Step 1: Checking TCP connectivity on {self.ip}:{self.port}...")
        if not check_tcp_port(self.ip, self.port):
            print(f"[-] ERROR: Port {self.port} on {self.ip} is not reachable.")
            self.results["connectivity"] = False
            return False
        print(f"    [+] Port {self.port} is reachable!")
        self.results["connectivity"] = True

        # 2. Landing Page
        print(f"\n[*] Step 2: Testing Landing & Web Chat REPL (GET /)...")
        landing_ok = self.test_landing_page()

        # 3. Settings Page
        print(f"\n[*] Step 3: Testing Settings Page (GET /settings)...")
        settings_ok, original_settings = self.test_settings_page()

        # 4. Settings Update & Persistence
        if test_save and settings_ok:
            print(f"\n[*] Step 4: Testing Settings Save & NVS Persistence (POST /settings/save)...")
            save_ok = self.test_settings_save(original_settings)
        else:
            save_ok = True

        # 5. OTA Firmware Page
        print(f"\n[*] Step 5: Testing OTA Update Page (GET /update)...")
        ota_ok = self.test_ota_page()

        # 6. Live Inference API
        print(f"\n[*] Step 6: Testing On-Device Inference API (POST /v1/chat/completions)...")
        inference_ok = self.test_inference(prompt)

        # Summary
        all_ok = landing_ok and settings_ok and save_ok and ota_ok and inference_ok
        print(f"\n=======================================================")
        print(f"  Test Results Summary: {'ALL PASSED [✓]' if all_ok else 'FAILED [✗]'}")
        print(f"=======================================================")
        print(f"  - TCP Connectivity:        [✓] Pass")
        print(f"  - Landing & Chat Page:     [{'✓' if landing_ok else '✗'}] {'Pass' if landing_ok else 'Fail'}")
        print(f"  - Settings Page:           [{'✓' if settings_ok else '✗'}] {'Pass' if settings_ok else 'Fail'}")
        if test_save:
            print(f"  - Settings Persistence:    [{'✓' if save_ok else '✗'}] {'Pass' if save_ok else 'Fail'}")
        print(f"  - OTA Firmware Page:       [{'✓' if ota_ok else '✗'}] {'Pass' if ota_ok else 'Fail'}")
        print(f"  - Live Model Inference:    [{'✓' if inference_ok else '✗'}] {'Pass' if inference_ok else 'Fail'}")
        print(f"=======================================================\n")
        return all_ok

    def test_landing_page(self) -> bool:
        status, headers, body, elapsed = http_request(f"{self.base_url}/")
        if status != 200:
            print(f"    [-] Expected status 200, got {status}")
            return False

        # Verify Catppuccin Mocha tokens
        missing_tokens = [k for k, hex_val in MOCHA_TOKENS.items() if hex_val.lower() not in body.lower()]
        if missing_tokens:
            print(f"    [-] Warning: Missing expected Mocha tokens: {missing_tokens}")

        # Extract Telemetry Badges
        badges = re.findall(r'<div class="badge">(.*?)</div>', body, re.DOTALL)
        clean_badges = [re.sub(r"<[^>]+>", "", b).strip() for b in badges]
        print(f"    [+] Status 200 OK ({elapsed:.2f}s, {len(body)} bytes)")
        print(f"    [+] Live Badges Found: {len(clean_badges)}")
        for b in clean_badges:
            print(f"        • {b}")

        # Verify Chat REPL elements
        has_chat = "chat-container" in body and "btn-send" in body
        has_nav = "/settings" in body and "/update" in body and "/reset" in body
        print(f"    [+] Chat REPL Container: {'Present' if has_chat else 'Missing'}")
        print(f"    [+] Navigation Links: {'Present' if has_nav else 'Missing'}")

        self.results["landing"] = {
            "status": status,
            "elapsed_sec": round(elapsed, 3),
            "badges": clean_badges,
            "has_chat": has_chat,
            "has_nav": has_nav,
        }
        return status == 200 and has_chat and has_nav

    def test_settings_page(self) -> Tuple[bool, Dict[str, Any]]:
        status, headers, body, elapsed = http_request(f"{self.base_url}/settings")
        if status != 200:
            print(f"    [-] Expected status 200, got {status}")
            return False, {}

        # Extract current input values
        temp_match = re.search(r'name="temperature"[^>]*value="([^"]+)"', body)
        topp_match = re.search(r'name="topp"[^>]*value="([^"]+)"', body)
        subvocab_match = re.search(r'<option value="(\d+)"\s+selected>', body)

        current_temp = float(temp_match.group(1)) if temp_match else 0.75
        current_topp = float(topp_match.group(1)) if topp_match else 0.90
        current_subvocab = int(subvocab_match.group(1)) if subvocab_match else 0

        # Extract Telemetry Rows
        table_rows = re.findall(r"<tr><td>(.*?)</td><td>(.*?)</td></tr>", body)
        print(f"    [+] Status 200 OK ({elapsed:.2f}s)")
        print(f"    [+] Current Config: temp={current_temp}, top_p={current_topp}, subvocab_clusters={current_subvocab}")
        print(f"    [+] Hardware Telemetry:")
        for label, val in table_rows:
            print(f"        • {label}: {val}")

        settings_data = {
            "temperature": current_temp,
            "topp": current_topp,
            "subvocab": current_subvocab,
            "telemetry": dict(table_rows),
        }
        self.results["settings"] = settings_data
        return True, settings_data

    def test_settings_save(self, original_settings: Dict[str, Any]) -> bool:
        orig_temp = original_settings.get("temperature", 0.75)
        orig_topp = original_settings.get("topp", 0.90)
        orig_subvocab = original_settings.get("subvocab", 0)

        # Target test values
        test_temp = 0.65 if orig_temp != 0.65 else 0.80
        test_topp = 0.85 if orig_topp != 0.85 else 0.95
        test_subvocab = 4 if orig_subvocab != 4 else 2

        print(f"    [*] Submitting update: temp={test_temp}, top_p={test_topp}, subvocab={test_subvocab}")
        form_data = urllib.parse.urlencode({
            "temperature": str(test_temp),
            "topp": str(test_topp),
            "subvocab": str(test_subvocab),
        }).encode("utf-8")

        status, headers, body, elapsed = http_request(
            f"{self.base_url}/settings/save",
            method="POST",
            headers={"Content-Type": "application/x-www-form-urlencoded"},
            data=form_data,
        )

        if status != 200:
            print(f"    [-] POST /settings/save failed with status {status}")
            return False

        has_confirm = "Settings Saved" in body
        print(f"    [+] POST /settings/save: {status} OK ({elapsed:.2f}s) - Confirmation card: {has_confirm}")

        # Re-fetch /settings to confirm persistence
        status_get, _, body_get, _ = http_request(f"{self.base_url}/settings")
        temp_match = re.search(r'name="temperature"[^>]*value="([^"]+)"', body_get)
        topp_match = re.search(r'name="topp"[^>]*value="([^"]+)"', body_get)
        subvocab_match = re.search(r'<option value="(\d+)"\s+selected>', body_get)

        read_temp = float(temp_match.group(1)) if temp_match else None
        read_topp = float(topp_match.group(1)) if topp_match else None
        read_subvocab = int(subvocab_match.group(1)) if subvocab_match else None

        persisted = (read_temp == test_temp) and (read_topp == test_topp) and (read_subvocab == test_subvocab)
        print(f"    [+] NVS Readback: temp={read_temp}, top_p={read_topp}, subvocab={read_subvocab}")
        print(f"    [+] NVS Persistence Check: {'PASSED [✓]' if persisted else 'FAILED [✗]'}")

        self.results["settings_save"] = {
            "status": status,
            "persisted": persisted,
            "test_values": {"temp": test_temp, "topp": test_topp, "subvocab": test_subvocab},
            "read_values": {"temp": read_temp, "topp": read_topp, "subvocab": read_subvocab},
        }
        return persisted

    def test_ota_page(self) -> bool:
        status, headers, body, elapsed = http_request(f"{self.base_url}/update")
        if status != 200:
            print(f"    [-] Expected status 200, got {status}")
            return False

        has_dropzone = "dropZone" in body
        has_file_input = 'type="file"' in body
        has_progress = "progressBar" in body

        print(f"    [+] Status 200 OK ({elapsed:.2f}s)")
        print(f"    [+] Drop Zone Element:    {'Present' if has_dropzone else 'Missing'}")
        print(f"    [+] Firmware File Input:  {'Present' if has_file_input else 'Missing'}")
        print(f"    [+] Progress Bar Element: {'Present' if has_progress else 'Missing'}")

        self.results["ota"] = {
            "status": status,
            "has_dropzone": has_dropzone,
            "has_file_input": has_file_input,
            "has_progress": has_progress,
        }
        return status == 200 and has_dropzone and has_file_input

    def test_inference(self, prompt: str) -> bool:
        payload = {
            "model": "esp32-sourdough",
            "messages": [{"role": "user", "content": prompt}],
        }
        data = json.dumps(payload).encode("utf-8")

        print(f"    [*] Sending query: \"{prompt}\"")
        status, headers, body, elapsed = http_request(
            f"{self.base_url}/v1/chat/completions",
            method="POST",
            headers={"Content-Type": "application/json"},
            data=data,
            timeout=15.0,
        )

        if status != 200:
            print(f"    [-] Inference request failed with status {status}: {body}")
            return False

        try:
            res_json = json.loads(body)
            answer = res_json["choices"][0]["message"]["content"]
            usage = res_json.get("usage", {})
            comp_tokens = usage.get("completion_tokens", 0)
            tok_sec = round(comp_tokens / elapsed, 1) if elapsed > 0 and comp_tokens > 0 else 0

            print(f"    [+] Response (Status 200 OK in {elapsed:.2f}s):")
            print(f"        \"{answer}\"")
            print(f"    [+] Tokens: {comp_tokens} completion tokens ({tok_sec} tok/s)")

            self.results["inference"] = {
                "status": status,
                "prompt": prompt,
                "answer": answer,
                "elapsed_sec": round(elapsed, 2),
                "completion_tokens": comp_tokens,
                "tokens_per_sec": tok_sec,
            }
            return len(answer.strip()) > 0
        except Exception as e:
            print(f"    [-] Failed to parse response JSON: {e}")
            return False


def main():
    parser = argparse.ArgumentParser(description="Test & Inspect ESP32 Sourdough Assistant Web Interface")
    parser.add_argument("--ip", type=str, help="Device IP address override")
    parser.add_argument("--port", type=int, help="Device port override (default 8080)")
    parser.add_argument("--prompt", type=str, default="Why is my bread gummy?", help="Prompt to test on-device inference")
    parser.add_argument("--no-save", action="store_true", help="Skip modifying settings via POST /settings/save")
    parser.add_argument("--json", action="store_true", help="Output result dictionary in JSON format")
    args = parser.parse_args()

    repo_root = find_repo_root()
    env_ip, env_port = load_env_config(repo_root)

    ip = args.ip if args.ip else env_ip
    port = args.port if args.port else env_port

    tester = WebTester(ip=ip, port=port)
    success = tester.run_all(prompt=args.prompt, test_save=not args.no_save)

    if args.json:
        print("\n" + json.dumps(tester.results, indent=2))

    sys.exit(0 if success else 1)


if __name__ == "__main__":
    main()
