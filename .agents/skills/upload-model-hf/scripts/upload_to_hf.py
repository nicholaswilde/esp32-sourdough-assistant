#!/usr/bin/env python3
"""Skill helper script to upload trained or quantized models to Hugging Face Hub.

Can be run from repository root or any project folder.
"""

import argparse
import subprocess
import sys
from pathlib import Path


def main():
    parser = argparse.ArgumentParser(
        description="Skill runner: Upload model binaries to Hugging Face Hub."
    )
    parser.add_argument(
        "--path",
        "-p",
        type=str,
        default=None,
        help="Local path to model binary or directory (defaults to model/tools/sourdough_q4.bin or firmware/models/sourdough_q4.bin)",
    )
    parser.add_argument(
        "--repo-id",
        "-r",
        type=str,
        default=None,
        help="Hugging Face repository ID (<username>/<repo_name>)",
    )
    parser.add_argument(
        "--private",
        action="store_true",
        help="Create private repo if new",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Dry run without actually uploading",
    )

    args = parser.parse_args()

    repo_root = Path(__file__).resolve().parents[4]
    model_project = repo_root / "model"
    uploader = model_project / "upload_model_hf.py"

    if not uploader.exists():
        print(f"Error: Upload script not found at {uploader}", file=sys.stderr)
        sys.exit(1)

    # Determine default path if not provided
    target_path = Path(args.path).resolve() if args.path else None
    if not target_path:
        for candidate in [
            model_project / "tools" / "sourdough_q4.bin",
            repo_root / "firmware" / "models" / "sourdough_q4.bin",
            model_project / "tools",
        ]:
            if candidate.exists():
                target_path = candidate
                break

    cmd = ["uv", "run", "python", str(uploader)]
    if target_path:
        cmd.extend(["--path", str(target_path)])
    if args.repo_id:
        cmd.extend(["--repo-id", args.repo_id])
    if args.private:
        cmd.append("--private")
    if args.dry_run:
        cmd.append("--dry-run")

    print(f"Running: {' '.join(cmd)}")
    result = subprocess.run(cmd, cwd=str(model_project))
    sys.exit(result.returncode)


if __name__ == "__main__":
    main()
