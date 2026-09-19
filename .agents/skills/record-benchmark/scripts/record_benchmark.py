#!/usr/bin/env python3
"""Record on-device benchmark results and compare against baseline and previous runs.

Capabilities:
  - Ingest run results from live device test, runs/latest.json, or custom JSON file.
  - Parse hardware telemetry (layers, dim, vocab size, free SRAM/PSRAM, SIMD).
  - Compute throughput (tok/s), per-token latency (ms), and speedup vs baseline.
  - Discover and compare against all historical runs in the project runs/ directory.
  - Persist run to runs/<name>.json and update runs/latest.json.
  - Output clean terminal comparison tables or JSON summaries.
  - Optionally update the comparison table in the project README.md.

Usage:
  uv run python .agents/skills/record-benchmark/scripts/record_benchmark.py [OPTIONS]
"""

import argparse
import json
import os
import re
import sys
import time
from pathlib import Path
from typing import Dict, Any, List, Optional

REPO_ROOT = Path(__file__).resolve().parents[4]


def get_current_project(repo_root: Path, project_arg: Optional[str] = None) -> str:
    """Determine the active project directory."""
    if project_arg:
        return project_arg

    env_path = repo_root / ".env"
    if env_path.exists():
        for line in env_path.read_text(encoding="utf-8").splitlines():
            line = line.strip()
            if line.startswith("CURRENT_PROJECT="):
                val = line.split("=", 1)[1].strip().strip('"').strip("'")
                if val:
                    return val

    return "s3-sourdough"


def parse_boot_telemetry(boot_log: str) -> Dict[str, Any]:
    """Extract architecture and memory telemetry from bootloader banner."""
    telemetry: Dict[str, Any] = {
        "vocab": None,
        "dim": None,
        "layers": None,
        "heads": None,
        "ffn": None,
        "ple_dim": None,
        "staged_tensors": None,
        "free_sram_kb": None,
        "free_psram_mb": None,
        "simd": False,
        "subvocab": False,
        "dual_core": False,
    }

    if not boot_log:
        return telemetry

    # Model loaded: vocab=6106, dim=160, layers=6, heads=4, ffn=448, ple_dim=128
    m = re.search(
        r"Model loaded:\s*vocab=(\d+),\s*dim=(\d+),\s*layers=(\d+),\s*heads=(\d+),\s*ffn=(\d+),\s*ple_dim=(\d+)",
        boot_log,
    )
    if m:
        telemetry["vocab"] = int(m.group(1))
        telemetry["dim"] = int(m.group(2))
        telemetry["layers"] = int(m.group(3))
        telemetry["heads"] = int(m.group(4))
        telemetry["ffn"] = int(m.group(5))
        telemetry["ple_dim"] = int(m.group(6))

    # Staged 44 core + head tensors to int8 in PSRAM
    m = re.search(r"Staged\s+(\d+)\s+core", boot_log)
    if m:
        telemetry["staged_tensors"] = int(m.group(1))

    # Free SRAM: 306.4 KB | Free PSRAM: 4.41 MB
    m = re.search(r"Free SRAM:\s*([\d.]+)\s*KB\s*\|\s*Free PSRAM:\s*([\d.]+)\s*MB", boot_log)
    if m:
        telemetry["free_sram_kb"] = float(m.group(1))
        telemetry["free_psram_mb"] = float(m.group(2))

    if "PIE 128-bit vector" in boot_log or "SIMD" in boot_log:
        telemetry["simd"] = True

    if "Sub-vocab: enabled" in boot_log:
        telemetry["subvocab"] = True

    if "Dual-core acceleration enabled" in boot_log:
        telemetry["dual_core"] = True

    return telemetry


def compute_metrics(run_data: Dict[str, Any]) -> Dict[str, Any]:
    """Compute aggregate speed and latency statistics for a benchmark run."""
    results = run_data.get("results", [])
    if not results:
        return {
            "total_tokens": 0,
            "total_time_s": 0.0,
            "avg_tok_per_sec": 0.0,
            "avg_ms_per_tok": 0.0,
            "query_count": 0,
        }

    total_tokens = sum(r.get("tokens", 0) for r in results)
    total_time_s = sum(r.get("time_s", 0.0) for r in results)
    query_count = len(results)

    avg_tok_per_sec = (
        (total_tokens / total_time_s) if total_time_s > 0 else 0.0
    )
    avg_ms_per_tok = (1000.0 / avg_tok_per_sec) if avg_tok_per_sec > 0 else 0.0

    return {
        "total_tokens": total_tokens,
        "total_time_s": round(total_time_s, 2),
        "avg_tok_per_sec": round(avg_tok_per_sec, 2),
        "avg_ms_per_tok": round(avg_ms_per_tok, 1),
        "query_count": query_count,
    }


