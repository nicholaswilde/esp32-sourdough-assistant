#!/usr/bin/env python3
"""Export trained Sourdough PLE model to INT4 packed binary format for ESP32-S3.

Outputs:
  - pc_tools/sourdough_q4.bin (Packed INT4 weights + FP16 scales with PLE header)
  - pc_tools/tokenizer.json (BPE tokenizer file)
  - pc_tools/metadata.json (Model card metadata)
  - pc_tools/golden.txt (Golden prompt logits for C++ unit test verification)
  - pc_tools/golden.npz (Numpy reference logits)
"""

import argparse
import hashlib
import json
import os
import shutil
import struct
import sys
from pathlib import Path

import numpy as np
import torch
from tokenizers import Tokenizer

# Add parent directory to sys.path to import research.model
PROJECT_DIR = Path(__file__).resolve().parents[1]
if str(PROJECT_DIR) not in sys.path:
    sys.path.insert(0, str(PROJECT_DIR))

from research.model import Config, TinyLM

MAGIC = 0x00454C50  # "PLE\0"
FORMAT_VERSION = 1
HEADER_BYTES = 56
FLAG_TIED_HEAD = 1 << 0
GROUP_DEFAULT = 128


def quant_pack(w: torch.Tensor, group: int = GROUP_DEFAULT):
    """Group-wise symmetric int4, ragged (no padding) with fp16 scales.

    Returns (packed_uint8, scales_fp16, dequantized_fp32).
    """
    w = w.float()
    out_shape = w.shape
    x = w.reshape(-1, out_shape[-1])
    rows, cols = x.shape
    n_groups = (cols + group - 1) // group
    q = torch.zeros(rows, cols)
    dq = torch.zeros(rows, cols)
    scales = torch.zeros(rows, n_groups)

    for gi in range(n_groups):
        a, b = gi * group, min((gi + 1) * group, cols)
        seg = x[:, a:b]
        sc = (seg.abs().amax(dim=1, keepdim=True) / 7.0).clamp_min(1e-8)
        sc = sc.half().float()  # Round scale to IEEE fp16
        scales[:, gi] = sc.squeeze(1)
        qi = torch.clamp(torch.round(seg / sc), -7, 7)
        q[:, a:b] = qi
        dq[:, a:b] = qi * sc
    dq = dq.reshape(out_shape)

    codes = (q.to(torch.int16) + 8).to(torch.uint8).numpy()
    row_bytes = (cols + 1) // 2
    packed = np.zeros((rows, row_bytes), dtype=np.uint8)
    lo = codes[:, 0::2]
    hi = codes[:, 1::2]
    packed[:, : lo.shape[1]] = lo
    packed[:, : hi.shape[1]] |= (hi << 4)
    scales16 = scales.numpy().astype(np.float16)
    return packed.reshape(-1), scales16.reshape(-1), dq


