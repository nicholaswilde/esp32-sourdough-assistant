#!/usr/bin/env python3
"""
Remote execution script for training s3-sourdough on Google Colab (Free Tier).

Runs inside the Colab VM environment:
1. Validates environment (T4 GPU or CPU free-tier runtime).
2. Installs dependencies (tokenizers, torch, numpy).
3. Unpacks uploaded payload into workspace.
4. Generates dataset and trains tokenizer if needed.
5. Trains PLE micro-LLM model on sourdough Q&A.
6. Stages checkpoints and tokenizer to /content/output/ for download.
"""

import argparse
import os
import shutil
import subprocess
import sys
import tarfile
from pathlib import Path


def log(msg: str):
    print(f"[colab-task] {msg}", flush=True)


def check_environment():
    log("=== Checking Environment ===")
    try:
        import torch
        log(f"PyTorch version: {torch.__version__}")
        if torch.cuda.is_available():
            gpu_name = torch.cuda.get_device_name(0)
            log(f"GPU detected: {gpu_name} (Free Tier T4)")
        else:
            log("No CUDA GPU detected; running on CPU (Free Tier).")
    except ImportError:
        log("PyTorch not imported yet.")


def install_dependencies():
    log("=== Installing Dependencies ===")
    pkgs = ["tokenizers", "numpy"]
    cmd = [sys.executable, "-m", "pip", "install", "-q"] + pkgs
    subprocess.run(cmd, check=True)
    log("Dependencies installed successfully.")


def setup_workspace(base_dir: Path) -> Path:
    log("=== Setting up Workspace ===")
    payload_tar = Path("/content/payload.tar.gz")
    work_dir = base_dir / "s3-sourdough"

    if payload_tar.exists():
        log(f"Extracting uploaded payload from {payload_tar}...")
        work_dir.mkdir(parents=True, exist_ok=True)
        with tarfile.open(payload_tar, "r:gz") as tar:
            tar.extractall(path=work_dir)
        log(f"Extracted payload into {work_dir}")
        return work_dir

    repo_dir = Path("/content/esp32-sandbox")
    if not repo_dir.exists():
        log("Cloning repository from GitHub...")
        subprocess.run(
            ["git", "clone", "https://github.com/nicholaswilde/esp32-sandbox.git", str(repo_dir)],
            check=True,
        )
    target = repo_dir / "projects" / "s3-sourdough"
    if target.exists():
        return target
    return repo_dir


