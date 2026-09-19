---
name: record-benchmark
description: Record on-device LLM benchmark test results from an active or recent run and compare throughput, latency, and memory against baseline and historical runs.
---

# Record & Compare Benchmark Runs (`record-benchmark`)

When the user asks to record benchmark results from an on-device run, compare current performance against previous runs or the baseline, or evaluate the impact of architectural changes (such as expanding vocabulary, enabling SIMD, or tuning sampling parameters), use this skill.

## Capabilities

1. **Telemetry & Metric Extraction**: Parses on-device bootloader logs (model dimensions, layer count, vocabulary size, staged INT8 tensors, free SRAM, and free PSRAM) and computes throughput (`tok/s`) and per-token latency (`ms/tok`).
2. **Historical Comparison**: Discovers all recorded runs in the project's `runs/` directory and formats aligned comparison tables showing speedup multipliers and percentage changes relative to the baseline.
3. **Run Persistence**: Records the latest benchmark output to `runs/<name>.json` and maintains `runs/latest.json`.
4. **Live Execution Mode**: Can trigger a live hardware test via the `test-device` skill (`--run`), ingest the resulting JSON, and immediately compare it against history.
5. **Machine-Readable JSON**: Exports structured JSON summaries for automated reporting and CI verification.

---

## Usage

### 1. Record Recent Test and Compare Against History

If you already ran `task test-device` or `test_device.py`:

```bash
uv run python .agents/skills/record-benchmark/scripts/record_benchmark.py --name expanded_vocab
```

### 2. Run Live Hardware Test and Record in One Step

Triggers a device hardware reset, runs benchmark questions, records the run, and displays the comparative table:

```bash
uv run python .agents/skills/record-benchmark/scripts/record_benchmark.py --run --name simd_opt_run
```

### 3. Compare from an Existing JSON File

```bash
uv run python .agents/skills/record-benchmark/scripts/record_benchmark.py \
  --input projects/s3-sourdough/runs/latest.json \
  --name vocab_expansion_test
```

### 4. Machine-Readable JSON Export

```bash
uv run python .agents/skills/record-benchmark/scripts/record_benchmark.py --json
```

### 5. Using Custom Baseline

By default, the skill looks for `baseline.json` in `runs/`. To compare against another historical reference:

```bash
uv run python .agents/skills/record-benchmark/scripts/record_benchmark.py --baseline 6layer_fullhead
```

---

## Output Metrics & Telemetry

| Metric | Source | Description |
| :--- | :--- | :--- |
| **Throughput (`tok/s`)** | Serial inference timer | Average generation speed across all benchmark prompts |
| **Latency (`ms/tok`)** | Inverted throughput | Time elapsed to compute and sample a single token |
| **Free PSRAM (`MB`)** | Bootloader heap caps | Octal PSRAM available after staging weights and allocating KV cache |
| **Free SRAM (`KB`)** | Bootloader heap caps | Internal fast memory available after activation buffers |
| **vs Baseline** | Computed ratio | Throughput multiplier and percent change ($X.XX\times \pm Y\%$) |
