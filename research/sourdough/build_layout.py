#!/usr/bin/env python3
"""Build layout.json and train BPE encoder for Sourdough Baker Assistant.

Follows the asymmetric vocabulary contract from slvDev/esp32-ai-barista:
- Trains a BPE tokenizer (e.g. 4,096 vocab) for encoding arbitrary user questions.
- Maps each of the curated output classes in vocab.json to an input token ID
  in out2in. Classes whose word is already an exact single BPE token reuse that
  BPE ID; classes requiring multi-token BPE sequences receive dedicated appended
  embedding rows starting at bpe_vocab.

Outputs:
  - data/sourdough/layout.json
  - data/sourdough/tokenizer.json
"""

import argparse
import json
from pathlib import Path
from typing import List, Dict

from tokenizers import Tokenizer, models, pre_tokenizers, trainers, decoders

PROJECT_ROOT = Path(__file__).resolve().parents[2]
DATA_DIR = PROJECT_ROOT / "data" / "sourdough"
CORPUS_PATH = DATA_DIR / "raw" / "sourdough_corpus.txt"
VOCAB_PATH = DATA_DIR / "vocab.json"
LAYOUT_PATH = DATA_DIR / "layout.json"
TOKENIZER_PATH = DATA_DIR / "tokenizer.json"


def train_bpe_tokenizer(corpus_path: Path, vocab_size: int, out_path: Path) -> Tokenizer:
    if not corpus_path.exists():
        raise FileNotFoundError(f"Corpus file not found: {corpus_path}")

    print(f"Training ByteLevel BPE encoder (vocab={vocab_size})...")
    tok = Tokenizer(models.BPE(unk_token=None))
    tok.pre_tokenizer = pre_tokenizers.ByteLevel(add_prefix_space=False)
    tok.decoder = decoders.ByteLevel()
    trainer = trainers.BpeTrainer(
        vocab_size=vocab_size,
        special_tokens=["<|endoftext|>"],
        initial_alphabet=pre_tokenizers.ByteLevel.alphabet(),
        show_progress=False,
    )
    tok.train([str(corpus_path)], trainer=trainer)
    tok.save(str(out_path))
    print(f"✓ Saved BPE tokenizer to {out_path}")
    return tok


def build_layout(vocab_path: Path, tokenizer: Tokenizer) -> Dict:
    with open(vocab_path, "r", encoding="utf-8") as f:
        vocab_data = json.load(f)

    tokens = [t["token"] for t in vocab_data["tokens"]]
    n_words = len(tokens)
    bpe_vocab = tokenizer.get_vocab_size()

    # Pass 1: find which tokens can reuse an existing single BPE token
    out2in: List[int] = [-1] * n_words
    used_bpe_ids = set()

    for idx, token_str in enumerate(tokens):
        enc = tokenizer.encode(token_str).ids
        if len(enc) == 1 and enc[0] not in used_bpe_ids:
            out2in[idx] = enc[0]
            used_bpe_ids.add(enc[0])

    # Pass 2: allocate appended rows monotonically for classes needing their own row
    next_appended_id = bpe_vocab
    for idx in range(n_words):
        if out2in[idx] == -1:
            out2in[idx] = next_appended_id
            next_appended_id += 1

    total = next_appended_id

    # Validate Barista layout contract
    assert len(out2in) == n_words
    assert len(set(out2in)) == n_words, "Duplicate input ID in out2in"
    assert min(out2in) >= 0 and max(out2in) < total, "ID out of range"
    appended_ids = [tid for tid in out2in if tid >= bpe_vocab]
    assert appended_ids == list(range(bpe_vocab, total)), "Appended IDs must be monotonic range(bpe_vocab, total)"

    reused_count = n_words - len(appended_ids)
    print(f"Layout summary:")
    print(f"  - Output classes (n_words) : {n_words}")
    print(f"  - Base BPE vocab          : {bpe_vocab}")
    print(f"  - Reused BPE token IDs    : {reused_count}")
    print(f"  - Appended dedicated rows : {len(appended_ids)}")
    print(f"  - Total embedding rows    : {total}")

    return {
        "bpe_vocab": bpe_vocab,
        "total": total,
        "n_words": n_words,
        "out2in": out2in,
    }


def main():
    parser = argparse.ArgumentParser(description="Build layout.json and train BPE encoder.")
    parser.add_argument("--corpus", type=Path, default=CORPUS_PATH, help="Path to sourdough_corpus.txt")
    parser.add_argument("--vocab", type=Path, default=VOCAB_PATH, help="Path to vocab.json")
    parser.add_argument("--bpe-vocab", type=int, default=4096, help="BPE vocabulary size (default: 4096)")
    parser.add_argument("--out-layout", type=Path, default=LAYOUT_PATH, help="Output layout.json path")
    parser.add_argument("--out-tok", type=Path, default=TOKENIZER_PATH, help="Output tokenizer.json path")
    args = parser.parse_args()

    args.out_layout.parent.mkdir(parents=True, exist_ok=True)
    tok = train_bpe_tokenizer(args.corpus, args.bpe_vocab, args.out_tok)
    layout = build_layout(args.vocab, tok)

    with open(args.out_layout, "w", encoding="utf-8") as f:
        json.dump(layout, f, indent=2)

    print(f"✓ Saved layout to {args.out_layout}")


if __name__ == "__main__":
    main()
