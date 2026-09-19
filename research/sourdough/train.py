#!/usr/bin/env python3
"""Train a micro-LLM on Sourdough Bread Baking Q&A for ESP32-S3.

Supports:
  - PLE (Per-Layer Embeddings, similar to Google Gemma 3n and slvDev/esp32-ai-barista)
  - Dense transformer
"""

import argparse
import hashlib
import json
import math
import os
import sys
import time
from pathlib import Path

import numpy as np
import torch

from research.model import Config, make_model

PROJECT_ROOT = Path(__file__).resolve().parents[2]
DATA_ROOT = PROJECT_ROOT / "data" / "sourdough"
RUNS_DIR = PROJECT_ROOT / "runs" / "sourdough"


def get_device():
    if torch.cuda.is_available():
        return "cuda"
    if torch.backends.mps.is_available():
        return "mps"
    return "cpu"


class AsymmetricBatcher:
    """Loads pre-encoded (x, y) tensor samples for asymmetric vocabulary training."""
    def __init__(self, split: str, batch_size: int, seq_len: int, device: str, dataset_dir: Path, pad_id: int = 0, seed: int = 42):
        self.bs, self.sl, self.device = batch_size, seq_len, device
        self.pad_id = pad_id
        self.rng = np.random.default_rng(1234 if split == "val" else seed)
        path = dataset_dir / f"{split}.pt"
        self.samples = torch.load(path, weights_only=True)

    def stream(self):
        n = len(self.samples)
        while True:
            ix = self.rng.integers(0, n, self.bs)
            batch = [self.samples[i] for i in ix]
            max_len = min(self.sl, max(len(s["x"]) for s in batch))
            x_arr = np.full((self.bs, max_len), self.pad_id, dtype=np.int64)
            y_arr = np.full((self.bs, max_len), -1, dtype=np.int64)
            for j, s in enumerate(batch):
                L = min(len(s["x"]), max_len)
                x_arr[j, :L] = s["x"][:L].numpy()
                y_arr[j, :L] = s["y"][:L].numpy()
            yield (
                torch.from_numpy(x_arr).to(self.device, non_blocking=True),
                torch.from_numpy(y_arr).to(self.device, non_blocking=True),
            )


class Batcher:
    def __init__(self, split: str, batch_size: int, seq_len: int, device: str, dataset_dir: Path, seed: int = 42):
        self.bs, self.sl, self.device = batch_size, seq_len, device
        self.rng = np.random.default_rng(1234 if split == "val" else seed)

        bin_path = dataset_dir / f"{split}.bin"
        self.data = np.fromfile(bin_path, dtype=np.uint16)

        # Parse document boundaries and prompt-completion boundaries for SFT loss masking
        tok_file = dataset_dir / "tokenizer.json"
        self.docs, self.colons = [], []

        if tok_file.exists():
            from tokenizers import Tokenizer
            tok = Tokenizer.from_file(str(tok_file))
            eot = tok.token_to_id("<|endoftext|>")
            asst_ids = tok.encode("Assistant:").ids
            eot_idx = np.where(self.data == eot)[0]

            for i in range(len(eot_idx) - 1):
                s, e = eot_idx[i], eot_idx[i + 1]
                doc = self.data[s : e + 1]
                if len(doc) <= 2:
                    continue
                colon_pos = -1
                if len(asst_ids) == 2:
                    matches = np.where((doc[:-1] == asst_ids[0]) & (doc[1:] == asst_ids[1]))[0]
                    if len(matches) > 0:
                        colon_pos = matches[0] + 1
                elif len(asst_ids) == 1:
                    matches = np.where(doc == asst_ids[0])[0]
                    if len(matches) > 0:
                        colon_pos = matches[0]
                if colon_pos > 0:
                    self.docs.append(doc)
                    self.colons.append(colon_pos)

    def stream(self):
        if self.docs:
            n_docs = len(self.docs)
            while True:
                ix = self.rng.integers(0, n_docs, self.bs)
                x_arr = np.zeros((self.bs, self.sl), dtype=np.int64)
                y_arr = np.full((self.bs, self.sl), -1, dtype=np.int64)
                for j, i in enumerate(ix):
                    d = self.docs[i]
                    c = self.colons[i]
                    L = min(len(d), self.sl)
                    x_arr[j, :L] = d[:L]
                    if c < L - 1:
                        y_arr[j, c : L - 1] = d[c + 1 : L]
                yield (
                    torch.from_numpy(x_arr).to(self.device, non_blocking=True),
                    torch.from_numpy(y_arr).to(self.device, non_blocking=True),
                )
        else:
            max_idx = len(self.data) - self.sl - 1
            while True:
                ix = self.rng.integers(0, max_idx, self.bs)
                x_arr = np.empty((self.bs, self.sl), dtype=np.int64)
                y_arr = np.empty((self.bs, self.sl), dtype=np.int64)
                for j, i in enumerate(ix):
                    chunk = self.data[i : i + self.sl + 1]
                    x_arr[j] = chunk[:-1]
                    y_arr[j] = chunk[1:]
                yield (
                    torch.from_numpy(x_arr).to(self.device, non_blocking=True),
                    torch.from_numpy(y_arr).to(self.device, non_blocking=True),
                )