def run_pipeline(work_dir: Path, output_dir: Path, steps: int = 1200, eval_every: int = 100):
    log(f"=== Action: Sourdough Training ({steps} steps) ===")

    # Step 1: Generate raw dataset if not already present
    raw_corpus = work_dir / "data" / "sourdough" / "raw" / "sourdough_corpus.txt"
    if not raw_corpus.exists():
        log("Generating sourdough dataset...")
        subprocess.run(
            [sys.executable, "-m", "research.sourdough.generate", "--samples", "5000"],
            cwd=str(work_dir),
            check=True,
        )

    # Step 2: Ensure asymmetric vocabulary and layout exist
    asym_dir = work_dir / "data" / "sourdough" / "asymmetric"
    train_pt = asym_dir / "train.pt"
    val_pt = asym_dir / "val.pt"
    vocab_json = work_dir / "data" / "sourdough" / "vocab.json"
    layout_json = work_dir / "data" / "sourdough" / "layout.json"
    tok_json = work_dir / "data" / "sourdough" / "tokenizer.json"

    if not vocab_json.exists():
        log("Building curated output vocabulary (vocab.json)...")
        subprocess.run(
            [sys.executable, "-m", "research.sourdough.build_vocab"],
            cwd=str(work_dir),
            check=True,
        )

    if not (layout_json.exists() and tok_json.exists()):
        log("Building layout and training BPE tokenizer (layout.json, tokenizer.json)...")
        subprocess.run(
            [sys.executable, "-m", "research.sourdough.build_layout"],
            cwd=str(work_dir),
            check=True,
        )

    gen_headers = work_dir / "pc_tools" / "generate_vocab_headers.py"
    if gen_headers.exists():
        log("Generating C headers for asymmetric vocabulary...")
        subprocess.run([sys.executable, str(gen_headers)], cwd=str(work_dir), check=True)

    if not (train_pt.exists() and val_pt.exists()):
        log("Preparing asymmetric training tensors (train.pt, val.pt)...")
        subprocess.run(
            [sys.executable, "-m", "research.sourdough.prepare_asymmetric"],
            cwd=str(work_dir),
            check=True,
        )

    # Step 3: Train PLE micro-LLM with asymmetric head
    log(f"Training PLE micro-LLM for {steps} steps with asymmetric vocabulary...")
    train_cmd = [
        sys.executable,
        "-m",
        "research.sourdough.train",
        "--arm",
        "ple",
        "--asymmetric",
        "--steps",
        str(steps),
        "--eval-every",
        str(eval_every),
    ]
    subprocess.run(train_cmd, cwd=str(work_dir), check=True)

    # Step 4: Test inference with sample prompt
    log("Testing inference on sample prompt...")
    sample_cmd = [
        sys.executable,
        "-m",
        "research.sourdough.sample",
        "Why is there liquid on top of my sourdough starter?",
    ]
    try:
        subprocess.run(sample_cmd, cwd=str(work_dir), check=False)
    except Exception as e:
        log(f"Sample test notice: {e}")

    # Step 5: Quantize and export model binary
    export_script = work_dir / "pc_tools" / "export_model.py"
    ckpt_path = work_dir / "runs" / "sourdough" / "ple-sourdough-v1-s0.pt"
    if export_script.exists() and ckpt_path.exists():
        log("Quantizing and exporting INT4 binary artifact (sourdough_q4.bin)...")
        subprocess.run(
            [
                sys.executable,
                str(export_script),
                "--ckpt",
                str(ckpt_path),
                "--tokenizer",
                str(tok_json),
            ],
            cwd=str(work_dir),
            check=True,
        )

    # Step 6: Stage artifacts to output_dir
    runs_dir = work_dir / "runs" / "sourdough"
    if runs_dir.exists():
        for pt_file in runs_dir.glob("*.pt"):
            shutil.copy2(pt_file, output_dir / pt_file.name)
            log(f"Staged checkpoint {output_dir / pt_file.name} ({pt_file.stat().st_size:,} bytes)")

    pc_tools_dir = work_dir / "pc_tools"
    if pc_tools_dir.exists():
        for fname in ["sourdough_q4.bin", "tokenizer.json", "metadata.json", "golden.txt", "golden.npz"]:
            src_f = pc_tools_dir / fname
            if src_f.exists():
                shutil.copy2(src_f, output_dir / fname)
                log(f"Staged {output_dir / fname} ({src_f.stat().st_size:,} bytes)")

    sourdough_data = work_dir / "data" / "sourdough"
    for fname in ["layout.json", "vocab.json", "tokenizer.json"]:
        src_f = sourdough_data / fname
        if src_f.exists() and not (output_dir / fname).exists():
            shutil.copy2(src_f, output_dir / fname)
            log(f"Staged {output_dir / fname}")


def main():
    parser = argparse.ArgumentParser(description="Google Colab Remote Task Runner for s3-sourdough")
    parser.add_argument(
        "--action",
        choices=["train-test", "train", "train-full"],
        default="train",
        help="Training action (default: train)",
    )
    args = parser.parse_args()

    base_dir = Path("/content")
    output_dir = base_dir / "output"
    output_dir.mkdir(parents=True, exist_ok=True)

    check_environment()
    install_dependencies()
    work_dir = setup_workspace(base_dir)

    if args.action == "train-test":
        run_pipeline(work_dir, output_dir, steps=50, eval_every=10)
    elif args.action == "train":
        run_pipeline(work_dir, output_dir, steps=1200, eval_every=100)
    elif args.action == "train-full":
        run_pipeline(work_dir, output_dir, steps=2000, eval_every=100)

    log("=== Task Complete ===")
    log("Artifacts available in /content/output/:")
    for item in output_dir.iterdir():
        log(f"  - {item.name} ({item.stat().st_size:,} bytes)")

    (output_dir / "status.txt").write_text("SUCCESS\n", encoding="utf-8")


if __name__ == "__main__":
    main()
