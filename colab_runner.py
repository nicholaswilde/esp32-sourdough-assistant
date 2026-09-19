#!/usr/bin/env python3
"""
Google Colab Task Runner for s3-sourdough (Free Tier).

Automates provisioning, uploading, remote execution, and downloading
of trained model checkpoints and tokenizer artifacts.

Usage:
  task colab-train        # Train PLE micro-LLM (1,200 steps)
  task colab-train-full   # Extended training (2,000 steps)
  task colab-train-test   # Fast smoke test (50 steps)
  task colab-stop         # Release Colab session
"""

import argparse
import os
import shutil
import subprocess
import sys
import tarfile
import tempfile
from pathlib import Path

PROJECT_DIR = Path(__file__).resolve().parent
REPO_ROOT = PROJECT_DIR.parent.parent
SESSION_DEFAULT = "s3-sourdough"


def log(msg: str):
    print(f"[colab-runner] {msg}", flush=True)


def check_colab_cli() -> bool:
    if shutil.which("colab") is None:
        log("Error: 'colab' CLI not found in PATH.")
        log("Install via: uv tool install google-colab-cli")
        return False
    return True


def check_auth() -> bool:
    if not check_colab_cli():
        return False

    try:
        res = subprocess.run(
            ["colab", "sessions"],
            capture_output=True,
            text=True,
            stdin=subprocess.DEVNULL,
            timeout=5,
        )
        if res.returncode == 0:
            log("Authentication verified successfully!")
            return True
    except (subprocess.TimeoutExpired, Exception):
        pass

    log("Authentication required for Google Colab CLI.")
    log("Please run this one-time authorization command in your interactive terminal:")
    log("    colab sessions")
    return False


def start_session(session_name: str, force_cpu: bool = False) -> bool:
    """Start a free-tier Colab VM session (attempts T4 GPU, falls back to CPU)."""
    if not force_cpu:
        log(f"Attempting to provision Free-Tier T4 GPU session: '{session_name}'...")
        res = subprocess.run(["colab", "new", "-s", session_name, "--gpu", "T4"], capture_output=True, text=True)
        if res.returncode == 0:
            log(f"Successfully provisioned T4 GPU session '{session_name}'.")
            return True
        log(f"T4 GPU allocation not available or quota reached: {res.stderr.strip()}")
        log("Falling back to Free-Tier standard CPU runtime...")

    res = subprocess.run(["colab", "new", "-s", session_name], capture_output=True, text=True)
    if res.returncode == 0:
        log(f"Successfully provisioned Free-Tier CPU session '{session_name}'.")
        return True
    log(f"Failed to start Colab session: {res.stderr.strip()}")
    return False


def stop_session(session_name: str):
    """Stop the Colab session to release free-tier compute resources."""
    log(f"Stopping session '{session_name}'...")
    subprocess.run(["colab", "stop", "-s", session_name], check=False)


def create_payload_tar(tar_path: Path):
    """Create lightweight payload tarball excluding large binaries and caches."""
    log(f"Creating project payload at {tar_path}...")
    exclude_dirs = {".venv", "__pycache__", ".git", ".pio", "runs"}
    exclude_exts = {".o", ".a"}

    def filter_tar(tarinfo):
        path_parts = Path(tarinfo.name).parts
        if any(part in exclude_dirs for part in path_parts):
            return None
        if Path(tarinfo.name).suffix in exclude_exts:
            return None
        if Path(tarinfo.name).suffix == ".pt" and "runs" in path_parts:
            return None
        if "pc_tools" in path_parts and Path(tarinfo.name).suffix == ".bin":
            return None
        return tarinfo

    with tarfile.open(tar_path, "w:gz") as tar:
        for item in ["research", "data", "pc_tools", "src", "include", "pyproject.toml", "colab_remote_task.py"]:
            src = PROJECT_DIR / item
            if src.exists():
                tar.add(src, arcname=item, filter=filter_tar)


