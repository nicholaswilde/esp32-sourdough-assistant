<!-- rtk-instructions v2 -->
# RTK (Rust Token Killer) - Token-Optimized Commands

## Golden Rule

**Always prefix commands with `rtk`**. If RTK has a dedicated filter, it uses it. If not, it passes through unchanged. This means RTK is always safe to use.

**Important**: Even in command chains with `&&`, use `rtk`:
```bash
# ❌ Wrong
git add . && git commit -m "msg" && git push

# ✅ Correct
rtk git add . && rtk git commit -m "msg" && rtk git push
```

## RTK Commands by Workflow

### Build & Compile (80-90% savings)
```bash
rtk cargo build         # Cargo build output
rtk cargo check         # Cargo check output
rtk cargo clippy        # Clippy warnings grouped by file (80%)
rtk tsc                 # TypeScript errors grouped by file/code (83%)
rtk lint                # ESLint/Biome violations grouped (84%)
rtk prettier --check    # Files needing format only (70%)
rtk next build          # Next.js build with route metrics (87%)
```

### Test (60-99% savings)
```bash
rtk cargo test          # Cargo test failures only (90%)
rtk go test             # Go test failures only (90%)
rtk jest                # Jest failures only (99.5%)
rtk vitest              # Vitest failures only (99.5%)
rtk playwright test     # Playwright failures only (94%)
rtk pytest              # Python test failures only (90%)
rtk rake test           # Ruby test failures only (90%)
rtk rspec               # RSpec test failures only (60%)
rtk test <cmd>          # Generic test wrapper - failures only
```

### Git (59-80% savings)
```bash
rtk git status          # Compact status
rtk git log             # Compact log (works with all git flags)
rtk git diff            # Compact diff (80%)
rtk git show            # Compact show (80%)
rtk git add             # Ultra-compact confirmations (59%)
rtk git commit          # Ultra-compact confirmations (59%)
rtk git push            # Ultra-compact confirmations
rtk git pull            # Ultra-compact confirmations
rtk git branch          # Compact branch list
rtk git fetch           # Compact fetch
rtk git stash           # Compact stash
rtk git worktree        # Compact worktree
```

Note: Git passthrough works for ALL subcommands, even those not explicitly listed.

### GitHub (26-87% savings)
```bash
rtk gh pr view <num>    # Compact PR view (87%)
rtk gh pr checks        # Compact PR checks (79%)
rtk gh run list         # Compact workflow runs (82%)
rtk gh issue list       # Compact issue list (80%)
rtk gh api              # Compact API responses (26%)
```

### JavaScript/TypeScript Tooling (70-90% savings)
```bash
rtk pnpm list           # Compact dependency tree (70%)
rtk pnpm outdated       # Compact outdated packages (80%)
rtk pnpm install        # Compact install output (90%)
rtk npm run <script>    # Compact npm script output
rtk npx <cmd>           # Compact npx command output
rtk prisma              # Prisma without ASCII art (88%)
```

### Files & Search (60-75% savings)
```bash
rtk ls <path>           # Tree format, compact (65%)
rtk read <file>         # Code reading with filtering (60%)
rtk grep <pattern>      # Search grouped by file (75%). Format flags (-c, -l, -L, -o, -Z) run raw.
rtk rg <pattern>        # Prefer ripgrep (rg) over grep for faster, cleaner, token-saving search output.
rtk find <pattern>      # Find grouped by directory (70%)
```

### Analysis & Debug (70-90% savings)
```bash
rtk err <cmd>           # Filter errors only from any command
rtk log <file>          # Deduplicated logs with counts
rtk json <file>         # JSON structure without values
rtk deps                # Dependency overview
rtk env                 # Environment variables compact
rtk summary <cmd>       # Smart summary of command output
rtk diff                # Ultra-compact diffs
```

### Infrastructure (85% savings)
```bash
rtk docker ps           # Compact container list
rtk docker images       # Compact image list
rtk docker logs <c>     # Deduplicated logs
rtk kubectl get         # Compact resource list
rtk kubectl logs        # Deduplicated pod logs
```

