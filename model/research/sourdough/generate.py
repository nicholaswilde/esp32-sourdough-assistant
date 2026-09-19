#!/usr/bin/env python3
"""Generate curated and expanded Q&A dataset for sourdough bread baking.

Supports:
  - Realistic prompt variations and domain-specific conversational prefixes
  - Controlled conversational noise (typos, casing, contraction drops, punctuation)
  - Multiple paraphrased answers per topic for varied, natural completions
  - Leak-free train / val split (validation holds out unseen question phrasings per topic)
  - Topic expansion across all 6 core domains

Outputs:
  - data/sourdough/raw/sourdough_qa.jsonl (tagged with "split": "train" | "val")
  - data/sourdough/raw/sourdough_corpus.txt (formatted for language model pretraining / BPE tokenizer)
"""

import argparse
import json
import random
from pathlib import Path
from typing import List, Dict, Tuple

from research.sourdough.knowledge import QA_ENTRIES, CATEGORIES

PROJECT_ROOT = Path(__file__).resolve().parents[2]
OUTPUT_DIR = PROJECT_ROOT / "data" / "sourdough" / "raw"

# Category-aware contextual openers and conversational framing
CATEGORY_PREFIXES: Dict[str, List[str]] = {
    "general": [
        "",
        "",
        "",
        "Hi, ",
        "Hello, ",
        "Hey baker, ",
        "Quick question: ",
        "I have a problem: ",
        "Can you help me? ",
        "Help! ",
        "Beginner question: ",
        "Need advice: ",
        "Wondering: ",
        "Hey, ",
        "Sourdough question: ",
        "Troubleshooting question: ",
        "Hey, quick sourdough question: ",
        "Need sourdough advice: ",
        "Troubleshooting my bake: ",
        "First time baker here, ",
    ],
    "starter_health": [
        "My starter is 2 weeks old, ",
        "Feeding 1:1:1 daily at 72F, ",
        "I keep my starter in the fridge, ",
        "After feeding my starter yesterday, ",
        "Starter troubleshooting: ",
        "My sourdough culture smells strange: ",
        "Checked my starter this morning: ",
        "Feeding 1:5:5 with unbleached flour: ",
    ],
    "bulk_fermentation": [
        "My kitchen is at 70F, ",
        "After 4 hours of bulk fermentation, ",
        "Dough has been rising all afternoon, ",
        "During bulk fermentation: ",
        "Checking dough at 78F: ",
        "Fermentation question: ",
        "Doing my BF at 68F, ",
        "My kitchen RT is 65F, ",
        "Aiming for 78F FDT, ",
        "After 4 sets of S&F, ",
        "My BF has been going for 6 hrs, ",
        "Checking dough during bulk: ",
        "Winter baking in cold kitchen: ",
        "Summer BF at 85F: ",
    ],
    "hydration_shaping": [
        "Using 75% hydration dough, ",
        "Working with sticky high-hydration dough, ",
        "Before shaping my loaves, ",
        "Using bread flour and whole wheat, ",
        "While shaping my batard: ",
        "Dough handling question: ",
        "Using 80% AP and 20% WW, ",
        "Mixing AP flour instead of bread flour, ",
        "Handling high hydration WW dough, ",
        "Doing coil folds every 45 min, ",
        "Working with rye and spelt blend, ",
        "Handling sticky rye dough: ",
    ],
    "scoring_baking": [
        "Baking in a cast iron Dutch oven, ",
        "Preheated oven to 450F, ",
        "After 20 minutes covered bake, ",
        "Open baking with steam tray, ",
        "Baking question: ",
        "Checking crust doneness: ",
        "Baking in a cast iron DO with ice cubes, ",
        "Baking on a baking steel at 475F, ",
        "Open baking with lava rocks, ",
        "Pulled the DO lid off after 20 mins, ",
        "Using a Pullman pan for sandwich bread, ",
        "Baking without a Dutch oven, ",
    ],
    "bakers_math": [
        "Formulating a recipe: ",
        "Doing baker's math: ",
        "Scaling for two loaves: ",
        "Calculating percentages: ",
        "Recipe math question: ",
        "Calculating baker's percentages for 2 loaves: ",
        "Doing baker's math with 15% levain: ",
        "Adjusting hydration formula: ",
    ],
    "guardrails": [
        "",
        "Hey, ",
        "Can you answer this? ",
        "Quick question: ",
    ],
}