def download_file(session_name: str, remote_path: str, local_path: Path | str, check: bool = True) -> bool:
    """Download artifact from Colab with token auto-refresh and retry."""
    cmd = ["colab", "download", "-s", session_name, remote_path, str(local_path)]
    res = subprocess.run(cmd, capture_output=True, text=True)
    if res.returncode != 0:
        # Long running actions expire the proxy token; force session refresh and retry once
        try:
            subprocess.run(["colab", "sessions"], capture_output=True, text=True, timeout=10)
        except Exception:
            pass
        res = subprocess.run(cmd, capture_output=True, text=True)

    if res.returncode != 0:
        err = res.stderr.strip() or res.stdout.strip()
        if check:
            log(f"Failed to download {remote_path}: {err}")
        return False
    return True


def execute_build(
    session_name: str,
    action: str,
    keep_session: bool,
    force_cpu: bool,
    timeout: int | None = None,
):
    if not check_auth():
        sys.exit(1)

    if timeout is None:
        if action == "train-full":
            timeout = 7200   # 2 hours
        elif action == "train":
            timeout = 3600   # 1 hour
        else:
            timeout = 1800   # 30 mins

    # Auto-heal google-colab-cli KernelClient & token refresh patches if needed
    patch_script = REPO_ROOT / "projects" / "s3-tiny-stories" / "patch_colab_cli.py"
    if patch_script.exists():
        try:
            import importlib.util
            spec = importlib.util.spec_from_file_location("patch_colab_cli", str(patch_script))
            mod = importlib.util.module_from_spec(spec)
            spec.loader.exec_module(mod)
            mod.main()
        except Exception as e:
            log(f"Notice: patch check skipped: {e}")

    with tempfile.TemporaryDirectory() as tmpdir:
        tar_path = Path(tmpdir) / "payload.tar.gz"
        create_payload_tar(tar_path)

        # Check if session is already running
        status_res = subprocess.run(["colab", "status", "-s", session_name], capture_output=True, text=True)
        session_exists = status_res.returncode == 0 and "not found" not in status_res.stdout.lower()

        if not session_exists:
            if not start_session(session_name, force_cpu=force_cpu):
                sys.exit(1)
        else:
            log(f"Using existing session '{session_name}'.")

        try:
            # Upload payload and remote runner
            log("Uploading payload to Colab VM...")
            subprocess.run(["colab", "upload", "-s", session_name, str(tar_path), "/content/payload.tar.gz"], check=True)
            subprocess.run(["colab", "upload", "-s", session_name, str(PROJECT_DIR / "colab_remote_task.py"), "/content/colab_remote_task.py"], check=True)

            # Execute remote task with streaming output
            log(f"Executing remote action: {action} (timeout: {timeout}s)...")
            status_file = "/content/output/status.txt"
            exec_code = (
                "import os, subprocess, sys\n"
                f"if os.path.exists('{status_file}'):\n"
                f"    os.remove('{status_file}')\n"
                f"p = subprocess.Popen([sys.executable, '-u', '/content/colab_remote_task.py', '--action', '{action}'], "
                "stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True, bufsize=1)\n"
                "for line in p.stdout:\n"
                "    sys.stdout.write(line)\n"
                "    sys.stdout.flush()\n"
                "p.wait()\n"
                "if p.returncode == 0:\n"
                f"    with open('{status_file}', 'w') as f:\n"
                "        f.write('SUCCESS\\n')\n"
                "else:\n"
                f"    raise RuntimeError(f'Remote action {action} failed with exit code {{p.returncode}}')\n"
            )
            proc = subprocess.Popen(
                ["colab", "exec", "-s", session_name, "--timeout", str(timeout)],
                stdin=subprocess.PIPE,
                text=True,
            )
            proc.communicate(input=exec_code)
            if proc.returncode != 0:
                log(f"Remote execution failed with exit code {proc.returncode}")
                sys.exit(proc.returncode)

            # Verify remote success status before downloading artifacts
            status_local = Path(tmpdir) / "status.txt"
            download_file(session_name, status_file, status_local, check=False)
            if not status_local.exists() or "SUCCESS" not in status_local.read_text():
                log(f"Remote action '{action}' failed on Colab VM (missing success confirmation).")
                sys.exit(1)

            # Download staged artifacts back to local repository
            log("Downloading artifacts from Colab VM...")
            runs_dir = PROJECT_DIR / "runs" / "sourdough"
            runs_dir.mkdir(parents=True, exist_ok=True)

            ckpt_name = "ple-sourdough-v1-s0.pt"
            download_file(session_name, f"/content/output/{ckpt_name}", runs_dir / ckpt_name, check=False)

            pc_tools_dir = PROJECT_DIR / "pc_tools"
            pc_tools_dir.mkdir(parents=True, exist_ok=True)
            for fname in ["sourdough_q4.bin", "tokenizer.json", "metadata.json", "golden.txt", "golden.npz", "layout.json", "vocab.json"]:
                download_file(session_name, f"/content/output/{fname}", pc_tools_dir / fname, check=False)

            data_sourdough = PROJECT_DIR / "data" / "sourdough"
            data_sourdough.mkdir(parents=True, exist_ok=True)
            for fname in ["tokenizer.json", "layout.json", "vocab.json"]:
                if (pc_tools_dir / fname).exists():
                    shutil.copy2(pc_tools_dir / fname, data_sourdough / fname)

            gen_headers = pc_tools_dir / "generate_vocab_headers.py"
            if gen_headers.exists() and (data_sourdough / "vocab.json").exists() and (data_sourdough / "layout.json").exists():
                subprocess.run([sys.executable, str(gen_headers)], check=False)

            gen_tok = pc_tools_dir / "generate_tokenizer_asset.py"
            if gen_tok.exists() and (data_sourdough / "tokenizer.json").exists():
                subprocess.run([sys.executable, str(gen_tok)], check=False)

            log("Training & INT4 quantization finished successfully! Artifacts saved in pc_tools/ and runs/.")

        finally:
            if not keep_session:
                stop_session(session_name)
            else:
                log(f"Session '{session_name}' kept alive. Remember to run 'colab stop -s {session_name}' when done.")