def load_run_file(path: Path) -> Optional[Dict[str, Any]]:
    """Load a run JSON file with metrics and telemetry."""
    if not path.exists():
        return None
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
        data["_path"] = str(path)
        data["_name"] = path.stem
        data["metrics"] = compute_metrics(data)
        data["telemetry"] = parse_boot_telemetry(data.get("boot_log", ""))
        return data
    except Exception as e:
        print(f"Warning: Could not parse {path}: {e}", file=sys.stderr)
        return None


def run_live_test(repo_root: Path) -> Dict[str, Any]:
    """Execute live on-device test using test-device skill script."""
    import subprocess

    test_script = repo_root / ".agents" / "skills" / "test-device" / "scripts" / "test_device.py"
    if not test_script.exists():
        raise FileNotFoundError(f"Test device script not found at {test_script}")

    print("Executing live on-device test via test-device skill...")
    cmd = ["uv", "run", "--with", "pyserial", "python", str(test_script), "--json"]
    proc = subprocess.run(cmd, cwd=str(repo_root), capture_output=True, text=True)
    if proc.returncode != 0:
        raise RuntimeError(f"test_device.py failed (exit {proc.returncode}):\n{proc.stderr}\n{proc.stdout}")

    return json.loads(proc.stdout)


def format_table(runs: List[Dict[str, Any]], current_run_name: str, baseline_name: str) -> str:
    """Format an aligned ASCII and Markdown comparison table."""
    baseline_run = next((r for r in runs if r["_name"] == baseline_name), runs[0] if runs else None)
    base_tps = baseline_run["metrics"]["avg_tok_per_sec"] if baseline_run else 1.0

    headers = [
        "Run Name",
        "Layers / D",
        "Vocab (PLE)",
        "Free PSRAM",
        "Throughput",
        "Latency",
        "vs Baseline",
    ]

    rows = []
    for r in runs:
        m = r["metrics"]
        t = r["telemetry"]
        name = r["_name"]
        if name == current_run_name:
            name_display = f"👉 {name} (Current)"
        elif name == baseline_name:
            name_display = f"⭐ {name} (Base)"
        else:
            name_display = name

        l_str = f"{t['layers']}L / D={t['dim']}" if t["layers"] and t["dim"] else "—"
        v_str = f"{t['vocab']}" if t["vocab"] else "—"
        psram_str = f"{t['free_psram_mb']:.2f} MB" if t["free_psram_mb"] is not None else "—"
        tps_str = f"{m['avg_tok_per_sec']:.1f} tok/s"
        lat_str = f"{m['avg_ms_per_tok']:.1f} ms"

        if base_tps > 0 and m["avg_tok_per_sec"] > 0:
            diff = ((m["avg_tok_per_sec"] - base_tps) / base_tps) * 100.0
            ratio = m["avg_tok_per_sec"] / base_tps
            if abs(diff) < 0.5:
                delta_str = "1.00× (Base)"
            elif diff > 0:
                delta_str = f"{ratio:.2f}× (+{diff:.1f}%)"
            else:
                delta_str = f"{ratio:.2f}× ({diff:.1f}%)"
        else:
            delta_str = "—"

        rows.append([name_display, l_str, v_str, psram_str, tps_str, lat_str, delta_str])

    # Compute column widths
    widths = [len(h) for h in headers]
    for row in rows:
        for i, val in enumerate(row):
            widths[i] = max(widths[i], len(val))

    # Format Markdown table
    header_line = "| " + " | ".join(h.ljust(widths[i]) for i, h in enumerate(headers)) + " |"
    sep_line = "| " + " | ".join("-" * widths[i] for i in range(len(headers))) + " |"
    data_lines = [
        "| " + " | ".join(val.ljust(widths[i]) for i, val in enumerate(row)) + " |"
        for row in rows
    ]

    return "\n".join([header_line, sep_line] + data_lines)


