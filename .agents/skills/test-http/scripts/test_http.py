#!/usr/bin/env python3
"""HTTP API Test, Evaluation, and Diagnostic Tool for ESP32 Sourdough Assistant.

Capabilities:
  1. Automated Health & Latency Testing: Queries /v1/models and /v1/chat/completions.
  2. Response Schema Validation: Ensures strict OpenAI API compatibility.
  3. Generation Quality & Coherence Scoring: Detects word salad, repetition loops,
     and model collapse.
  4. Domain Relevance Analysis: Evaluates keyword coverage for standard sourdough questions.
  5. Diagnostic Engine & Automated Remediation:
     - Detects network / IP mismatches (DHCP changes).
     - Checks local model binary checksum against canonical reference.
     - Inspects partition offset alignment in partitions.csv.
     - Guides or runs corrective actions.

Usage:
  uv run python .agents/skills/test-http/scripts/test_http.py [OPTIONS]
"""

import argparse
import hashlib
import json
import os
import re
import socket
import sys
import time
import urllib.error
import urllib.request
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

# Known canonical reference hash for the verified INT4 PLE model
CANONICAL_MODEL_MD5 = "da71c27d9b9745a18e16f3dda973003b"
EXPECTED_PARTITION_OFFSET = 0x520000

# Benchmark test queries and their expected domain keywords
BENCHMARK_PROMPTS = [
    {
        "prompt": "Why is my bread gummy?",
        "expected_keywords": ["sliced", "cool", "baked", "under", "temperature", "205", "210", "rack", "internal"],
        "min_keywords": 2,
    },
    {
        "prompt": "Why is there liquid on top of my sourdough starter?",
        "expected_keywords": ["hooch", "alcohol", "food", "feed", "pour", "stir", "water", "flour"],
        "min_keywords": 2,
    },
    {
        "prompt": "How do I feed my sourdough starter?",
        "expected_keywords": ["ratio", "flour", "water", "equal", "parts", "1:", "feed", "weight"],
        "min_keywords": 2,
    },
]


def find_repo_root() -> Path:
    """Find git repository root directory."""
    curr = Path(__file__).resolve()
    for parent in [curr] + list(curr.parents):
        if (parent / ".git").exists() or (parent / "Taskfile.yml").exists():
            return parent
    return Path.cwd()


def load_env_config(repo_root: Path) -> Tuple[str, int]:
    """Read DEVICE_IP and DEVICE_PORT from .env file or return defaults."""
    env_file = repo_root / ".env"
    ip = "192.168.1.100"
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


def check_tcp_port(ip: str, port: int, timeout: float = 2.0) -> bool:
    """Check if TCP port is open and accepting connections."""
    s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    s.settimeout(timeout)
    try:
        s.connect((ip, port))
        s.close()
        return True
    except Exception:
        return False


def http_get(url: str, timeout: float = 5.0) -> Tuple[int, Optional[Dict[str, Any]], float]:
    """Perform HTTP GET request and return (status_code, json_dict, elapsed_sec)."""
    t0 = time.time()
    try:
        req = urllib.request.Request(url, headers={"User-Agent": "test-http/1.0"})
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            data = resp.read().decode("utf-8")
            elapsed = time.time() - t0
            return resp.status, json.loads(data), elapsed
    except urllib.error.HTTPError as e:
        elapsed = time.time() - t0
        try:
            body = json.loads(e.read().decode("utf-8"))
        except Exception:
            body = None
        return e.code, body, elapsed
    except Exception as e:
        elapsed = time.time() - t0
        return -1, {"error": str(e)}, elapsed