def main():
    parser = argparse.ArgumentParser(description="Google Colab Runner for s3-sourdough")
    subparsers = parser.add_subparsers(dest="command", required=True)

    # Auth check
    subparsers.add_parser("check-auth", help="Verify colab CLI authentication")

    # Start session
    start_p = subparsers.add_parser("start-session", help="Start a Colab VM session")
    start_p.add_argument("-s", "--session", default=SESSION_DEFAULT, help="Session name")
    start_p.add_argument("--cpu", action="store_true", help="Force CPU instead of T4 GPU")

    # Stop session
    stop_p = subparsers.add_parser("stop-session", help="Stop a Colab VM session")
    stop_p.add_argument("-s", "--session", default=SESSION_DEFAULT, help="Session name")

    # Build / Train
    build_p = subparsers.add_parser("build", help="Run training task on Colab")
    build_p.add_argument(
        "--action",
        choices=["train-test", "train", "train-full"],
        default="train",
        help="Action to perform on Colab (default: train)",
    )
    build_p.add_argument("-s", "--session", default=SESSION_DEFAULT, help="Session name")
    build_p.add_argument("--keep", action="store_true", help="Keep VM session running after task finishes")
    build_p.add_argument("--cpu", action="store_true", help="Force CPU instead of T4 GPU")
    build_p.add_argument("--timeout", type=int, default=None, help="Execution timeout in seconds")

    args = parser.parse_args()

    if args.command == "check-auth":
        check_auth()
    elif args.command == "start-session":
        start_session(args.session, force_cpu=args.cpu)
    elif args.command == "stop-session":
        stop_session(args.session)
    elif args.command == "build":
        execute_build(args.session, args.action, args.keep, args.cpu, args.timeout)


if __name__ == "__main__":
    main()
