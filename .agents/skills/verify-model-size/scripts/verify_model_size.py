#!/usr/bin/env python3
"""Pre-training & post-training sizing verifier for ESP32-S3-DevKitC-1-N16R8.

Verifies that model weights, flash partition mmap, and PSRAM/SRAM runtime buffers
fit on an ESP32-S3 with 16MB Flash and 8MB Octal PSRAM.
"""

import argparse
import os
import struct
import sys
from pathlib import Path

# ESP32-S3-DevKitC-1-N16R8 Hardware Limits
FLASH_TOTAL_BYTES = 16 * 1024 * 1024       # 16 MB
MODEL_PARTITION_OFFSET = 0x110000          # 1,114,112 bytes
MODEL_PARTITION_LIMIT = 0xEE0000           # 15,597,568 bytes (~14.88 MB)
PSRAM_TOTAL_BYTES = 8 * 1024 * 1024        # 8 MB (8,388,608 bytes)
PSRAM_SAFE_LIMIT = 7 * 1024 * 1024         # 7 MB (leaving 1 MB headroom for OS/heap)
SRAM_SAFE_LIMIT = 327 * 1024               # ~327 KB available user SRAM
HEADER_BYTES = 56                          # Format v1 header


def quant_tensor_bytes(rows: int, cols: int, group: int = 128) -> int:
    """Bytes required to store an int4 quant tensor in model.bin."""
    row_bytes = (cols + 1) // 2
    n_groups = (cols + group - 1) // group
    packed_bytes = rows * row_bytes
    scale_bytes = rows * n_groups * 2  # fp16
    return 4 + packed_bytes + scale_bytes  # 4 bytes for int32 group prefix


def fp32_tensor_bytes(n: int) -> int:
    """Bytes required to store an unquantized FP32 tensor in model.bin."""
    return n * 4


def stage_psram_bytes(rows: int, cols: int, group: int = 128) -> int:
    """Bytes required for staged int8 weights + float scales in PSRAM."""
    w_bytes = rows * cols  # int8
    scale_offset = (w_bytes + 3) & ~3
    n_groups = (cols + group - 1) // group
    return scale_offset + rows * n_groups * 4  # fp32 scales


