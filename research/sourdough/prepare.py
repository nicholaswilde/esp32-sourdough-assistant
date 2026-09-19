#!/usr/bin/env python3
"""Train BPE tokenizer and export token bins for Sourdough Bread Baking model.

Supports leak-free train/val splits when sourdough_qa.jsonl has 'split' tags.

Outputs:
  - data/sourdough/vocab-{vocab}/tokenizer.json
  - data/sourdough/vocab-{vocab}/train.bin (uint16)
  - data/sourdough/vocab-{vocab}/val.bin (uint16)
"""

import argparse
import json
import os
import sys
from pathlib import Path

import numpy as np
from tokenizers import Tokenizer, decoders, models, pre_tokenizers, trainers

PROJECT_ROOT = Path(__file__).resolve().parents[2]
DATA_DIR = PROJECT_ROOT / "data" / "sourdough"
RAW_FILE = DATA_DIR / "raw" / "sourdough_corpus.txt"
JSONL_FILE = DATA_DIR / "raw" / "sourdough_qa.jsonl"
DEFAULT_VOCAB = 2048
VAL_FRACTION = 0.05


def variant_dir(vocab_size: int) -> Path:
    return DATA_DIR / f"vocab-{vocab_size}"


def train_tokenizer(text: str, vocab_size: int, out_path: Path, force: bool = False) -> Tokenizer:
    if out_path.exists() and not force:
        print(f"Loading existing tokenizer from {out_path}...")
        return Tokenizer.from_file(str(out_path))

    print(f"Training ByteLevel BPE tokenizer (vocab={vocab_size})...")
    tok = Tokenizer(models.BPE(unk_token=None))
    tok.pre_tokenizer = pre_tokenizers.ByteLevel(add_prefix_space=False)
    tok.decoder = decoders.ByteLevel()
    trainer = trainers.BpeTrainer(
        vocab_size=vocab_size,
        special_tokens=["<|endoftext|>"],
        initial_alphabet=pre_tokenizers.ByteLevel.alphabet(),
        show_progress=True,
    )
    tok.train_from_iterator([text], trainer=trainer)
    tok.save(str(out_path))
    print(f"✓ Tokenizer saved to {out_path}")
    return tok


def main():
    parser = argparse.ArgumentParser(description="Prepare sourdough dataset: train BPE and write token bins.")
    parser.add_argument(
        "--vocab",
        type=int,
        default=DEFAULT_VOCAB,
        help=f"Vocabulary size (default: {DEFAULT_VOCAB})",
    )
    parser.add_argument(
        "--force",
        action="store_true",
        help="Rebuild bins even if they already exist",
    )

    args = parser.parse_args()

    if not 0 < args.vocab <= 65536:
        raise SystemExit("--vocab must be between 1 and 65536 (bins are uint16)")

    out = variant_dir(args.vocab)
    out.mkdir(parents=True, exist_ok=True)
    train_bin = out / "train.bin"
    val_bin = out / "val.bin"
    tok_path = out / "tokenizer.json"

    if not args.force and train_bin.exists() and val_bin.exists() and tok_path.exists():
        print(f"Bins already exist in {out}. Pass --force to regenerate.")
        return

    # Ensure corpus exists
    if not RAW_FILE.exists() or not JSONL_FILE.exists():
        print(f"Raw dataset files not found. Running generator...")
        from research.sourdough.generate import main as run_generate
        run_generate()

    with open(RAW_FILE, "r", encoding="utf-8") as f:
        text = f.read()

    tok = train_tokenizer(text, args.vocab, tok_path, force=args.force)
    eot = tok.token_to_id("<|endoftext|>")

    train_ids = []
    val_ids = []

    # Check if JSONL contains explicit train/val split tags (leak-free mode)
    use_jsonl_splits = False
    if JSONL_FILE.exists():
        with open(JSONL_FILE, "r", encoding="utf-8") as f:
            records = [json.loads(line) for line in f if line.strip()]
        if any("split" in r for r in records):
            use_jsonl_splits = True

    if use_jsonl_splits:
        train_docs = [f"User: {r['prompt']}\nAssistant: {r['completion']}" for r in records if r.get("split") != "val"]
        val_docs = [f"User: {r['prompt']}\nAssistant: {r['completion']}" for r in records if r.get("split") == "val"]
        print(f"Encoding Q&A documents using leak-free split (Train: {len(train_docs):,}, Val: {len(val_docs):,})...")

        for doc in train_docs:
            enc = tok.encode(doc)
            train_ids.append(eot)
            train_ids.extend(enc.ids)

        for doc in val_docs:
            enc = tok.encode(doc)
            val_ids.append(eot)
            val_ids.extend(enc.ids)
    else:
        print("Encoding Q&A documents using legacy split...")
        raw_docs = [d.strip() for d in text.split("<|endoftext|>") if d.strip()]
        np.random.seed(42)
        indices = np.random.permutation(len(raw_docs))
        n_val = max(1, int(len(raw_docs) * VAL_FRACTION))
        val_indices = set(indices[:n_val])

        for i, doc in enumerate(raw_docs):
            enc = tok.encode(doc)
            target_list = val_ids if i in val_indices else train_ids
            target_list.append(eot)
            target_list.extend(enc.ids)

    if train_ids:
        train_ids.append(eot)
    if val_ids:
        val_ids.append(eot)

    print(f"Train tokens: {len(train_ids):,} ({len(train_ids)*2/1024:.1f} KB)")
    print(f"Val tokens:   {len(val_ids):,} ({len(val_ids)*2/1024:.1f} KB)")

    np.array(train_ids, dtype=np.uint16).tofile(train_bin)
    np.array(val_ids, dtype=np.uint16).tofile(val_bin)

    print(f"\n✓ Saved binary dataset to {out}:")
    print(f"  train:     {train_bin}")
    print(f"  val:       {val_bin}")
    print(f"  tokenizer: {tok_path}")


if __name__ == "__main__":
    main()