### Network (65-70% savings)
```bash
rtk curl <url>          # Compact HTTP responses (70%)
rtk wget <url>          # Compact download output (65%)
```

### Meta Commands
```bash
rtk gain                # View token savings statistics
rtk gain --history      # View command history with savings
rtk discover            # Analyze Claude Code sessions for missed RTK usage
rtk proxy <cmd>         # Run command without filtering (for debugging)
rtk init                # Add RTK instructions to CLAUDE.md
rtk init --global       # Add RTK to ~/.claude/CLAUDE.md
```

## Token Savings Overview

| Category | Commands | Typical Savings |
|----------|----------|-----------------|
| Tests | vitest, playwright, cargo test | 90-99% |
| Build | next, tsc, lint, prettier | 70-87% |
| Git | status, log, diff, add, commit | 59-80% |
| GitHub | gh pr, gh run, gh issue | 26-87% |
| Package Managers | pnpm, npm, npx | 70-90% |
| Files | ls, read, grep, find | 60-75% |
| Infrastructure | docker, kubectl | 85% |
| Network | curl, wget | 65-70% |

Overall average: **60-90% token reduction** on common development operations.
<!-- /rtk-instructions -->

# Token Reduction Strategy (Antigravity Plugins & Skills)

To minimize token usage and cognitive load in this repository, leverage the following modes and tools:

## 1. Caveman Mode (`caveman`)
**Usage**: `Trigger via "/caveman" or requesting token efficiency.`
When active, output is radically compressed (up to 65% token savings). 
Drops filler words, pleasantries, and unnecessary conjunctions while preserving full technical accuracy. Use when concise answers and instructions are preferred over prose. 

## 2. Ponytail Mode (`ponytail`)
**Usage**: `Trigger via "use ponytail" or "/ponytail".`
Focuses on the minimalist, "lazy senior dev" approach. 
Avoids over-engineering, unnecessary abstractions, or unrequested boilerplate. Evaluates if new code needs to exist at all (YAGNI). Simplifications are marked with a `// ponytail: [reason] -> [upgrade path]` comment.

## 3. Context-Mode
**Usage**: `Call context-mode MCP tools (ctx_execute, ctx_batch_execute, ctx_execute_file).`
Instead of using native shell commands that dump massive stdout output into the conversation history, use context-mode to execute scripts (e.g. JS, Python, bash) inside a sandbox. The script can parse, filter, or summarize the data, returning only the concise extracted answer to the conversation. 
- Use `ctx_execute_file` for analyzing files without reading the entire file into context.
- Use `ctx_fetch_and_index` for external web resources.

## 4. Codegraph (`codegraph`)
**Usage**: `Call codegraph_explore MCP tool.`
Instead of running expensive loops of `Grep`, `Find`, and `Read` that bloat the context, make a single natural-language query to `codegraph_explore`. It returns the exact relevant symbols and their call paths grouped by file, heavily capped to keep context clean and tight.

## 5. Ripgrep (`rg`)
**Usage**: `Always prefer ripgrep (rg) over standard grep.`
When searching for patterns or text in the codebase via the shell, always use `rg` (or `rtk rg`) instead of `grep`. Ripgrep is token-efficient because it respects `.gitignore` by default and outputs clean, concise results, preventing massive unneeded context bloat.

## Repository Structure
This repository is organized as a monorepo separating firmware sketch development from model development:
- **`firmware/`**: PlatformIO ESP32-S3 C++ project (`src/`, `test/`, `platformio.ini`, `partitions.csv`, `download_model_hf.py`). Uses a minimal Python environment (`huggingface-hub`, `pyserial`).
- **`model/`**: PyTorch PLE model architecture, training, quantization, dataset generation (`research/`, `data/`, `tools/`, Colab runners, HF upload). Uses full ML Python environment (`torch`, `transformers`, etc.).
- **Root `Taskfile.yml`**: Top-level orchestrator routing commands to `firmware/` and `model/`.