def main():
    parser = argparse.ArgumentParser(
        description="Record on-device LLM benchmark results and compare against historical runs."
    )
    parser.add_argument("--run", action="store_true", help="Execute live test on connected device first")
    parser.add_argument("--input", "-i", type=Path, help="Input benchmark JSON file (defaults to runs/latest.json)")
    parser.add_argument("--name", "-n", type=str, help="Name for this run (default: timestamped run name)")
    parser.add_argument("--project", "-p", type=str, help="Target project (default: read from .env)")
    parser.add_argument("--baseline", "-b", type=str, default="baseline", help="Baseline run name (default: baseline)")
    parser.add_argument("--json", action="store_true", help="Output comparison summary as JSON")
    parser.add_argument("--no-save", action="store_true", help="Do not write/update files in runs/")
    args = parser.parse_args()

    if (REPO_ROOT / "runs").exists() or not (REPO_ROOT / "projects").exists():
        project_dir = REPO_ROOT
        project_name = REPO_ROOT.name
    else:
        project_name = get_current_project(REPO_ROOT, args.project)
        project_dir = REPO_ROOT / "projects" / project_name
    runs_dir = project_dir / "runs"
    runs_dir.mkdir(parents=True, exist_ok=True)

    # 1. Acquire current run data
    if args.run:
        raw_data = run_live_test(REPO_ROOT)
    elif args.input:
        if not args.input.exists():
            sys.exit(f"Error: Specified input file not found: {args.input}")
        raw_data = json.loads(args.input.read_text(encoding="utf-8"))
    else:
        latest_file = runs_dir / "latest.json"
        if not latest_file.exists():
            sys.exit(
                f"Error: No latest.json found in {runs_dir}. Run with --run to perform a live test or specify --input."
            )
        raw_data = json.loads(latest_file.read_text(encoding="utf-8"))

    # Determine run name
    timestamp = time.strftime("%Y%m%d_%H%M%S")
    run_name = args.name or f"run_{timestamp}"

    # 2. Persist to runs directory
    if not args.no_save:
        target_path = runs_dir / f"{run_name}.json"
        with open(target_path, "w", encoding="utf-8") as f:
            json.dump(raw_data, f, indent=2)

        latest_path = runs_dir / "latest.json"
        with open(latest_path, "w", encoding="utf-8") as f:
            json.dump(raw_data, f, indent=2)

        print(f"✓ Recorded run to {target_path} and updated {latest_path}")

    # 3. Load all historical runs for comparison
    all_runs: List[Dict[str, Any]] = []
    seen_names = set()

    # Load target run
    current_run = {
        "_path": str(runs_dir / f"{run_name}.json"),
        "_name": run_name,
        **raw_data,
        "metrics": compute_metrics(raw_data),
        "telemetry": parse_boot_telemetry(raw_data.get("boot_log", "")),
    }

    # Load other JSON files in runs/
    for p in sorted(runs_dir.glob("*.json")):
        if p.stem == "latest" or p.stem == run_name:
            continue
        r = load_run_file(p)
        if r and r["_name"] not in seen_names:
            seen_names.add(r["_name"])
            all_runs.append(r)

    # Ensure baseline is first if it exists
    base_idx = next((i for i, r in enumerate(all_runs) if r["_name"] == args.baseline), None)
    if base_idx is not None:
        base_item = all_runs.pop(base_idx)
        all_runs.insert(0, base_item)

    # Append current run
    all_runs.append(current_run)

    # 4. Output results
    if args.json:
        summary = {
            "project": project_name,
            "recorded_run": run_name,
            "metrics": current_run["metrics"],
            "telemetry": current_run["telemetry"],
            "comparison": [
                {
                    "run": r["_name"],
                    "avg_tok_per_sec": r["metrics"]["avg_tok_per_sec"],
                    "avg_ms_per_tok": r["metrics"]["avg_ms_per_tok"],
                    "layers": r["telemetry"]["layers"],
                    "dim": r["telemetry"]["dim"],
                    "vocab": r["telemetry"]["vocab"],
                    "free_psram_mb": r["telemetry"]["free_psram_mb"],
                }
                for r in all_runs
            ],
        }
        print(json.dumps(summary, indent=2))
        return

    print("\n" + "=" * 80)
    print(f"  📊 On-Device Benchmark Comparison: {project_name}")
    print("=" * 80)
    print(format_table(all_runs, current_run_name=run_name, baseline_name=args.baseline))
    print("=" * 80)

    # Detailed Per-Prompt Breakdown for Current Run
    print(f"\n🔍 Query Breakdown for Current Run [{run_name}]:")
    for i, res in enumerate(current_run.get("results", []), 1):
        prompt = res.get("prompt", "")
        toks = res.get("tokens", 0)
        t_s = res.get("time_s", 0.0)
        tps = res.get("tok_per_sec", 0.0)
        print(f"  {i}. \"{prompt}\"")
        print(f"     ➔ {toks} tokens in {t_s:.2f}s ({tps:.1f} tok/s | {(1000.0/tps if tps>0 else 0):.1f} ms/tok)")

    print()


if __name__ == "__main__":
    main()