PROMPT_SUFFIXES = [
    " Thanks!",
    " Any advice?",
    " What should I do?",
    " Any tips?",
    " What went wrong?",
    " Please advise.",
]

COMMON_TYPOS = {
    "sourdough": ["sourduogh", "sourdoh", "sourdoug"],
    "starter": ["starer", "startr"],
    "hydration": ["hydraton", "hydraition"],
    "banneton": ["banniton", "baneton"],
    "fermentation": ["fermentaion", "fermentaton"],
    "temperature": ["temp", "temperatue"],
    "refrigerator": ["fridge", "refridgerator"],
    "flour": ["flouer"],
    "proofing": ["profing", "prooving"],
    "autolyse": ["autolyze", "autolyse"],
    "boule": ["boole"],
    "batard": ["batarde"],
}

CASUAL_CONTRACTIONS = [
    ("didn't", "didnt"),
    ("won't", "wont"),
    ("don't", "dont"),
    ("it's", "its"),
    ("what's", "whats"),
    ("doesn't", "doesnt"),
    ("couldn't", "couldnt"),
    ("haven't", "havent"),
    ("can't", "cant"),
]

# Baking abbreviations frequently used in colloquial baking forums and queries
BAKING_ABBREVIATIONS = [
    ("bulk fermentation", "BF"),
    ("Bulk fermentation", "BF"),
    ("final dough temperature", "FDT"),
    ("desired dough temperature", "DDT"),
    ("all-purpose flour", "AP flour"),
    ("all-purpose", "AP"),
    ("whole wheat flour", "WW flour"),
    ("whole wheat", "WW"),
    ("Dutch oven", "DO"),
    ("dutch oven", "DO"),
    ("stretch and folds", "S&F"),
    ("stretch and fold", "S&F"),
    ("coil folds", "CF"),
    ("room temperature", "RT"),
]


def inject_noise(text: str, rng: random.Random) -> str:
    """Inject controlled conversational noise (casing, punctuation, apostrophes, abbreviations, rare typos)."""
    # 1. Punctuation and casing noise
    rand_style = rng.random()
    if rand_style < 0.25:
        text = text.lower()
    elif rand_style < 0.40 and text.endswith("?"):
        text = text[:-1]
    elif rand_style < 0.45 and text.endswith("?"):
        text = text + "??"

    # 2. Omit informal apostrophes (casual smartphone typing, 20% chance)
    if rng.random() < 0.20:
        for formal, casual in CASUAL_CONTRACTIONS:
            text = text.replace(formal, casual).replace(formal.capitalize(), casual.capitalize())

    # 3. Colloquial baking abbreviation replacement (15% chance)
    if rng.random() < 0.15:
        for formal, abbr in BAKING_ABBREVIATIONS:
            if formal in text:
                text = text.replace(formal, abbr)
                break

    # 4. Controlled realistic typo (5% probability, strictly on common domain keywords)
    if rng.random() < 0.05:
        words = text.split()
        for i, w in enumerate(words):
            clean_w = w.lower().strip("?,.!")
            if clean_w in COMMON_TYPOS:
                typo = rng.choice(COMMON_TYPOS[clean_w])
                if w and w[0].isupper():
                    typo = typo.capitalize()
                punct = "".join(c for c in w if c in "?,.!")
                words[i] = typo + punct
                break
        text = " ".join(words)

    return text


