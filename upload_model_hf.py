#!/usr/bin/env python3
"""Upload trained or quantized ESP32-S3 Sourdough Baker models to Hugging Face Hub.

Uploads the 5 core artifacts:
  - README.md (Model Card with metadata)
  - LICENSE (Apache 2.0 or repository license)
  - metadata.json (Architecture, quantization, and hardware specifications)
  - *.bin (Quantized/packed model weights)
  - tokenizer.json (Vocabulary and tokenizer configuration)
"""

import argparse
import json
import os
import sys
from pathlib import Path
from typing import Dict, List, Optional, Tuple

try:
    from huggingface_hub import HfApi
except ImportError:
    print(
        "Error: huggingface_hub is not installed. Run 'uv add huggingface-hub'.",
        file=sys.stderr,
    )
    sys.exit(1)


def generate_model_card(repo_id: str, bin_filenames: List[str]) -> str:
    """Generate a clean model card README.md with YAML metadata for Hugging Face."""
    primary_bin = bin_filenames[0] if bin_filenames else "sourdough_q4.bin"

    card = f"""---
language:
- en
license: apache-2.0
tags:
- esp32
- esp32-s3
- sourdough
- baking
- edge-ai
- quantized
- int4
- embedded
- ple
pipeline_tag: text-generation
---

# ESP32-S3 Sourdough Bread Baking Assistant

An offline, edge AI language model trained specifically to answer sourdough baking and troubleshooting questions directly on an **ESP32-S3** microcontroller.

Inspired by [slvDev/esp32-ai-barista](https://huggingface.co/slvDev/esp32-ai-barista) and built inside the **[esp32-sandbox](https://github.com/nicholaswilde/esp32-sandbox)** project (`projects/s3-sourdough`).

## Model Details

- **Target Hardware**: ESP32-S3 (e.g., ESP32-S3-DevKitC-1-N16R8)
- **Architecture**: Per-Layer Embeddings (PLE) micro-LLM
- **Flash Memory Required**: ≥ 16MB
- **PSRAM Required**: ≥ 8MB (Octal SPI recommended)
- **Vocabulary**: 2,048 tokens (compact ByteLevel BPE)
- **Quantization**: INT4 grouped quantization (`group_size = 128`)
- **Partition Offset**: `0x110000` (mapped via `esp_partition_mmap`)
- **Training Dataset**: `sourdough_qa.jsonl` (5,000 conversational Q&A pairs covering 111 curated sourdough baking topics with leak-free validation split)
- **Domain Scope**:
  - Starter health (hooch, mold, feeding ratios, acetone smells, sluggish rise, drying/reviving)
  - Bulk fermentation (under/over-proofing signs, poke test, temperature, DDT formula)
  - Hydration & shaping (sticky dough, rice flour bannetons, cold retard, batard stitching)
  - Scoring & baking (steam, ear development, gummy crumb prevention, blisters, temperatures)
  - Baker's math & percentages (100/70/20/2 formulas, preferment %, inclusion math)
  - Guardrails (out-of-domain refusals, toxic food hazards, medical disclaimers)

## Quick Flashing to ESP32-S3

```bash
# 1. Download model binary and tokenizer
hf download {repo_id} {primary_bin} --local-dir .

# 2. Flash to model partition (0x110000)
esptool --baud 921600 --port /dev/ttyACM0 write-flash 0x110000 {primary_bin}
```

## Running Inference

Refer to the [esp32-sandbox repository](https://github.com/nicholaswilde/esp32-sandbox/tree/main/projects/s3-sourdough) for firmware building, flashing, and interactive USB serial querying.
"""
    return card


def generate_default_metadata(bin_name: str) -> dict:
    return {
        "model_name": bin_name,
        "domain": "sourdough_bread_baking",
        "architecture": "TinyLM-PLE",
        "quantization": "int4_group_128",
        "target_hardware": {
            "mcu": "ESP32-S3",
            "recommended_module": "ESP32-S3-DevKitC-1-N16R8",
            "flash_required_mb": 16,
            "psram_required_mb": 8,
            "flash_partition_offset": "0x110000",
        },
        "vocab_size": 2048,
        "seq_len": 128,
        "inference_engine": "llama2.c / ple compatible (esp_partition_mmap)",
    }


def get_default_repo(api: HfApi, repo_name: str = "esp32-s3-sourdough") -> str:
    try:
        user_info = api.whoami()
        username = user_info.get("name")
        if username:
            return f"{username}/{repo_name}"
    except Exception:
        pass
    return f"your-username/{repo_name}"


