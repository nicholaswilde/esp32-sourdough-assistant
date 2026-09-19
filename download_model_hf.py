#!/usr/bin/env python3
"""Download ESP32-S3 Sourdough Baker Assistant model bundle from Hugging Face Hub.

Downloads model artifacts:
  - sourdough_q4.bin (Quantized INT4 weights)
  - tokenizer.json (Tokenizer configuration and vocabulary)
  - metadata.json (Architecture metadata)
  - README.md (Model Card)

Optionally regenerates C headers in src/generated/ (vocab.h, tokenizer_asset.h)
so firmware is immediately ready to compile and flash.
"""

import argparse
import os
import subprocess
import sys
from pathlib import Path
from typing import List, Optional

try:
    from huggingface_hub import HfApi, hf_hub_download, list_repo_files
except ImportError:
    print(
        "Error: huggingface_hub is not installed. Run 'uv add huggingface-hub'.",
        file=sys.stderr,
    )
    sys.exit(1)

PROJECT_ROOT = Path(__file__).resolve().parent
DEFAULT_REPO_NAME = "esp32-s3-sourdough"
CORE_FILES = ["sourdough_q4.bin", "tokenizer.json", "metadata.json", "README.md"]


def get_default_repo(api: HfApi) -> str:
    """Infer default repository ID from current Hugging Face credentials or fallback."""
    try:
        user_info = api.whoami()
        username = user_info.get("name")
        if username:
            return f"{username}/{DEFAULT_REPO_NAME}"
    except Exception:
        pass
    return f"nicholascwilde/{DEFAULT_REPO_NAME}"


def download_artifacts(
    repo_id: str,
    out_dir: Path,
    filenames: Optional[List[str]] = None,
    revision: str = "main",
    token: Optional[str] = None,
) -> List[Path]:
    """Download specified or all model artifacts from Hugging Face repository."""
    out_dir.mkdir(parents=True, exist_ok=True)

    print(f"Connecting to Hugging Face Hub: https://huggingface.co/{repo_id}")
    try:
        remote_files = list_repo_files(repo_id=repo_id, revision=revision, token=token)
    except Exception as e:
        print(f"Error accessing repository '{repo_id}': {e}", file=sys.stderr)
        sys.exit(1)

    target_files = []
    if filenames:
        for f in filenames:
            if f in remote_files:
                target_files.append(f)
            else:
                print(f"Warning: File '{f}' not found in repository {repo_id}.", file=sys.stderr)
    else:
        # Match core files first, or any .bin files
        for cf in CORE_FILES:
            if cf in remote_files:
                target_files.append(cf)
        for rf in remote_files:
            if rf.endswith(".bin") and rf not in target_files:
                target_files.append(rf)

    if not target_files:
        print(f"Error: No matching model artifacts found in {repo_id}.", file=sys.stderr)
        sys.exit(1)

    print(f"Downloading {len(target_files)} files to {out_dir}...\n")
    downloaded_paths = []

    for fname in target_files:
        print(f"  Downloading '{fname}'...", end=" ", flush=True)
        try:
            cached_path = hf_hub_download(
                repo_id=repo_id,
                filename=fname,
                revision=revision,
                token=token,
                local_dir=str(out_dir),
                local_dir_use_symlinks=False,
            )
            dest = Path(cached_path)
            downloaded_paths.append(dest)
            size_kb = dest.stat().st_size / 1024
            if size_kb > 1024:
                print(f"✓ ({size_kb / 1024:.2f} MB)")
            else:
                print(f"✓ ({size_kb:.1f} KB)")
        except Exception as e:
            print(f"FAILED ({e})")
            raise

    return downloaded_paths


def regenerate_c_headers():
    """Regenerate vocab.h and tokenizer_asset.h from downloaded tokenizer.json."""
    gen_vocab = PROJECT_ROOT / "pc_tools" / "generate_vocab.py"
    gen_asset = PROJECT_ROOT / "pc_tools" / "generate_tokenizer_asset.py"
    gen_subvocab = PROJECT_ROOT / "pc_tools" / "generate_subvocab.py"

    if gen_vocab.exists():
        print("\nUpdating C decoding header (src/generated/vocab.h)...")
        subprocess.run([sys.executable, str(gen_vocab)], check=True)
    if gen_asset.exists():
        print("Updating C encoding header (src/generated/tokenizer_asset.h)...")
        subprocess.run([sys.executable, str(gen_asset)], check=True)
    if gen_subvocab.exists():
        print("Updating sub-vocab cluster header (src/generated/sourdough_subvocab.h)...")
        subprocess.run([sys.executable, str(gen_subvocab)], check=True)


def main():
    parser = argparse.ArgumentParser(
        description="Download Sourdough Baker Assistant model from Hugging Face Hub."
    )
    parser.add_argument(
        "--repo-id",
        "-r",
        type=str,
        default=None,
        help="Hugging Face repository ID (<username>/<repo>). Defaults to authenticated user or nicholaswilde/esp32-s3-sourdough",
    )
    parser.add_argument(
        "--out-dir",
        "-o",
        type=Path,
        default=PROJECT_ROOT / "pc_tools",
        help="Directory to save downloaded files (default: pc_tools/)",
    )
    parser.add_argument(
        "--filename",
        "-f",
        type=str,
        default=None,
        help="Download a single specific file instead of full bundle",
    )
    parser.add_argument(
        "--revision",
        type=str,
        default="main",
        help="Repository revision/branch/tag (default: main)",
    )
    parser.add_argument(
        "--generate-headers",
        action="store_true",
        default=True,
        help="Automatically regenerate C headers in src/generated/ (default: True)",
    )
    parser.add_argument(
        "--no-generate-headers",
        action="store_false",
        dest="generate_headers",
        help="Skip C header regeneration",
    )
    parser.add_argument(
        "--token",
        type=str,
        default=os.environ.get("HF_TOKEN"),
        help="Hugging Face API token (optional, or set HF_TOKEN env var)",
    )

    args = parser.parse_args()

    api = HfApi(token=args.token)
    repo_id = args.repo_id or get_default_repo(api)

    filenames = [args.filename] if args.filename else None
    downloaded = download_artifacts(
        repo_id=repo_id,
        out_dir=args.out_dir,
        filenames=filenames,
        revision=args.revision,
        token=args.token,
    )

    print(f"\n✓ Successfully downloaded {len(downloaded)} artifacts to {args.out_dir}")

    # Regenerate C headers if tokenizer.json was downloaded and flag enabled
    if args.generate_headers and any(p.name == "tokenizer.json" for p in downloaded):
        regenerate_c_headers()
        print("\n✓ C firmware headers updated. Ready to flash with 'task flash-model && task flash'")


if __name__ == "__main__":
    main()