def lr_at(step: int, total_steps: int, base_lr: float, warmup: int) -> float:
    if step < warmup:
        return base_lr * (step + 1) / max(1, warmup)
    progress = (step - warmup) / max(1, total_steps - warmup)
    return base_lr * 0.5 * (1.0 + math.cos(math.pi * progress))


@torch.no_grad()
def evaluate(model, batcher: Batcher, iters: int = 10) -> float:
    model.eval()
    losses = []
    stream = batcher.stream()
    for _ in range(iters):
        x, y = next(stream)
        _, loss = model(x, y)
        losses.append(loss.item())
    model.train()
    return float(np.mean(losses))


def main():
    parser = argparse.ArgumentParser(description="Train Sourdough micro-LLM for ESP32-S3.")
    parser.add_argument("--arm", choices=["dense", "ple", "tiered"], default="ple", help="Model architecture")
    parser.add_argument("--vocab", type=int, default=2048, help="Vocabulary size (default: 2048)")
    parser.add_argument("--seq-len", type=int, default=128, help="Context sequence length (default: 128)")
    parser.add_argument("--d-model", type=int, default=160, help="Model embedding dimension (default: 160)")
    parser.add_argument("--n-layers", type=int, default=6, help="Number of transformer layers (default: 6)")
    parser.add_argument("--n-heads", type=int, default=4, help="Number of attention heads (default: 4)")
    parser.add_argument("--ffn-hidden", type=int, default=448, help="FFN hidden dimension (default: 448)")
    parser.add_argument("--ple-dim", type=int, default=128, help="PLE dimension per layer (default: 128)")
    parser.add_argument("--target-core", type=int, default=None, help="Target core param count (default: None, uses --ffn-hidden)")
    parser.add_argument("--batch-size", type=int, default=16, help="Batch size (default: 16)")
    parser.add_argument("--micro-batch-size", type=int, default=4, help="Micro batch size for memory savings")
    parser.add_argument("--steps", type=int, default=1200, help="Total training steps (default: 1200)")
    parser.add_argument("--lr", type=float, default=1e-3, help="Learning rate (default: 1e-3)")
    parser.add_argument("--warmup", type=int, default=100, help="Warmup steps (default: 100)")
    parser.add_argument("--eval-every", type=int, default=100, help="Evaluation interval")
    parser.add_argument("--seed", type=int, default=0, help="Random seed")
    parser.add_argument("--tag", type=str, default="sourdough-v1", help="Run identifier tag")
    parser.add_argument("--asymmetric", action="store_true", default=True, help="Use asymmetric vocabulary (default: True)")
    parser.add_argument("--no-asymmetric", dest="asymmetric", action="store_false", help="Use legacy symmetric vocabulary")

    args = parser.parse_args()

    device = get_device()
    print(f"Training device: {device}")
    RUNS_DIR.mkdir(parents=True, exist_ok=True)

    micro_bs = min(args.micro_batch_size, args.batch_size)
    accum_steps = max(1, args.batch_size // micro_bs)

    if args.asymmetric:
        layout_path = DATA_ROOT / "layout.json"
        asym_dir = DATA_ROOT / "asymmetric"
        if not layout_path.exists() or not (asym_dir / "train.pt").exists():
            raise SystemExit(
                "Asymmetric dataset or layout.json not found. Run 'task layout' and 'uv run python -m research.sourdough.prepare_asymmetric' first."
            )
        layout = json.loads(layout_path.read_text(encoding="utf-8"))
        vocab_size = layout["total"]
        out_vocab_size = layout["n_words"]
        pad_id = layout["out2in"][0]

        tok_path = DATA_ROOT / "tokenizer.json"
        tok_sha = hashlib.sha256(open(tok_path, "rb").read()).hexdigest() if tok_path.exists() else "asym"

        print(f"Asymmetric mode: vocab_size={vocab_size}, out_vocab_size={out_vocab_size} (untied head)")
        base = Config(
            seq_len=args.seq_len,
            ple_dim=args.ple_dim,
            vocab_size=vocab_size,
            out_vocab_size=out_vocab_size,
            d_model=args.d_model,
            n_layers=args.n_layers,
            n_heads=args.n_heads,
            ffn_hidden=args.ffn_hidden,
        )
        if args.target_core is not None:
            model = make_model(args.arm, args.target_core, base).to(device)
        else:
            model = make_model(args.arm, 0, base, fixed_ffn=args.ffn_hidden).to(device)

        train_b = AsymmetricBatcher("train", micro_bs, args.seq_len, device, asym_dir, pad_id=pad_id, seed=args.seed)
        val_b = AsymmetricBatcher("val", micro_bs, args.seq_len, device, asym_dir, pad_id=pad_id)
    else:
        dataset_dir = DATA_ROOT / f"vocab-{args.vocab}"
        tok_path = dataset_dir / "tokenizer.json"
        if not tok_path.exists():
            raise SystemExit(f"Dataset not found at {dataset_dir}. Run 'task sourdough:prepare' first.")

        tok_sha = hashlib.sha256(open(tok_path, "rb").read()).hexdigest()
        base = Config(
            seq_len=args.seq_len,
            ple_dim=args.ple_dim,
            vocab_size=args.vocab,
            d_model=args.d_model,
            n_layers=args.n_layers,
            n_heads=args.n_heads,
            ffn_hidden=args.ffn_hidden,
        )
        if args.target_core is not None:
            model = make_model(args.arm, args.target_core, base).to(device)
        else:
            model = make_model(args.arm, 0, base, fixed_ffn=args.ffn_hidden).to(device)
        train_b = Batcher("train", micro_bs, args.seq_len, device, dataset_dir, seed=args.seed)
        val_b = Batcher("val", micro_bs, args.seq_len, device, dataset_dir)

    budget = model.param_budget()
    print(f"Model architecture: {args.arm.upper()} | Total parameters: {budget.get('total', 0):,}")

    decay, no_decay = [], []
    for n, p in model.named_parameters():
        (no_decay if p.ndim < 2 or "table" in n or "tok_emb" in n else decay).append(p)
    opt = torch.optim.AdamW(
        [{"params": decay, "weight_decay": 0.05}, {"params": no_decay, "weight_decay": 0.0}],
        lr=args.lr,
        betas=(0.9, 0.95),
    )
    train_stream = train_b.stream()

    run_name = f"{args.arm}-{args.tag}-s{args.seed}"
    history, best_val = [], float("inf")
    t0 = time.time()

    print(f"Starting training for {args.steps} steps...")
    for step in range(args.steps):
        lr = lr_at(step, args.steps, args.lr, args.warmup)
        for g in opt.param_groups:
            g["lr"] = lr

        step_loss = 0.0
        opt.zero_grad(set_to_none=True)
        for _ in range(accum_steps):
            x, y = next(train_stream)
            _, loss = model(x, y)
            loss_scaled = loss / accum_steps
            loss_scaled.backward()
            step_loss += loss.item() / accum_steps

        torch.nn.utils.clip_grad_norm_(model.parameters(), 1.0)
        opt.step()

        if step % args.eval_every == 0 or step == args.steps - 1:
            vl = evaluate(model, val_b, iters=5)
            best_val = min(best_val, vl)
            elapsed = time.time() - t0
            print(
                f"Step {step:4d}/{args.steps} | Train: {step_loss:.4f} | Val: {vl:.4f} | "
                f"PPL: {math.exp(vl):6.2f} | {elapsed:.1f}s"
            )
            history.append({"step": step, "train": step_loss, "val": vl})

    # Save checkpoint
    ckpt_path = RUNS_DIR / f"{run_name}.pt"
    torch.save(
        {
            "cfg": model.cfg.__dict__,
            "state": model.state_dict(),
            "tokenizer_sha256": tok_sha,
            "vocab": args.vocab,
            "arm": args.arm,
            "params": budget,
        },
        ckpt_path,
    )
    print(f"\n✓ Saved model checkpoint to {ckpt_path}")


if __name__ == "__main__":
    main()
