#!/usr/bin/env python3
"""Hardware Serial Monitor & Interactive REPL Tester for ESP32 LLM / Firmware.

Capabilities:
  - Auto-detect connected ESP32-S3 serial ports (/dev/ttyACM*, /dev/ttyUSB*).
  - Hardware reset via USB-UART RTS/DTR line toggling.
  - Capture and parse bootloader banners, partition mounts, and memory stats.
  - Send batch prompts or run an interactive REPL session.
  - Measure inference latency, token counts, and generation throughput (tok/s).
  - Export structured benchmark results as JSON.

Usage:
  uv run --with pyserial python .agents/skills/test-device/scripts/test_device.py [OPTIONS]
"""

import argparse
import glob
import json
import os
import re
import sys
import time
from typing import List, Optional, Dict, Any

try:
    import serial
except ImportError:
    print("Error: pyserial is required. Run via 'uv run --with pyserial python ...'", file=sys.stderr)
    sys.exit(1)


def find_serial_port(preferred: Optional[str] = None) -> str:
    """Find serial port or return preferred."""
    if preferred and os.path.exists(preferred):
        return preferred

    candidates = sorted(glob.glob("/dev/ttyACM*") + glob.glob("/dev/ttyUSB*"))
    if not candidates:
        raise RuntimeError("No serial device found under /dev/ttyACM* or /dev/ttyUSB*")
    return candidates[0]


def reset_device(ser: serial.Serial, delay_s: float = 0.1):
    """Pulse RTS to trigger hardware reset on ESP32."""
    ser.setDTR(False)
    ser.setRTS(True)
    time.sleep(delay_s)
    ser.setRTS(False)


def capture_boot_output(ser: serial.Serial, timeout_s: float = 2.5) -> str:
    """Read serial output until prompt indicator, completion of autonomous run, or timeout."""
    start_time = time.time()
    boot_log = ""
    max_wait = timeout_s
    while time.time() - start_time < max_wait:
        n = ser.in_waiting
        if n:
            chunk = ser.read(n).decode("utf-8", errors="replace")
            boot_log += chunk
            if "User: " in boot_log or "READY>" in boot_log:
                break
            # If LLM model initialization or autonomous generation begins, extend timeout to allow completion
            if any(k in boot_log for k in (">>>", "=== ESP32-S3", "TinyLM", "Vin=")) and max_wait == timeout_s and timeout_s < 60.0:
                max_wait = 60.0
            # Completion marker for autonomous generation
            if "profile ms/token:" in boot_log or ("throughput:" in boot_log and "\n" in boot_log.split("throughput:")[1]):
                break
        time.sleep(0.05)
    return boot_log


def send_query(
    ser: serial.Serial,
    prompt: str,
    prompt_marker: str = "User: ",
    timeout_s: float = 15.0
) -> Dict[str, Any]:
    """Send a prompt to the device and capture the streamed completion."""
    # Flush incoming bytes
    ser.read(ser.in_waiting or 0)

    # Write prompt
    ser.write((prompt + "\n").encode("utf-8"))
    ser.flush()

    start_time = time.time()
    raw_response = ""
    first_char_time = None

    while time.time() - start_time < timeout_s:
        n = ser.in_waiting
        if n:
            chunk = ser.read(n).decode("utf-8", errors="replace")
            if first_char_time is None and chunk.strip():
                first_char_time = time.time()
            raw_response += chunk

            # Check if prompt marker returned (indicating end of turn)
            if prompt_marker in raw_response[len(prompt):]:
                break
        time.sleep(0.04)

    total_time = time.time() - start_time

    # Clean echoed prompt if present
    cleaned = raw_response
    if cleaned.startswith(prompt):
        cleaned = cleaned[len(prompt):].lstrip("\r\n")

    # Extract timing line if present: e.g. [40 tokens in 3.70 s, 10.8 tok/s] or [15 words in 1.42 s, 10.6 words/s]
    timing_match = re.search(
        r"\[(\d+)\s+(?:tokens?|words?|pieces?)\s+in\s+([\d\.]+)\s+s(?:,\s+([\d\.]+)\s+(?:tok|words?|pieces?)/s)?\]",
        cleaned,
    )
    tokens_count = None
    gen_time = None
    tok_per_sec = None

    if timing_match:
        tokens_count = int(timing_match.group(1))
        gen_time = float(timing_match.group(2))
        if timing_match.group(3):
            tok_per_sec = float(timing_match.group(3))
        elif gen_time > 0:
            tok_per_sec = tokens_count / gen_time

    # Extract answer text
    answer_text = cleaned
    if prompt_marker in answer_text:
        answer_text = answer_text[:answer_text.rfind(prompt_marker)].strip()
    if timing_match:
        answer_text = answer_text[:timing_match.start()].strip()
    if answer_text.startswith("Assistant:"):
        answer_text = answer_text[len("Assistant:"):].strip()

    return {
        "prompt": prompt,
        "answer": answer_text,
        "tokens": tokens_count,
        "time_s": gen_time or round(total_time, 2),
        "tok_per_sec": tok_per_sec,
        "raw": raw_response.strip(),
    }


