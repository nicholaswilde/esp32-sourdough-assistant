# ESP32-S3 Sourdough Baker Assistant - Model Development & Training

This directory contains the machine learning pipeline, dataset generator, training loops, quantization tools, Google Colab runners, and Hugging Face release automation for the Sourdough Baker Micro-LLM.

---

## 📁 Directory Layout

```
model/
├── pyproject.toml         # ML dependencies (torch, numpy, tokenizers, etc.)
├── uv.lock                # Locked Python environment
├── Taskfile.yml           # Model development tasks
├── colab_runner.py        # Free-tier Google Colab session runner
├── colab_remote_task.py   # Training task script executed inside Colab VM
├── upload_model_hf.py     # Hugging Face Hub release publisher
├── data/                  # Dataset corpus, vocabulary, and layout configs
│   └── sourdough/         # Raw JSONL, asymmetric splits, tokenizer
├── research/              # PyTorch model architecture & training scripts
│   ├── model.py           # Per-Layer Embeddings (PLE) transformer architecture
│   ├── quantize.py        # INT4 symmetric group quantization
│   └── sourdough/         # Training scripts (generate, train, sample, verify)
├── tools/                 # Export, quantization, and C header generation
│   ├── export_model.py    # Pack PyTorch weights into INT4 binary format
│   ├── generate_vocab.py  # C header for vocabulary decoding
│   ├── generate_vocab_headers.py # C headers for class-to-word & out2in mapping
│   ├── generate_subvocab.py      # Sub-vocab cluster centroid generation
│   ├── generate_tokenizer_asset.py # BTK1 tokenizer binary asset header
│   └── sourdough_q4.bin   # Latest quantized INT4 model binary
└── runs/                  # PyTorch model checkpoints (.pt)
```

---

## 🚀 Training & Export Workflow

All tasks can be executed inside this directory using `task <name>` or from the repository root via `task model:<name>`.

### 1. Dataset Generation & Tokenization
Generate the 5,000+ domain Q&A dataset and build vocabulary & layout:
```bash
task generate
task vocab
task layout
task prepare
```

Verify dataset token lengths and splits:
```bash
task validate-dataset
```

### 2. Local Training
Train the Sourdough PLE micro-LLM locally:
```bash
task train          # 3,000 steps
task train-full     # 5,000 steps
```

Sample predictions from a trained checkpoint:
```bash
task sample PROMPT="Why is my bread gummy?"
```

### 3. Google Colab Free-Tier Training
Train on a free-tier Colab GPU instance:
```bash
task colab-auth     # Verify Colab CLI credentials
task colab-start    # Start free-tier Colab VM (T4 GPU or CPU)
task colab-train    # Run training and fetch artifacts
task colab-stop     # Terminate Colab session
```

### 4. Quantize & Export
Pack the trained PyTorch checkpoint into the target INT4 binary format and update C firmware headers:
```bash
task quantize
task headers
```

### 5. Publish to Hugging Face Hub
Upload the model bundle (binary weights, tokenizer, metadata, model card) to Hugging Face:
```bash
task upload-model
# Or specify a target repository:
task upload-model REPO=nicholascwilde/esp32-s3-sourdough
```