def main():
    parser = argparse.ArgumentParser(description="Export Sourdough PLE checkpoint to INT4 binary.")
    parser.add_argument(
        "--ckpt",
        type=Path,
        default=PROJECT_DIR / "runs" / "sourdough" / "ple-sourdough-v1-s0.pt",
        help="Path to trained checkpoint (.pt)",
    )
    parser.add_argument(
        "--tokenizer",
        type=Path,
        default=PROJECT_DIR / "data" / "sourdough" / "tokenizer.json" if (PROJECT_DIR / "data" / "sourdough" / "tokenizer.json").exists() else PROJECT_DIR / "data" / "sourdough" / "vocab-2048" / "tokenizer.json",
        help="Path to tokenizer.json",
    )
    parser.add_argument(
        "--out-dir",
        type=Path,
        default=PROJECT_DIR / "pc_tools",
        help="Destination directory for exported artifacts (default: pc_tools/)",
    )
    parser.add_argument(
        "--out-name",
        type=str,
        default="sourdough_q4.bin",
        help="Output binary filename (default: sourdough_q4.bin)",
    )
    parser.add_argument(
        "--group",
        type=int,
        default=GROUP_DEFAULT,
        help=f"Quantization group size (default: {GROUP_DEFAULT})",
    )
    args = parser.parse_args()

    if not args.ckpt.exists():
        sys.exit(f"Error: checkpoint {args.ckpt} not found. Run training first.")
    if not args.tokenizer.exists():
        sys.exit(f"Error: tokenizer {args.tokenizer} not found. Run 'task layout' or 'task prepare' first.")

    args.out_dir.mkdir(parents=True, exist_ok=True)

    print(f"Loading checkpoint: {args.ckpt.name}")
    ck = torch.load(args.ckpt, map_location="cpu", weights_only=False)
    cfg = Config(**ck["cfg"])

    if cfg.arm != "ple":
        sys.exit(f"Error: checkpoint arm={cfg.arm}, expected 'ple'")

    out_vocab = cfg.resolved_out_vocab_size
    print(f"input_vocab={cfg.vocab_size} | output_vocab={out_vocab} (active classes)")

    model = TinyLM(cfg)
    model.load_state_dict(ck["state"])
    model.eval()

    sd = model.state_dict()
    plan = []

    def add_tensor(name: str, quant: bool):
        plan.append((name, sd[name], quant))

    # Strict tensor order matching C runtime
    add_tensor("tok_emb.weight", True)
    add_tensor("ple_model_proj.weight", True)
    add_tensor("ple_proj_norm.weight", False)
    add_tensor("ple_table.weight", True)

    for i in range(cfg.n_layers):
        p = f"blocks.{i}."
        add_tensor(p + "attn_norm.weight", False)
        add_tensor(p + "attn.qkv.weight", True)
        add_tensor(p + "attn.proj.weight", True)
        add_tensor(p + "ffn_norm.weight", False)
        add_tensor(p + "ffn.gate.weight", True)
        add_tensor(p + "ffn.up.weight", True)
        add_tensor(p + "ffn.down.weight", True)
        add_tensor(p + "ple_gate.weight", True)
        add_tensor(p + "ple_proj.weight", True)
        add_tensor(p + "ple_norm.weight", False)

    add_tensor("out_norm.weight", False)
    flags = 0
    if cfg.head_is_tied:
        flags |= FLAG_TIED_HEAD
    else:
        add_tensor("head.weight", True)

    print(f"Quantizing {len(plan)} tensors (group_size={args.group}, untied_head={not cfg.head_is_tied})...")
    dq_sd = {k: v.clone() for k, v in sd.items()}
    blobs = []

    for name, t, quant in plan:
        if quant:
            packed, scales, dq = quant_pack(t, group=args.group)
            dq_sd[name] = dq
            blobs.append(("Q", name, t.shape, packed, scales))
        else:
            blobs.append(("F", name, t.shape, t.contiguous().numpy().astype(np.float32), None))

    # Write binary artifact
    bin_path = args.out_dir / args.out_name

    with open(bin_path, "wb") as f:
        # Header (56 bytes)
        f.write(struct.pack("<IIII", MAGIC, FORMAT_VERSION, HEADER_BYTES, flags))
        f.write(struct.pack("<II", cfg.vocab_size, out_vocab))
        for v in [cfg.d_model, cfg.n_layers, cfg.n_heads, cfg.ffn_hidden, cfg.ple_dim, cfg.seq_len, args.group]:
            f.write(struct.pack("<i", v))
        f.write(struct.pack("<f", cfg.rope_theta))

        # Tensors
        for entry in blobs:
            kind = entry[0]
            if kind == "Q":
                _, _, _, packed, scales = entry
                f.write(struct.pack("<i", args.group))
                f.write(packed.tobytes())
                f.write(scales.tobytes())
            else:
                _, _, _, arr, _ = entry
                f.write(arr.tobytes())

    bin_size = bin_path.stat().st_size
    print(f"✓ Wrote {bin_path} ({bin_size / (1024*1024):.2f} MB / {bin_size:,} bytes)")

    # Copy tokenizer.json
    tok_out = args.out_dir / "tokenizer.json"
    if not (tok_out.exists() and os.path.samefile(args.tokenizer, tok_out)):
        shutil.copy2(args.tokenizer, tok_out)
        print(f"✓ Copied tokenizer to {tok_out}")

    # Generate metadata.json
    metadata = {
        "model_name": "sourdough_q4",
        "architecture": "ple",
        "arm": cfg.arm,
        "quantization": "int4_symmetric",
        "group_size": args.group,
        "dim": cfg.d_model,
        "n_layers": cfg.n_layers,
        "n_heads": cfg.n_heads,
        "ffn_hidden": cfg.ffn_hidden,
        "ple_dim": cfg.ple_dim,
        "vocab_size": cfg.vocab_size,
        "active_vocab_size": out_vocab,
        "seq_len": cfg.seq_len,
        "rope_theta": cfg.rope_theta,
        "tied_head": cfg.head_is_tied,
        "total_parameters": ck.get("params", {}).get("total", 2309248),
        "target_hardware": {
            "mcu": "ESP32-S3",
            "recommended_module": "ESP32-S3-DevKitC-1-N16R8",
            "flash_required_mb": 16,
            "psram_required_mb": 8,
            "flash_partition_offset": "0x110000",
        },
    }
    meta_path = args.out_dir / "metadata.json"
    meta_path.write_text(json.dumps(metadata, indent=2), encoding="utf-8")
    print(f"✓ Wrote metadata to {meta_path}")

    # Golden verification inference
    if cfg.head_is_tied and "head.weight" in dq_sd:
        dq_sd["head.weight"] = dq_sd["tok_emb.weight"]

    gold = TinyLM(cfg)
    gold.load_state_dict(dq_sd)
    gold.eval()

    prompt = [1, 50, 100, 200, 42, 500, 13, 99]
    ids = torch.tensor([prompt])
    with torch.no_grad():
        logits, _ = gold(ids)
    last_logits = logits[0, -1].numpy().astype(np.float32)[:out_vocab]

    # Save golden.npz
    np.savez(
        args.out_dir / "golden.npz",
        prompt=np.array(prompt, dtype=np.int32),
        logits=last_logits,
    )

    # Save golden.txt
    with open(args.out_dir / "golden.txt", "w") as gf:
        gf.write(f"{len(prompt)}\n")
        gf.write(" ".join(str(t) for t in prompt) + "\n")
        gf.write("\n".join(f"{v:.6f}" for v in last_logits) + "\n")

    top5 = last_logits.argsort()[-5:][::-1]
    print(f"✓ Generated golden reference: prompt={prompt}, top5={top5.tolist()}")
    print("Export complete!")


if __name__ == "__main__":
    main()
