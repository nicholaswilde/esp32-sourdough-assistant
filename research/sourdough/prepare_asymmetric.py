#!/usr/bin/env python3
"""Pre-encode Q&A dataset into asymmetric (x, y) token pairs.

For each Q&A sample:
  - Prompt is encoded into BPE input token IDs via data/sourdough/tokenizer.json.
  - Completion is tokenized into word classes via data/sourdough/vocab.json.
  - Input sequence x:
      [prompt_bpe_ids..., OUT2IN[BOS], OUT2IN[ans_class_0], ..., OUT2IN[ans_class_last-1]]
  - Target sequence y:
      [-1, ..., -1, ans_class_0, ans_class_1, ..., EOS_CLASS]
  (where -1 is the ignore index for prompt tokens so loss is computed solely on the answer).

Outputs:
  - data/sourdough/asymmetric/train.pt
  - data/sourdough/asymmetric/val.pt
"""

import argparse
import json
import re
from pathlib import Path
from typing import List, Dict

import torch
from tokenizers import Tokenizer

PROJECT_ROOT = Path(__file__).resolve().parents[2]
DATA_DIR = PROJECT_ROOT / "data" / "sourdough"
VOCAB_PATH = DATA_DIR / "vocab.json"
LAYOUT_PATH = DATA_DIR / "layout.json"
TOKENIZER_PATH = DATA_DIR / "tokenizer.json"
QA_PATH = DATA_DIR / "raw" / "sourdough_qa.jsonl"
OUT_DIR = DATA_DIR / "asymmetric"

SPECIALS = ("<pad>", "<bos>", "<eos>", "<unk>")
BOS_CLASS = 1
EOS_CLASS = 2


def tokenize_answer(text: str) -> List[str]:
    text = text.replace("\u00b0", " ").replace("\u00ba", " ").replace("%", " % ")
    raw = re.findall(r"[a-zA-Z0-9]+(?:'[a-zA-Z]+)?|[.,:;?%]", text)
    return [t.lower() for t in raw if all(0x20 <= ord(c) <= 0x7E for c in t)]


def main():
    parser = argparse.ArgumentParser(description="Pre-encode asymmetric Q&A dataset.")
    parser.add_argument("--qa-path", type=Path, default=QA_PATH, help="Path to sourdough_qa.jsonl")
    parser.add_argument("--vocab", type=Path, default=VOCAB_PATH, help="Path to vocab.json")
    parser.add_argument("--layout", type=Path, default=LAYOUT_PATH, help="Path to layout.json")
    parser.add_argument("--tokenizer", type=Path, default=TOKENIZER_PATH, help="Path to tokenizer.json")
    parser.add_argument("--out-dir", type=Path, default=OUT_DIR, help="Output directory")
    parser.add_argument("--seq-len", type=int, default=128, help="Max sequence length")
    args = parser.parse_args()

    args.out_dir.mkdir(parents=True, exist_ok=True)

    with open(args.vocab, "r", encoding="utf-8") as f:
        vocab_data = json.load(f)
    word_to_class = {entry["token"]: idx for idx, entry in enumerate(vocab_data["tokens"])}

    with open(args.layout, "r", encoding="utf-8") as f:
        layout_data = json.load(f)
    out2in = layout_data["out2in"]

    tok = Tokenizer.from_file(str(args.tokenizer))

    train_samples = []
    val_samples = []

    with open(args.qa_path, "r", encoding="utf-8") as f:
        for line in f:
            if not line.strip():
                continue
            item = json.loads(line)
            prompt = item["prompt"]
            ans_str = item["completion"]
            split = item.get("split", "train")

            # 1. Encode prompt
            prompt_ids = tok.encode(prompt).ids

            # 2. Tokenize completion into classes
            ans_tokens = tokenize_answer(ans_str)
            ans_classes = [word_to_class[t] for t in ans_tokens] + [EOS_CLASS]

            # 3. Build input sequence x and target sequence y
            ans_in_ids = [out2in[c] for c in ans_classes]

            x = prompt_ids + [out2in[BOS_CLASS]] + ans_in_ids[:-1]
            y = [-1] * len(prompt_ids) + ans_classes

            if len(x) > args.seq_len:
                print(f"Warning: sample exceeded seq_len {args.seq_len} ({len(x)} tokens), skipping.")
                continue

            sample = {
                "x": torch.tensor(x, dtype=torch.long),
                "y": torch.tensor(y, dtype=torch.long),
            }

            if split == "val":
                val_samples.append(sample)
            else:
                train_samples.append(sample)

    print(f"Encoded samples: Train={len(train_samples):,}, Val={len(val_samples):,}")

    torch.save(train_samples, args.out_dir / "train.pt")
    torch.save(val_samples, args.out_dir / "val.pt")
    print(f"✓ Saved pre-encoded dataset to {args.out_dir}")


if __name__ == "__main__":
    main()