def get_prefix(category: str, rng: random.Random) -> str:
    """Select appropriate prefix based on category context."""
    roll = rng.random()
    if roll < 0.30:
        return ""
    elif roll < 0.70:
        return rng.choice(CATEGORY_PREFIXES.get("general", [""]))
    else:
        return rng.choice(CATEGORY_PREFIXES.get(category, [""]))


def get_suffix(rng: random.Random) -> str:
    """Select optional casual sign-off (20% frequency)."""
    if rng.random() < 0.20:
        return rng.choice(PROMPT_SUFFIXES)
    return ""


def format_prompt(base_q: str, category: str, rng: random.Random) -> str:
    """Compose full realistic prompt with prefix, suffix, and noise injection."""
    q = base_q.strip()
    prefix = get_prefix(category, rng)
    suffix = get_suffix(rng)

    if prefix:
        if prefix.endswith(": ") or prefix.endswith("? ") or prefix.endswith(", ") or prefix.endswith("! "):
            q = prefix + q[0].upper() + q[1:]
        else:
            q = prefix + q

    if suffix:
        if q.endswith("?"):
            q = q[:-1] + suffix
        else:
            q = q + suffix

    return inject_noise(q, rng)


def expand_dataset(
    entries: List[Dict],
    target_samples: int = 5000,
    val_ratio: float = 0.10,
    guardrail_ratio: float = 0.08,
    seed: int = 42,
) -> Tuple[List[Dict], List[Dict]]:
    """Expand seed QA pairs with realistic variations and leak-free train/val separation."""
    rng = random.Random(seed)

    target_val = int(target_samples * val_ratio)
    target_train = target_samples - target_val

    # Partition each topic's questions into train and val pools
    topic_pools = []
    for entry in entries:
        qs = entry["questions"]
        answers = entry.get("answers", [entry.get("answer", "")])

        # Hold out at least 1 question for validation (approx 20-25%)
        val_count = max(1, round(len(qs) * 0.2))
        val_qs = qs[-val_count:]
        train_qs = qs[:-val_count] if len(qs) > val_count else qs

        # If multiple answers, reserve alternate answer for validation
        if len(answers) >= 2:
            train_ans = answers[:-1]
            val_ans = answers[-1:]
        else:
            train_ans = answers
            val_ans = answers

        topic_pools.append({
            "category": entry["category"],
            "train_qs": train_qs,
            "train_ans": train_ans,
            "val_qs": val_qs,
            "val_ans": val_ans,
        })

    baking_pools = [t for t in topic_pools if t["category"] != "guardrails"]
    guardrail_pools = [t for t in topic_pools if t["category"] == "guardrails"]

    # 1. Build Validation Split (strictly from val_qs)
    val_dataset = []
    # Include all canonical held-out validation questions first
    for topic in topic_pools:
        for q in topic["val_qs"]:
            val_dataset.append({
                "prompt": q,
                "completion": rng.choice(topic["val_ans"]),
                "category": topic["category"],
                "split": "val",
            })

    target_val_guardrails = int(target_val * guardrail_ratio)
    val_guardrail_count = sum(1 for d in val_dataset if d["category"] == "guardrails")

    # Expand validation to target_val
    while len(val_dataset) < target_val:
        if val_guardrail_count < target_val_guardrails and guardrail_pools:
            topic = rng.choice(guardrail_pools)
            val_guardrail_count += 1
        else:
            topic = rng.choice(baking_pools)

        base_q = rng.choice(topic["val_qs"])
        q_variant = format_prompt(base_q, topic["category"], rng)
        val_dataset.append({
            "prompt": q_variant,
            "completion": rng.choice(topic["val_ans"]),
            "category": topic["category"],
            "split": "val",
        })

    # 2. Build Training Split (strictly from train_qs)
    train_dataset = []
    # Include all canonical train questions first
    for topic in topic_pools:
        for q in topic["train_qs"]:
            train_dataset.append({
                "prompt": q,
                "completion": rng.choice(topic["train_ans"]),
                "category": topic["category"],
                "split": "train",
            })

    target_train_guardrails = int(target_train * guardrail_ratio)
    train_guardrail_count = sum(1 for d in train_dataset if d["category"] == "guardrails")

    # Expand training to target_train
    while len(train_dataset) < target_train:
        if train_guardrail_count < target_train_guardrails and guardrail_pools:
            topic = rng.choice(guardrail_pools)
            train_guardrail_count += 1
        else:
            topic = rng.choice(baking_pools)

        base_q = rng.choice(topic["train_qs"])
        q_variant = format_prompt(base_q, topic["category"], rng)
        train_dataset.append({
            "prompt": q_variant,
            "completion": rng.choice(topic["train_ans"]),
            "category": topic["category"],
            "split": "train",
        })

    rng.shuffle(train_dataset)
    rng.shuffle(val_dataset)

    # Verify zero prompt leakage between train and val
    train_prompts = {item["prompt"].strip().lower() for item in train_dataset}
    val_prompts = {item["prompt"].strip().lower() for item in val_dataset}
    overlap = train_prompts.intersection(val_prompts)
    if overlap:
        raise ValueError(f"Data leakage detected! {len(overlap)} overlapping prompts between train and val.")

    return train_dataset, val_dataset