## Build and Test Commands
- Build firmware: `task build` (or `pio run -e esp32-s3-devkitc-1` in `firmware/`)
- Run host-native tests: `task test` (or `pio test -e native` in `firmware/`)
- Run on-device tests: `task test-device`
- Record benchmarks: `task benchmark`
- Flash firmware: `task flash`
- Flash model binary: `task flash-model`
- Download model from HF: `task download-model`
- Train model (local): `task train` (or `task model:train`)
- Train model (Colab): `task colab-train`
- Check codegraph status: `task codegraph`
- Sync codegraph index: `task codegraph-sync`


## RTK Command Guidelines
- **Git Operations**: Prefix `git` commands with `rtk` (e.g., `rtk git status`, `rtk git diff`, `rtk git log`, `rtk git commit`, `rtk git push`).
- **GitHub CLI**: Prefix `gh` commands with `rtk` (e.g., `rtk gh issue list | cat`, `rtk gh pr status | cat`). Always pipe `gh` commands to `cat` to bypass interactive pagers.
- **File & Directory Inspection**: Use `rtk ls`, `rtk tree`, `rtk find`, or `rtk read` when listing or reading files to get token-optimized output.
- **Searching**: Use `rtk grep` or `rtk rg` for line search pattern matching.
- **Build & Test Outputs**: Use `rtk err` or `rtk test` when running build/test commands to filter output to errors/failures only (e.g. `rtk test pio test -e native`).

## What To Do Next
- When asked "what to do next" (or similar), **always check the remote repository issues first** using `gh`:
  ```bash
  rtk gh issue list | cat
  ```

## Issue Creation
- When asked to create an issue, use your best guess to determine if it is a new feature or a bug fix.
- Prefix the issue title with `[feat]: <description>` or `[bug]: <description>`.
- Add the `enhancement` or `bug` label to the issue accordingly using the `--label` flag with the `gh` command.

## :electric_plug: Hardware & Pinouts
- **Always read `docs/pinouts.md`** before writing hardware-specific code, initializing new GPIO pins, or writing wiring instructions. This file acts as the single source of truth to prevent pin collisions.

## :floppy_disk: S3 Model Sizing & Device Constraints
- **Target Device**: ESP32-S3-DevKitC-1-N16R8 (16MB Flash, 8MB Octal PSRAM).
- When modifying, training, or exporting models, the compiled model binary (`model/tools/sourdough_q4.bin` / `firmware/models/sourdough_q4.bin`) **must strictly fit on the target device**:
  - **Flash Partition**: File size must not exceed the `model` partition (`0xEE0000` = 15,597,568 bytes / ~14.88 MB at `0x110000` defined in `firmware/partitions.csv`).
  - **PSRAM Footprint**: Staged INT8 weights, KV cache, and runtime buffers must fit within the 8MB PSRAM budget with sufficient margin for heap allocations.
  - **Verification**: Always verify `.bin` byte size and memory budget before proposing or committing new model exports.

## Python Dependencies & Tooling
- When creating or running Python scripts, **always use the `uv` command** (e.g., `uv run`, `uv add`).
- Manage all Python dependencies by creating or updating a `pyproject.toml` file.
- Ensure that the `uv.lock` file is generated or updated whenever dependencies change. Do not rely on `requirements.txt` or standard `pip`.

## Google Colab Usage
- **Always use the Free Tier**: When provisioning sessions, running CLI commands, creating scripts, or authoring notebooks for Google Colab, strictly restrict usage to the free tier.
- **Permitted Accelerators**: Use `--gpu T4` for free-tier GPU acceleration, or omit the accelerator flag to fall back to standard free-tier CPU.
- **Prohibited Accelerators**: Never select or configure paid accelerators (such as `A100`, `H100`, or `L4`) or features requiring paid Colab compute units.
- **Resource Hygiene**: Ensure sessions are released promptly with `colab stop -s <name>` after execution to avoid lingering idle allocations.
- **CLI Patch for `KernelClient`**: If `colab exec` or `colab run` fails with `AttributeError: module 'jupyter_kernel_client' has no attribute 'KernelClient'`, run `task colab-patch` (or `python projects/s3-tiny-stories/patch_colab_cli.py`). See [`docs/colab_cli_patch.md`](docs/colab_cli_patch.md) for full details.