def main():
    parser = argparse.ArgumentParser(description="Monitor and interactively test connected ESP32 LLM device.")
    parser.add_argument("--port", "-p", type=str, default=None, help="Serial port (default: auto-detect)")
    parser.add_argument("--baud", "-b", type=int, default=115200, help="Baud rate (default: 115200)")
    parser.add_argument("--no-reset", action="store_true", help="Do not trigger hardware reset on start")
    parser.add_argument("--boot-timeout", type=float, default=2.5, help="Seconds to capture boot log (default: 2.5)")
    parser.add_argument("--timeout", type=float, default=15.0, help="Timeout per query in seconds (default: 15.0)")
    parser.add_argument("--query", "-q", action="append", help="Prompt question to send (can repeat)")
    parser.add_argument("--interactive", "-i", action="store_true", help="Launch interactive terminal REPL")
    parser.add_argument("--json", action="store_true", help="Output results as JSON")
    args = parser.parse_args()

    port = find_serial_port(args.port)
    if not args.json:
        print(f"Connecting to ESP32 on {port} at {args.baud} baud...")

    try:
        ser = serial.Serial(port, args.baud, timeout=1.0, exclusive=True)
    except TypeError:
        ser = serial.Serial(port, args.baud, timeout=1.0)
    except Exception as e:
        print(f"Error opening {port}: {e}", file=sys.stderr)
        sys.exit(1)

    boot_output = ""
    if not args.no_reset:
        if not args.json:
            print("Triggering hardware reset via RTS/DTR...")
        reset_device(ser)
        boot_output = capture_boot_output(ser, args.boot_timeout)
        if not args.json and boot_output:
            print("\n--- Boot Banner ---")
            print(boot_output.strip())
            print("-------------------\n")

    results = []

    # Check if the device performed an autonomous generation on boot
    tiny_timing = re.search(r"throughput:\s+([\d\.]+)\s+tok/s\s+\(([\d\.]+)\s+ms/token\)", boot_output)
    tiny_total = re.search(r"---\s+(\d+)\s+tokens in\s+([\d\.]+)\s+s\s+---", boot_output)

    if tiny_timing or ">>>" in boot_output:
        body = boot_output.split(">>>", 1)[1] if ">>>" in boot_output else boot_output
        if tiny_total:
            body = re.split(r"---\s+\d+\s+tokens in", body)[0]
        story = " ".join(l.strip() for l in body.splitlines() if l.strip())

        tokens_count = int(tiny_total.group(1)) if tiny_total else None
        gen_time = float(tiny_total.group(2)) if tiny_total else None
        tok_per_sec = float(tiny_timing.group(1)) if tiny_timing else None

        profile_match = re.search(
            r"profile ms/token:\s+input\s+([\d\.]+)\s+\|\s+attn\s+([\d\.]+)\s+\|\s+ffn\s+([\d\.]+)\s+\|\s+ple\s+([\d\.]+)\s+\|\s+head\s+([\d\.]+)",
            boot_output,
        )
        profile_data = None
        if profile_match:
            profile_data = {
                "input_ms": float(profile_match.group(1)),
                "attn_ms": float(profile_match.group(2)),
                "ffn_ms": float(profile_match.group(3)),
                "ple_ms": float(profile_match.group(4)),
                "head_ms": float(profile_match.group(5)),
            }

        res = {
            "prompt": "<autonomous generation on boot>",
            "answer": story,
            "tokens": tokens_count,
            "time_s": gen_time,
            "tok_per_sec": tok_per_sec,
            "profile": profile_data,
            "raw": boot_output.strip(),
        }
        results.append(res)

        if not args.json:
            print("\nAutonomous Generation Result:")
            print(f"Generated text: {story}\n")
            if tokens_count and tok_per_sec:
                print(f"[{tokens_count} tokens in {gen_time:.2f}s, {tok_per_sec:.2f} tok/s]")
            if profile_data:
                print(f"Profile: input {profile_data['input_ms']}ms | attn {profile_data['attn_ms']}ms | ffn {profile_data['ffn_ms']}ms | ple {profile_data['ple_ms']}ms | head {profile_data['head_ms']}ms\n")

    # Queries: run if explicitly passed, or if not interactive and no autonomous results were parsed
    queries = args.query
    if not queries and not args.interactive and not results:
        queries = [
            "Why is there liquid on top of my sourdough starter?",
            "How do I feed my sourdough starter?",
            "Why is my bread gummy?",
        ]

    if queries:
        for q in queries:
            if not args.json:
                print(f"User: {q}")
            res = send_query(ser, q, timeout_s=args.timeout)
            results.append(res)
            if not args.json:
                print(f"Assistant: {res['answer']}")
                if res['tokens'] is not None and res['tok_per_sec'] is not None:
                    print(f"[{res['tokens']} tokens in {res['time_s']:.2f}s, {res['tok_per_sec']:.1f} tok/s]\n")
                else:
                    print(f"[Done in {res['time_s']:.2f}s]\n")

    if args.interactive:
        print("Starting interactive REPL session (type 'exit' or Ctrl+C to quit):\n")
        try:
            while True:
                user_input = input("User: ").strip()
                if not user_input or user_input.lower() in ("exit", "quit"):
                    break
                res = send_query(ser, user_input, timeout_s=args.timeout)
                print(f"Assistant: {res['answer']}")
                if res['tokens'] is not None and res['tok_per_sec'] is not None:
                    print(f"[{res['tokens']} tokens in {res['time_s']:.2f}s, {res['tok_per_sec']:.1f} tok/s]\n")
                else:
                    print()
        except (KeyboardInterrupt, EOFError):
            print("\nExiting interactive session.")

    ser.close()

    if args.json:
        output_data = {
            "port": port,
            "baud": args.baud,
            "boot_log": boot_output.strip(),
            "results": results
        }
        print(json.dumps(output_data, indent=2))


if __name__ == "__main__":
    main()