def main():
    parser = argparse.ArgumentParser(description="Generate Sourdough Q&A dataset.")
    parser.add_argument(
        "--samples",
        type=int,
        default=5000,
        help="Target number of Q&A samples to generate (default: 5000)",
    )
    parser.add_argument(
        "--val-ratio",
        type=float,
        default=0.10,
        help="Fraction of samples reserved for validation (default: 0.10)",
    )
    parser.add_argument(
        "--guardrail-ratio",
        type=float,
        default=0.08,
        help="Target fraction of samples allocated to guardrail refusals (default: 0.08)",
    )
    parser.add_argument(
        "--seed",
        type=int,
        default=42,
        help="Random seed for repeatable expansion (default: 42)",
    )

    args = parser.parse_args()

    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    jsonl_path = OUTPUT_DIR / "sourdough_qa.jsonl"
    txt_path = OUTPUT_DIR / "sourdough_corpus.txt"

    print(f"Expanding seed QA pairs ({len(QA_ENTRIES)} topics) to ~{args.samples} samples (guardrail ratio: {args.guardrail_ratio:.1%})...")
    train_set, val_set = expand_dataset(
        QA_ENTRIES,
        target_samples=args.samples,
        val_ratio=args.val_ratio,
        guardrail_ratio=args.guardrail_ratio,
        seed=args.seed,
    )
    all_samples = train_set + val_set

    # Write JSONL
    with open(jsonl_path, "w", encoding="utf-8") as f:
        for item in all_samples:
            f.write(json.dumps(item) + "\n")

    # Write plaintext pretraining / tuning corpus
    total_words = 0
    with open(txt_path, "w", encoding="utf-8") as f:
        for item in all_samples:
            block = f"<|endoftext|>User: {item['prompt']}\nAssistant: {item['completion']}<|endoftext|>\n"
            f.write(block)
            total_words += len(block.split())

    file_size_kb = txt_path.stat().st_size / 1024
    print(f"\n✓ Generated {len(all_samples):,} Q&A pairs (Train: {len(train_set):,}, Val: {len(val_set):,}):")
    print(f"  JSONL dataset:  {jsonl_path}")
    print(f"  Text corpus:    {txt_path} ({file_size_kb:.1f} KB, ~{total_words:,} words)")

    # Category breakdown
    print("\nCategory distribution:")
    counts = {}
    for item in all_samples:
        counts[item["category"]] = counts.get(item["category"], 0) + 1
    for cat in CATEGORIES:
        pct = (counts.get(cat, 0) / len(all_samples)) * 100
        print(f"  - {cat:<22}: {counts.get(cat, 0):4d} samples ({pct:4.1f}%)")


if __name__ == "__main__":
    main()