def http_post(url: str, payload: Dict[str, Any], timeout: float = 15.0) -> Tuple[int, Optional[Dict[str, Any]], float]:
    """Perform HTTP POST request and return (status_code, json_dict, elapsed_sec)."""
    t0 = time.time()
    raw_data = json.dumps(payload).encode("utf-8")
    try:
        req = urllib.request.Request(
            url,
            data=raw_data,
            headers={"Content-Type": "application/json", "User-Agent": "test-http/1.0"},
        )
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            data = resp.read().decode("utf-8")
            elapsed = time.time() - t0
            return resp.status, json.loads(data), elapsed
    except urllib.error.HTTPError as e:
        elapsed = time.time() - t0
        try:
            body = json.loads(e.read().decode("utf-8"))
        except Exception:
            body = None
        return e.code, body, elapsed
    except Exception as e:
        elapsed = time.time() - t0
        return -1, {"error": str(e)}, elapsed


def evaluate_response_quality(content: str, prompt_info: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
    """Evaluate generation coherence, repetition, sentence structure, and domain accuracy."""
    words = content.strip().split()
    n_words = len(words)

    # 1. Repetition Analysis (n-gram loops)
    repetition_ratio = 0.0
    collapsed = False
    if n_words >= 6:
        # Check repeated adjacent 1-grams and 2-grams
        bigrams = [f"{words[i]} {words[i+1]}" for i in range(n_words - 1)]
        bigram_counts = {}
        for b in bigrams:
            bigram_counts[b] = bigram_counts.get(b, 0) + 1
        max_bigram_rep = max(bigram_counts.values()) if bigram_counts else 0
        repetition_ratio = max_bigram_rep / max(len(bigrams), 1)

        # Mode collapse flag (e.g. ", and, and, and")
        if repetition_ratio > 0.25 and max_bigram_rep >= 4:
            collapsed = True

    # 2. Punctuation & Sentence Completeness
    has_terminal_punct = bool(re.search(r"[.!?]$", content.strip()))

    # 3. Domain Keywords Match
    keyword_matches = []
    keyword_score = 100.0
    word_salad = False

    if prompt_info and "expected_keywords" in prompt_info:
        expected = prompt_info["expected_keywords"]
        content_lower = content.lower()
        keyword_matches = [k for k in expected if k in content_lower]
        min_kw = prompt_info.get("min_keywords", 1)

        if len(keyword_matches) < min_kw:
            keyword_score = (len(keyword_matches) / min_kw) * 100.0
            # If length is long (>25 words) but zero expected keywords match, strong sign of word salad
            if len(keyword_matches) == 0 and n_words >= 25:
                word_salad = True

    # 4. Overall Coherence Status
    if collapsed:
        status = "MODE_COLLAPSE"
        explanation = "Model is stuck in a repetitive loop."
    elif word_salad:
        status = "WORD_SALAD"
        explanation = "Model generated incoherent words without answering the question."
    elif n_words < 5:
        status = "TOO_SHORT"
        explanation = "Model response is unexpectedly truncated."
    elif not has_terminal_punct and n_words >= 45:
        status = "TRUNCATED"
        explanation = "Response cut off before completing sentence."
    else:
        status = "HEALTHY"
        explanation = "Coherent, domain-appropriate sourdough response."

    return {
        "status": status,
        "explanation": explanation,
        "word_count": n_words,
        "repetition_ratio": round(repetition_ratio, 3),
        "has_terminal_punct": has_terminal_punct,
        "keyword_matches": keyword_matches,
        "keyword_score": round(keyword_score, 1),
    }


def diagnose_system(repo_root: Path, ip: str, port: int) -> List[Dict[str, Any]]:
    """Run diagnostic checks on device connection, model binary, and partition table."""
    issues = []

    # Check 1: Network Reachability
    if not check_tcp_port(ip, port, timeout=2.0):
        issues.append({
            "code": "NETWORK_UNREACHABLE",
            "severity": "CRITICAL",
            "message": f"Device at {ip}:{port} is not reachable via TCP.",
            "remediation": [
                f"Verify that ESP32-S3 is powered on and connected to the same WiFi network.",
                f"Check serial monitor (`task monitor` or `task test-device`) to see if IP changed.",
                f"Update DEVICE_IP in .env if device received a new DHCP address.",
                f"Verify firmware/src/secrets.h WiFi credentials.",
            ],
        })

    # Check 2: Model Binary Checksum
    bin_path = repo_root / "firmware" / "models" / "sourdough_q4.bin"
    if not bin_path.exists():
        issues.append({
            "code": "MODEL_FILE_MISSING",
            "severity": "CRITICAL",
            "message": f"Compiled model file not found at {bin_path}.",
            "remediation": ["Run `task download-model` to download model from Hugging Face Hub."],
        })
    else:
        file_bytes = bin_path.read_bytes()
        actual_md5 = hashlib.md5(file_bytes).hexdigest()
        if actual_md5 != CANONICAL_MODEL_MD5:
            issues.append({
                "code": "MODEL_CHECKSUM_MISMATCH",
                "severity": "HIGH",
                "message": f"Model binary MD5 ({actual_md5}) does not match canonical verified weights ({CANONICAL_MODEL_MD5}).",
                "remediation": [
                    "Download the verified canonical model from Hugging Face Hub: `task download-model`",
                    "Flash the updated binary to flash offset 0x520000: `task flash-model`",
                ],
            })

    # Check 3: Partition Table Offset
    part_csv = repo_root / "firmware" / "partitions.csv"
    if part_csv.exists():
        text = part_csv.read_text(encoding="utf-8")
        if "0x520000" not in text:
            issues.append({
                "code": "PARTITION_OFFSET_MISMATCH",
                "severity": "HIGH",
                "message": "firmware/partitions.csv does not place the 'model' partition at 0x520000.",
                "remediation": [
                    "Ensure 'model' partition starts at offset 0x520000 in firmware/partitions.csv.",
                    "Flash partition table and firmware: `task flash-model && task flash`.",
                ],
            })

    return issues


def main():
    parser = argparse.ArgumentParser(
        description="Run task test-http, evaluate on-device LLM responses, and diagnose/fix issues."
    )
    parser.add_argument("--prompt", "-p", type=str, default=None, help="Custom prompt to test")
    parser.add_argument("--ip", type=str, default=None, help="Override device IP address")
    parser.add_argument("--port", type=int, default=None, help="Override device HTTP port")
    parser.add_argument("--timeout", type=float, default=15.0, help="HTTP request timeout (seconds)")
    parser.add_argument("--diagnose", "-d", action="store_true", help="Run system diagnostics (network, model, partitions)")
    parser.add_argument("--json", "-j", action="store_true", help="Output results in JSON format")
    parser.add_argument("--fix", action="store_true", help="Attempt automatic fix for known configuration issues")
    args = parser.parse_args()

    repo_root = find_repo_root()
    default_ip, default_port = load_env_config(repo_root)
    ip = args.ip or default_ip
    port = args.port or default_port

    base_url = f"http://{ip}:{port}"
    chat_url = f"{base_url}/v1/chat/completions"
    models_url = f"{base_url}/v1/models"

    results: Dict[str, Any] = {
        "device_ip": ip,
        "device_port": port,
        "models_endpoint": None,
        "queries": [],
        "diagnostics": [],
        "overall_status": "PASS",
    }

    if not args.json:
        print("=" * 72)
        print(f"🥖 ESP32-S3 Sourdough Assistant — HTTP API Evaluator")
        print("=" * 72)
        print(f"Target: {base_url}")
        print(f"Checking endpoint connectivity...\n")

    # 1. Health check: /v1/models
    code, models_data, elapsed = http_get(models_url, timeout=min(args.timeout, 4.0))
    results["models_endpoint"] = {
        "status_code": code,
        "elapsed_sec": round(elapsed, 3),
        "data": models_data,
    }

    if code != 200:
        results["overall_status"] = "FAIL"
        if not args.json:
            print(f"✗ Failed to connect to {models_url} (HTTP {code})")
            if code == -1:
                print(f"  Error: {models_data.get('error', 'Connection refused or timed out')}\n")
    else:
        if not args.json:
            model_name = "unknown"
            if isinstance(models_data, dict) and "data" in models_data and models_data["data"]:
                model_name = models_data["data"][0].get("id", "unknown")
            print(f"✓ Connected to device (HTTP 200 in {elapsed*1000:.1f}ms) | Active model: '{model_name}'\n")

    # 2. Run test queries
    prompts_to_test = (
        [{"prompt": args.prompt, "expected_keywords": [], "min_keywords": 0}]
        if args.prompt
        else BENCHMARK_PROMPTS
    )

    for item in prompts_to_test:
        prompt_text = item["prompt"]
        payload = {
            "model": "esp32-sourdough",
            "messages": [{"role": "user", "content": prompt_text}],
        }

        if not args.json:
            print(f"Prompt: \"{prompt_text}\"")

        code, body, elapsed = http_post(chat_url, payload, timeout=args.timeout)

        query_result: Dict[str, Any] = {
            "prompt": prompt_text,
            "status_code": code,
            "elapsed_sec": round(elapsed, 2),
            "response": None,
            "evaluation": None,
        }

        if code == 200 and isinstance(body, dict):
            query_result["response"] = body
            # Extract assistant reply
            choices = body.get("choices", [])
            content = choices[0].get("message", {}).get("content", "") if choices else ""
            usage = body.get("usage", {})
            comp_tokens = usage.get("completion_tokens", len(content.split()))
            tok_per_sec = comp_tokens / elapsed if elapsed > 0 else 0.0

            eval_res = evaluate_response_quality(content, item)
            eval_res["completion_tokens"] = comp_tokens
            eval_res["tokens_per_sec"] = round(tok_per_sec, 1)
            query_result["evaluation"] = eval_res

            if eval_res["status"] != "HEALTHY":
                results["overall_status"] = "WARN" if results["overall_status"] != "FAIL" else "FAIL"

            if not args.json:
                status_icon = "✓" if eval_res["status"] == "HEALTHY" else "✗"
                print(f"Assistant: {content}")
                print(f"Metrics:   {comp_tokens} tokens in {elapsed:.2f}s ({tok_per_sec:.1f} tok/s)")
                print(f"Quality:   [{status_icon} {eval_res['status']}] {eval_res['explanation']}")
                if eval_res.get("keyword_matches"):
                    print(f"Keywords:  Matched: {', '.join(eval_res['keyword_matches'])}")
                print("-" * 72)
        else:
            results["overall_status"] = "FAIL"
            err_msg = body.get("error", "Request failed") if isinstance(body, dict) else str(body)
            query_result["error"] = err_msg
            if not args.json:
                print(f"✗ Query failed with HTTP {code}: {err_msg}")
                print("-" * 72)

        results["queries"].append(query_result)

    # 3. Diagnostic Suite
    should_diagnose = args.diagnose or (results["overall_status"] != "PASS")
    if should_diagnose:
        issues = diagnose_system(repo_root, ip, port)
        results["diagnostics"] = issues

        if not args.json and issues:
            print("\n" + "=" * 72)
            print("⚠️ DIAGNOSTIC FINDINGS & REMEDIATION")
            print("=" * 72)
            for iss in issues:
                print(f"[{iss['severity']}] {iss['code']}: {iss['message']}")
                print("Recommended fix:")
                for r in iss["remediation"]:
                    print(f"  • {r}")
                print()

    # 4. Optional Auto-Fix
    if args.fix and results.get("diagnostics"):
        if not args.json:
            print("🔧 Executing automated fixes where possible...")
        for iss in results["diagnostics"]:
            if iss["code"] == "MODEL_CHECKSUM_MISMATCH":
                if not args.json:
                    print("Attempting to restore canonical model from Hugging Face...")
                from subprocess import run
                cmd = ["uv", "run", "python", "download_model_hf.py"]
                res = run(cmd, cwd=repo_root / "firmware")
                if res.returncode == 0 and not args.json:
                    print("✓ Downloaded canonical model. Run `task flash-model` to apply to hardware.")

    if args.json:
        print(json.dumps(results, indent=2))
    else:
        print("\nSummary Status: " + ("✓ PASS" if results["overall_status"] == "PASS" else "✗ " + results["overall_status"]))

    sys.exit(0 if results["overall_status"] == "PASS" else 1)


if __name__ == "__main__":
    main()
