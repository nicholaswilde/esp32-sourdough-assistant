#!/usr/bin/env python3
"""Interactive inference / sampling for trained Sourdough micro-LLM."""

import argparse
from pathlib import Path

import torch
from tokenizers import Tokenizer

from research.model import Config, make_model

PROJECT_ROOT = Path(__file__).resolve().parents[2]
RUNS_DIR = PROJECT_ROOT / "runs" / "sourdough"
DATA_ROOT = PROJECT_ROOT / "data" / "sourdough"


def get_device():
    if torch.cuda.is_available():
        return "cuda"
    if torch.backends.mps.is_available():
        return "mps"
    return "cpu"


import json

def generate_response(
    model,
    tokenizer,
    prompt: str,
    max_new_tokens: int = 60,
    temperature: float = 0.7,
    top_p: float = 0.9,
    out2in: list[int] | None = None,
    words: list[str] | None = None,
):
    model.eval()
    device = next(model.parameters()).device

    formatted_input = f"<|endoftext|>User: {prompt.strip()}\nAssistant:"
    input_ids = tokenizer.encode(formatted_input).ids
    x = torch.tensor([input_ids], dtype=torch.long, device=device)

    is_asym = out2in is not None and words is not None
    eot_id = tokenizer.token_to_id("<|endoftext|>")

    generated_words = []
    with torch.no_grad():
        for _ in range(max_new_tokens):
            idx_cond = x if x.size(1) <= model.cfg.seq_len else x[:, -model.cfg.seq_len:]
            logits, _ = model(idx_cond)
            logits = logits[:, -1, :] / max(temperature, 1e-5)

            # Top-p (nucleus) filtering
            if top_p < 1.0:
                sorted_logits, sorted_indices = torch.sort(logits, descending=True)
                cumulative_probs = torch.cumsum(torch.softmax(sorted_logits, dim=-1), dim=-1)
                sorted_indices_to_remove = cumulative_probs > top_p
                sorted_indices_to_remove[..., 1:] = sorted_indices_to_remove[..., :-1].clone()
                sorted_indices_to_remove[..., 0] = 0
                indices_to_remove = sorted_indices_to_remove.scatter(1, sorted_indices, sorted_indices_to_remove)
                logits[indices_to_remove] = -float("Inf")

            probs = torch.softmax(logits, dim=-1)
            next_sample = torch.multinomial(probs, num_samples=1)

            if is_asym:
                cls_idx = next_sample.item()
                if cls_idx >= len(words):
                    break
                w = words[cls_idx]
                if w in ("<|endoftext|>", "<eos>", "<pad>"):
                    break
                # Spacing logic similar to firmware emit_word
                punct = len(w) == 1 and w in ".,:;?%"
                if generated_words and not punct:
                    generated_words.append(" ")
                generated_words.append(w)

                in_tok = out2in[cls_idx]
                next_id = torch.tensor([[in_tok]], dtype=torch.long, device=device)
            else:
                next_id = next_sample
                if next_id.item() == eot_id:
                    break

            x = torch.cat((x, next_id), dim=1)

    if is_asym:
        return "".join(generated_words)
    else:
        generated_tokens = x[0].tolist()[len(input_ids):]
        return tokenizer.decode(generated_tokens)


def main():
    parser = argparse.ArgumentParser(description="Query the sourdough baking model.")
    parser.add_argument("prompt", type=str, nargs="?", default="Why is my bread gummy inside?", help="User baking question")
    parser.add_argument("--ckpt", type=str, default=None, help="Path to checkpoint .pt file")
    parser.add_argument("--temp", type=float, default=0.7, help="Sampling temperature")
    args = parser.parse_args()

    ckpt_path = Path(args.ckpt) if args.ckpt else sorted(list(RUNS_DIR.glob("*.pt")))[-1] if list(RUNS_DIR.glob("*.pt")) else None
    if not ckpt_path or not ckpt_path.exists():
        raise SystemExit("No trained checkpoints found in runs/sourdough/. Run 'task sourdough:train' first.")

    print(f"Loading checkpoint: {ckpt_path.name}")
    checkpoint = torch.load(ckpt_path, map_location="cpu")
    cfg = Config(**checkpoint["cfg"])
    vocab = checkpoint.get("vocab", 2048)
    arm = checkpoint.get("arm", "ple")
    is_asym = checkpoint.get("asymmetric", False) or (cfg.out_vocab_size is not None and cfg.out_vocab_size != cfg.vocab_size)

    out2in = None
    words = None
    if is_asym:
        tok_path = DATA_ROOT / "tokenizer.json"
        layout_path = DATA_ROOT / "layout.json"
        vocab_path = DATA_ROOT / "vocab.json"
        with open(layout_path, "r", encoding="utf-8") as f:
            out2in = json.load(f)["out2in"]
        with open(vocab_path, "r", encoding="utf-8") as f:
            words = [t["token"] for t in json.load(f)["tokens"]]
    else:
        tok_path = DATA_ROOT / f"vocab-{vocab}" / "tokenizer.json"

    tokenizer = Tokenizer.from_file(str(tok_path))

    device = get_device()
    from research.model import TinyLM
    model = TinyLM(cfg).to(device)
    model.load_state_dict(checkpoint["state"])

    print(f"\nUser: {args.prompt}")
    answer = generate_response(
        model, tokenizer, args.prompt, temperature=args.temp, out2in=out2in, words=words
    )
    print(f"Assistant: {answer}\n")


if __name__ == "__main__":
    main()