def collect_artifacts(
    target_path: Path, repo_root: Path
) -> Dict[str, Tuple[Optional[Path], Optional[str]]]:
    artifacts: Dict[str, Tuple[Optional[Path], Optional[str]]] = {}

    if target_path.is_dir():
        base_dir = target_path
        bin_files = sorted(list(base_dir.glob("*.bin")))
    else:
        base_dir = target_path.parent
        bin_files = [target_path] if target_path.suffix == ".bin" else sorted(list(base_dir.glob("*.bin")))

    for b in bin_files:
        artifacts[b.name] = (b, None)

    # Tokenizer
    tok_candidates = [
        base_dir / "tokenizer.json",
        repo_root / "projects" / "s3-sourdough" / "data" / "sourdough" / "vocab-2048" / "tokenizer.json",
        repo_root / "projects" / "s3-sourdough" / "pc_tools" / "tokenizer.json",
    ]
    for cand in tok_candidates:
        if cand.exists():
            artifacts["tokenizer.json"] = (cand, None)
            break

    # Dataset Q&A pairs (sourdough_qa.jsonl)
    qa_candidates = [
        base_dir / "sourdough_qa.jsonl",
        repo_root / "projects" / "s3-sourdough" / "data" / "sourdough" / "raw" / "sourdough_qa.jsonl",
        repo_root / "data" / "sourdough" / "raw" / "sourdough_qa.jsonl",
    ]
    for cand in qa_candidates:
        if cand.exists():
            artifacts["sourdough_qa.jsonl"] = (cand, None)
            break

    # Metadata
    meta_candidate = base_dir / "metadata.json"
    if meta_candidate.exists():
        artifacts["metadata.json"] = (meta_candidate, None)
    else:
        primary_name = bin_files[0].name if bin_files else "sourdough_q4.bin"
        meta_data = generate_default_metadata(primary_name)
        artifacts["metadata.json"] = (None, json.dumps(meta_data, indent=2))

    # License
    license_candidate = base_dir / "LICENSE"
    if not license_candidate.exists():
        license_candidate = repo_root / "LICENSE"

    if license_candidate.exists():
        artifacts["LICENSE"] = (license_candidate, None)

    # README.md
    readme_candidate = base_dir / "README.md"
    if readme_candidate.exists() and readme_candidate != (repo_root / "projects" / "s3-sourdough" / "README.md"):
        artifacts["README.md"] = (readme_candidate, None)
    else:
        bin_names = [b.name for b in bin_files] if bin_files else ["sourdough_q4.bin"]
        card_content = generate_model_card("REPO_ID_PLACEHOLDER", bin_names)
        artifacts["README.md"] = (None, card_content)

    return artifacts


def main():
    parser = argparse.ArgumentParser(
        description="Upload ESP32-S3 Sourdough model artifacts to Hugging Face Hub."
    )
    parser.add_argument(
        "--path",
        "-p",
        type=str,
        default="pc_tools/",
        help="Local path to model binary or directory (default: pc_tools/)",
    )
    parser.add_argument(
        "--repo-id",
        "-r",
        type=str,
        default=None,
        help="Hugging Face repository ID (<username>/<repo_name>). Defaults to <current_user>/esp32-s3-sourdough",
    )
    parser.add_argument(
        "--private",
        action="store_true",
        help="Make repository private if newly created",
    )
    parser.add_argument(
        "--commit-message",
        "-m",
        type=str,
        default=None,
        help="Custom commit message for Hugging Face git history",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Simulate upload without uploading files or creating repositories",
    )

    args = parser.parse_args()

    api = HfApi()

    try:
        user_info = api.whoami()
        username = user_info.get("name")
        print(f"✓ Authenticated as Hugging Face user: {username} ({user_info.get('fullname', '')})")
    except Exception as e:
        print(f"Error: Not authenticated with Hugging Face ({e}). Run 'hf auth login' first.", file=sys.stderr)
        sys.exit(1)

    repo_id = args.repo_id or get_default_repo(api)
    print(f"Target repository: https://huggingface.co/{repo_id}")

    upload_path = Path(args.path).resolve()
    curr = upload_path
    repo_root = curr
    for parent in [curr] + list(curr.parents):
        if (parent / ".git").exists() or (parent / "LICENSE").exists():
            repo_root = parent
            break

    artifacts = collect_artifacts(upload_path, repo_root)

    if "README.md" in artifacts:
        local_path, content = artifacts["README.md"]
        if content and "REPO_ID_PLACEHOLDER" in content:
            artifacts["README.md"] = (local_path, content.replace("REPO_ID_PLACEHOLDER", repo_id))

    print("\n📦 Files prepared for Hugging Face Hub upload:")
    print(f"{'File':<20} | {'Source':<50} | {'Size'}")
    print("-" * 80)
    for dest_name, (local_file, content) in artifacts.items():
        if local_file and local_file.exists():
            size_str = f"{local_file.stat().st_size / 1024:.1f} KB"
            if local_file.stat().st_size > 1024 * 1024:
                size_str = f"{local_file.stat().st_size / (1024*1024):.2f} MB"
            print(f"{dest_name:<20} | {str(local_file):<50} | {size_str}")
        else:
            size_str = f"{len(content.encode('utf-8'))} B" if content else "0 B"
            print(f"{dest_name:<20} | {'<auto-generated>':<50} | {size_str}")

    commit_msg = args.commit_message or f"Upload Sourdough Baker artifacts ({', '.join(artifacts.keys())})"

    if args.dry_run:
        print(f"\n[DRY-RUN] Would create/verify repo: {repo_id} (private={args.private})")
        print(f"[DRY-RUN] Would commit with message: '{commit_msg}'")
        print("[DRY-RUN] No files were uploaded.")
        return

    try:
        api.create_repo(repo_id=repo_id, repo_type="model", private=args.private, exist_ok=True)
        print(f"\n✓ Verified repository: https://huggingface.co/{repo_id}")
    except Exception as e:
        print(f"Warning: could not create or verify repo {repo_id}: {e}", file=sys.stderr)

    print(f"\nUploading {len(artifacts)} files to {repo_id}...")
    for dest_name, (local_file, content) in artifacts.items():
        if local_file and local_file.exists():
            api.upload_file(
                path_or_fileobj=str(local_file),
                path_in_repo=dest_name,
                repo_id=repo_id,
                repo_type="model",
                commit_message=f"Upload {dest_name}",
            )
        elif content:
            api.upload_file(
                path_or_fileobj=content.encode("utf-8"),
                path_in_repo=dest_name,
                repo_id=repo_id,
                repo_type="model",
                commit_message=f"Add {dest_name}",
            )
        print(f"  ✓ Uploaded {dest_name}")

    print(f"\n✨ Done! Model is live at: https://huggingface.co/{repo_id}")


if __name__ == "__main__":
    main()