def solve_ffn_hidden(target_core: int, d_model: int, n_layers: int, ple_dim: int) -> int:
    """Calculate ffn_hidden from target_core parameters."""
    fixed = ple_dim * d_model + n_layers * (4 * d_model * d_model + 2 * ple_dim * d_model)
    per_ffn = 3 * n_layers * d_model
    ffn_hidden = max(16, (target_core - fixed) // per_ffn)
    # Round to multiple of 2
    return (ffn_hidden + 1) & ~1


def calculate_sizing(
    vocab_size: int,
    out_vocab_size: int,
    d_model: int,
    n_layers: int,
    n_heads: int,
    ffn_hidden: int,
    ple_dim: int,
    seq_len: int,
    group: int = 128,
    tied_head: bool = True,
):
    """Calculate model.bin file size and runtime memory footprints."""
    # 1. Flash binary size
    bin_bytes = HEADER_BYTES
    # Embedding
    bin_bytes += quant_tensor_bytes(vocab_size, d_model, group)
    # PLE projection & norm
    bin_bytes += quant_tensor_bytes(n_layers * ple_dim, d_model, group)
    bin_bytes += fp32_tensor_bytes(ple_dim)
    # PLE table
    bin_bytes += quant_tensor_bytes(vocab_size, n_layers * ple_dim, group)
    # Transformer layers
    for _ in range(n_layers):
        bin_bytes += fp32_tensor_bytes(d_model)                           # attn_norm
        bin_bytes += quant_tensor_bytes(3 * d_model, d_model, group)      # qkv
        bin_bytes += quant_tensor_bytes(d_model, d_model, group)          # attn_proj
        bin_bytes += fp32_tensor_bytes(d_model)                           # ffn_norm
        bin_bytes += quant_tensor_bytes(ffn_hidden, d_model, group)       # gate
        bin_bytes += quant_tensor_bytes(ffn_hidden, d_model, group)       # up
        bin_bytes += quant_tensor_bytes(d_model, ffn_hidden, group)       # down
        bin_bytes += quant_tensor_bytes(ple_dim, d_model, group)          # ple_gate
        bin_bytes += quant_tensor_bytes(d_model, ple_dim, group)          # ple_proj
        bin_bytes += fp32_tensor_bytes(d_model)                           # ple_norm
    # Final out_norm
    bin_bytes += fp32_tensor_bytes(d_model)
    # Untied head (if applicable)
    if not tied_head:
        bin_bytes += quant_tensor_bytes(out_vocab_size, d_model, group)

    # 2. PSRAM footprint (staged int8 core + head + KV cache + logits)
    # Staged core tensors: ple_model_proj + 7 layer tensors
    psram_staged = stage_psram_bytes(n_layers * ple_dim, d_model, group)
    for _ in range(n_layers):
        psram_staged += stage_psram_bytes(3 * d_model, d_model, group)
        psram_staged += stage_psram_bytes(d_model, d_model, group)
        psram_staged += stage_psram_bytes(ffn_hidden, d_model, group)
        psram_staged += stage_psram_bytes(ffn_hidden, d_model, group)
        psram_staged += stage_psram_bytes(d_model, ffn_hidden, group)
        psram_staged += stage_psram_bytes(ple_dim, d_model, group)
        psram_staged += stage_psram_bytes(d_model, ple_dim, group)
    # Staged output head
    psram_staged += stage_psram_bytes(out_vocab_size, d_model, group)

    # Dynamic PSRAM buffers
    psram_logits = out_vocab_size * 4
    psram_kv = 2 * (n_layers * seq_len * d_model * 4)
    total_psram = psram_staged + psram_logits + psram_kv

    # 3. Internal SRAM working set
    sram_scratch = (
        d_model * 4 + max(ffn_hidden, d_model) * 4 + 3 * d_model * 4 +
        d_model * 4 + ffn_hidden * 4 + max(ple_dim, ffn_hidden) * 4 +
        3 * (n_layers * ple_dim * 4) + seq_len * 4
    )
    sram_norms = (ple_dim + 3 * n_layers * d_model + d_model) * 4
    sram_static_xq = 2 * 4096  # dual-core LLM_Q8_MAX_INPUT static buffers
    total_sram = sram_scratch + sram_norms + sram_static_xq

    # 4. Total parameter count
    core_params = (
        ple_dim * d_model +
        n_layers * (4 * d_model * d_model + 3 * ffn_hidden * d_model + 2 * ple_dim * d_model)
    )
    table_params = vocab_size * (d_model + n_layers * ple_dim)
    total_params = core_params + table_params

    return {
        "bin_bytes": bin_bytes,
        "psram_staged": psram_staged,
        "psram_logits": psram_logits,
        "psram_kv": psram_kv,
        "total_psram": total_psram,
        "total_sram": total_sram,
        "core_params": core_params,
        "table_params": table_params,
        "total_params": total_params,
    }


def parse_bin_file(path: str):
    """Read configuration from an exported model.bin header."""
    with open(path, "rb") as f:
        data = f.read(56)
    if len(data) < 56:
        raise ValueError(f"File too short for PLE header: {len(data)} bytes")
    fields = struct.unpack("<IIIIIIiiiiiiif", data)
    magic, ver, hdr_len, flags, vocab, out_vocab, dim, layers, heads, ffn, ple, seq, group, rope = fields
    if magic != 0x00454C50:
        raise ValueError(f"Invalid magic: {hex(magic)}, expected 0x00454C50 ('PLE\\0')")
    return {
        "vocab_size": vocab,
        "out_vocab_size": out_vocab,
        "d_model": dim,
        "n_layers": layers,
        "n_heads": heads,
        "ffn_hidden": ffn,
        "ple_dim": ple,
        "seq_len": seq,
        "group": group,
        "tied_head": bool(flags & 1),
    }


def main():
    parser = argparse.ArgumentParser(
        description="Verify model binary size and memory budget for ESP32-S3-DevKitC-1-N16R8 before training."
    )
    # File input mode
    parser.add_argument("--bin", type=str, default=None, help="Path to existing model.bin to inspect")
    
    # Architecture parameter mode (pre-training)
    parser.add_argument("--vocab", type=int, default=32768, help="Vocabulary size (default: 32768)")
    parser.add_argument("--out-vocab", type=int, default=25353, help="Output vocabulary size (default: 25353)")
    parser.add_argument("--d-model", type=int, default=96, help="Model hidden dimension (default: 96)")
    parser.add_argument("--n-layers", type=int, default=6, help="Number of transformer layers (default: 6)")
    parser.add_argument("--n-heads", type=int, default=4, help="Number of attention heads (default: 4)")
    parser.add_argument("--ffn-hidden", type=int, default=None, help="FFN hidden dimension (auto-solved if target-core provided)")
    parser.add_argument("--target-core", type=int, default=560000, help="Target core parameter budget (default: 560000)")
    parser.add_argument("--ple-dim", type=int, default=128, help="PLE adapter dimension (default: 128)")
    parser.add_argument("--seq-len", type=int, default=256, help="Context sequence length (default: 256)")
    parser.add_argument("--group", type=int, default=128, help="Quantization group size (default: 128)")

    args = parser.parse_args()

    actual_file_size = None
    if args.bin:
        bin_path = Path(args.bin).resolve()
        if not bin_path.exists():
            print(f"Error: Specified bin file not found: {bin_path}", file=sys.stderr)
            sys.exit(1)
        actual_file_size = bin_path.stat().st_size
        cfg = parse_bin_file(str(bin_path))
        print(f"Loaded config from {bin_path.name}:")
    else:
        # Pre-training estimation from parameters
        ffn = args.ffn_hidden
        if ffn is None:
            ffn = solve_ffn_hidden(args.target_core, args.d_model, args.n_layers, args.ple_dim)
        cfg = {
            "vocab_size": args.vocab,
            "out_vocab_size": args.out_vocab,
            "d_model": args.d_model,
            "n_layers": args.n_layers,
            "n_heads": args.n_heads,
            "ffn_hidden": ffn,
            "ple_dim": args.ple_dim,
            "seq_len": args.seq_len,
            "group": args.group,
            "tied_head": True,
        }

    res = calculate_sizing(**cfg)
    bin_size = actual_file_size if actual_file_size is not None else res["bin_bytes"]

    # Evaluation
    flash_fits = bin_size <= MODEL_PARTITION_LIMIT
    flash_margin = MODEL_PARTITION_LIMIT - bin_size
    psram_fits = res["total_psram"] <= PSRAM_TOTAL_BYTES
    psram_margin = PSRAM_TOTAL_BYTES - res["total_psram"]
    sram_fits = res["total_sram"] <= SRAM_SAFE_LIMIT
    sram_margin = SRAM_SAFE_LIMIT - res["total_sram"]

    print("=" * 78)
    print("ESP32-S3-DevKitC-1-N16R8 Model Sizing & Memory Verification")
    print("=" * 78)
    print(f"Model Configuration:")
    print(f"  Vocab: {cfg['vocab_size']} (Out: {cfg['out_vocab_size']}) | D: {cfg['d_model']} | Layers: {cfg['n_layers']} | Heads: {cfg['n_heads']}")
    print(f"  FFN: {cfg['ffn_hidden']} | PLE: {cfg['ple_dim']} | SeqLen: {cfg['seq_len']} | Quant Group: {cfg['group']}")
    print(f"  Parameters: Core {res['core_params'] / 1e6:.2f}M + Table {res['table_params'] / 1e6:.2f}M = Total {res['total_params'] / 1e6:.2f}M")
    print("-" * 78)

    print(f"{'Memory Domain':<22} | {'Requirement':<12} | {'Hardware Limit':<15} | {'Margin / Status'}")
    print("-" * 78)

    # Flash Check
    status_flash = f"✓ FITS (+{flash_margin / 1024:.0f} KB)" if flash_fits else f"✗ OVERFLOW ({flash_margin / 1024:.0f} KB)"
    print(f"{'Flash (model part)':<22} | {bin_size / (1024*1024):.2f} MB     | {MODEL_PARTITION_LIMIT / (1024*1024):.2f} MB (0xEE0000) | {status_flash}")

    # PSRAM Check
    status_psram = f"✓ FITS (+{psram_margin / (1024*1024):.2f} MB)" if psram_fits else f"✗ OVERFLOW ({psram_margin / (1024*1024):.2f} MB)"
    print(f"{'PSRAM (staged+KV)':<22} | {res['total_psram'] / (1024*1024):.2f} MB     | {PSRAM_TOTAL_BYTES / (1024*1024):.2f} MB (Octal)    | {status_psram}")

    # SRAM Check
    status_sram = f"✓ FITS (+{sram_margin / 1024:.0f} KB)" if sram_fits else f"✗ OVERFLOW ({sram_margin / 1024:.0f} KB)"
    print(f"{'Internal SRAM':<22} | {res['total_sram'] / 1024:.1f} KB      | ~{SRAM_SAFE_LIMIT / 1024:.0f} KB (Internal)  | {status_sram}")
    print("=" * 78)

    # Detailed PSRAM Breakdown
    print("PSRAM Breakdown:")
    print(f"  - Staged INT8 Core + Head: {res['psram_staged'] / (1024*1024):.2f} MB")
    print(f"  - KV Cache (2*L*S*D*4):    {res['psram_kv'] / (1024*1024):.2f} MB")
    print(f"  - Logits Scratch (Vout*4):  {res['psram_logits'] / 1024:.1f} KB")

    if not flash_fits:
        print("\n[FATAL ERROR] Model binary exceeds the 0xEE0000 (14.88 MB) flash partition limit!", file=sys.stderr)
        print("Remedies before training:", file=sys.stderr)
        print("  1. Reduce vocabulary size (--vocab) or PLE dimension (--ple-dim).", file=sys.stderr)
        print("  2. Reduce core budget (--target-core) or model layers (--n-layers).", file=sys.stderr)
        print("  3. Increase quantization group size if accuracy permits.", file=sys.stderr)
        sys.exit(1)

    if not psram_fits:
        print("\n[FATAL ERROR] Model runtime allocations exceed the 8 MB PSRAM budget!", file=sys.stderr)
        sys.exit(1)

    print("\n✓ ALL SIZING CHECKS PASSED: Model is guaranteed to fit on ESP32-S3-DevKitC-1-N16R8.")
    sys.exit(0)


if __name__ == "__main__":
    main()
