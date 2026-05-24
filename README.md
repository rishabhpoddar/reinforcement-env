# Web Design Replication RL Environments

A pipeline that generates RL environments for testing coding agents' ability to replicate multi-page web designs from screenshots. Uses the [Harbor framework](https://harborframework.com/) for task packaging and evaluation.

## How It Works

```
┌─────────────┐    ┌─────────────┐    ┌─────────────┐    ┌─────────────┐    ┌─────────────┐
│   1. SPEC   │───▶│  2. BUILD   │───▶│  3. JUDGE   │───▶│4. SCREENSHOT│───▶│ 5. PACKAGE  │
│             │    │             │    │             │    │             │    │             │
│ LLM generates│   │ OpenCode    │    │ OpenCode    │    │ Playwright  │    │ Harbor task │
│ website spec │   │ agent builds│    │ agents score│    │ captures    │    │ directory   │
│ from seed   │    │ HTML+CSS    │    │ 0-10 with   │    │ at 3        │    │ with grader │
│ examples    │    │ with        │    │ Playwright  │    │ viewports   │    │             │
│             │    │ Playwright  │    │ screenshots │    │             │    │             │
│             │    │ self-check  │    │             │    │             │    │             │
└─────────────┘    └──────┬──────┘    └──────┬──────┘    └─────────────┘    └─────────────┘
                          │                  │
                          │    ◀─────────────┘
                          │    feedback loop until
                          │    all judges give 10/10
                          └──────────────────────
```

**Build + Judge iterate** until all judges give a perfect 10/10, or max iterations are reached. Each judge is an OpenCode coding agent with Playwright — it reads the source code, takes screenshots at desktop/tablet/mobile viewports, and writes a verdict file with a score and actionable feedback.

## Setup

### Prerequisites

- Python 3.11+
- Node.js 20+
- [OpenCode](https://opencode.ai/) installed globally (`npm i -g opencode-ai`)

### Install

```bash
# Clone the repo
git clone <repo-url>
cd reinforcement-env

# Create Python virtualenv
python3 -m venv .venv
source .venv/bin/activate

# Install Python dependencies
pip install -r pipeline/requirements.txt

# Install Playwright browser
python -m playwright install chromium

# Create .env with your API keys
cat > .env << 'EOF'
ANTHROPIC_API_KEY=sk-ant-...
OPENAI_API_KEY=sk-...
EOF
```

### Verify Setup

```bash
# Check OpenCode works with your keys
source .venv/bin/activate
python -c "
from pipeline.agents.opencode_wrapper import OpenCodeAgent
import tempfile
agent = OpenCodeAgent(timeout_sec=30)
with tempfile.TemporaryDirectory() as d:
    r = agent.run('Create a file called test.txt with hello', 'anthropic/claude-opus-4-7', d)
    print(f'Success: {r.success}')
"
```

## Usage

### Full Pipeline

Generates website specs, builds them with coding agents, captures screenshots, and packages as Harbor tasks.

```bash
source .venv/bin/activate

# Generate 1 clean task
python -m pipeline.run_pipeline --count 1 --clean

# Generate 1 broken task (with intentional design defects)
python -m pipeline.run_pipeline --count 1 --broken

# Generate 10 tasks (3 broken, 7 clean)
python -m pipeline.run_pipeline --count 10 --broken-count 3

# Override models
python -m pipeline.run_pipeline --count 1 --clean --models anthropic/claude-opus-4-7

# Use cheaper/faster models
python -m pipeline.run_pipeline --count 1 --clean --models openai/gpt-5.4-mini

# Limit builder-judge iterations
python -m pipeline.run_pipeline --count 1 --clean --max-iterations 3
```

### Individual Steps

Run any step independently on an existing workspace.

#### 1. `spec` — Generate a website specification

Creates a new workspace in `generated/<slug>/` with a `spec.json` file.

```bash
# Generate a clean spec
python -m pipeline.run_pipeline --step spec --clean

# Generate a broken spec (with intentional defects)
python -m pipeline.run_pipeline --step spec --broken

# Use a specific model for spec generation
python -m pipeline.run_pipeline --step spec --clean --spec-model claude-opus-4-7
```

Output: `generated/<category>-<name>/spec.json`

#### 2. `build` — Build a website from a spec

Runs the builder+judge loop on an existing workspace. Reads `spec.json`, writes HTML+CSS to `site/`.

```bash
python -m pipeline.run_pipeline --step build generated/my-site/

# With specific models
python -m pipeline.run_pipeline --step build generated/my-site/ --models anthropic/claude-opus-4-7

# With multiple models (used for both building and judging)
python -m pipeline.run_pipeline --step build generated/my-site/ --models anthropic/claude-opus-4-7 openai/gpt-5.5

# Limit iterations
python -m pipeline.run_pipeline --step build generated/my-site/ --max-iterations 3
```

Requires: `spec.json` in workspace
Output: `site/*.html`, `site/styles.css`

#### 3. `judge` — Score an existing website

Runs judge agents on an already-built site. Each judge reads the source code, takes Playwright screenshots, and writes a verdict.

```bash
python -m pipeline.run_pipeline --step judge generated/my-site/

# With cheap model for quick checks
python -m pipeline.run_pipeline --step judge generated/my-site/ --models openai/gpt-5.4-mini

# Multiple judges
python -m pipeline.run_pipeline --step judge generated/my-site/ --models anthropic/claude-opus-4-7 openai/gpt-5.5
```

Requires: `spec.json` + `site/*.html` in workspace
Output: Prints scores and feedback to console + log file

#### 4. `screenshot` — Capture reference screenshots

Takes screenshots of each page at 3 viewport sizes using Playwright (Python, not the agent).

```bash
python -m pipeline.run_pipeline --step screenshot generated/my-site/
```

Requires: `site/*.html` in workspace
Output: `screenshots/*.png` (e.g., `home-desktop.png`, `home-tablet.png`, `home-mobile.png`)

Viewports:
| Name | Size | Represents |
|------|------|------------|
| Desktop | 1280x900 | Standard desktop |
| Tablet | 768x1024 | iPad portrait |
| Mobile | 375x812 | iPhone portrait |

#### 5. `package` — Create a Harbor task

Packages the generated site + screenshots into a Harbor-compatible task directory.

```bash
python -m pipeline.run_pipeline --step package generated/my-site/
```

Requires: `spec.json` + `site/*.html` + `screenshots/*.png` in workspace
Output: `tasks/web-design-<slug>/` with full Harbor task structure

#### 6. Run evaluations (via Modal)

Evaluations run entirely on [Modal](https://modal.com/) — the Harbor orchestrator, agent, and sandbox all run in the cloud. Your local machine only streams logs and downloads results.

See `remote_eval.py` for configuration and details.

**Setup (one-time):**
```bash
pip install modal
modal setup

# Create secrets in Modal
modal secret create anthropic-api-key ANTHROPIC_API_KEY=sk-ant-...
modal secret create openai-api-key OPENAI_API_KEY=sk-...
```

**Run:**
```bash
# Run all tasks (10 trials each, 2 concurrent per task)
modal run remote_eval.py
```

Results are automatically downloaded to `remote-jobs/` when the run completes. You can also browse logs in the [Modal dashboard](https://modal.com/apps).

**How it works:**
- `remote_eval.py` spins up one Modal machine per task (10 tasks = 10 machines in parallel)
- Each machine runs the Harbor orchestrator + claude-code agent
- Harbor spawns child Modal sandboxes for each trial environment
- With `EVAL_CONCURRENT=2`, each machine runs 2 trials at a time
- Configure `EVAL_TRIALS` and `EVAL_CONCURRENT` at the top of the script

### Full Pipeline Arguments Reference

| Argument | Default | Description |
|----------|---------|-------------|
| `--count N` | 1 | Number of tasks to generate |
| `--clean` | — | Force all tasks to be clean (no defects) |
| `--broken` | — | Force all tasks to have intentional defects |
| `--broken-count N` | auto (25%) | Exact number of broken tasks out of `--count` |
| `--models M [M...]` | `claude-opus-4-7 gpt-5.5` | LLM models for building and judging |
| `--max-iterations N` | 5 | Max builder-judge iterations per task |
| `--spec-model M` | `claude-opus-4-7` | Anthropic model for spec generation |
| `--step STEP` | — | Run a single step: `spec`, `build`, `judge`, `screenshot`, `package` |
| `workspace` | — | Workspace directory (required for all steps except `spec`) |
| `--language LANG` | random | Force website language (e.g. `en`, `es`, `fr`, `ja`, `ar`, `ko`, `de`, `pt`, `hi`, `zh`, `mixed-en-es`, `mixed-en-ja`) |

## Project Structure

```
reinforcement-env/
├── .env                          # API keys (ANTHROPIC_API_KEY, OPENAI_API_KEY)
├── remote_eval.py                # Run evals on Modal (all tasks in parallel)
├── .opencode/                    # OpenCode isolated config + data (gitignored)
├── pipeline/
│   ├── config.py                 # Configuration, paths, logger
│   ├── run_pipeline.py           # CLI entry point
│   ├── requirements.txt          # Python dependencies
│   ├── agents/
│   │   └── opencode_wrapper.py   # Python wrapper for OpenCode CLI
│   ├── generate/
│   │   ├── spec_generator.py     # LLM-driven website spec generation
│   │   ├── generation_loop.py    # Builder + judge iteration loop
│   │   ├── screenshot.py         # Playwright screenshot capture
│   │   └── seed_specs.json       # 15 seed examples for spec diversity
│   ├── package/
│   │   └── harbor_task.py        # Harbor task directory builder
│   └── grade/
│       └── grader.py             # Grading system (runs inside Harbor)
├── generated/                    # Generated workspaces (gitignored)
│   └── <category>-<name>/        # One workspace per website
│       ├── spec.json             # Website specification
│       ├── site/                 # Source code (HTML + CSS only)
│       │   ├── home.html
│       │   ├── about.html
│       │   └── styles.css
│       └── screenshots/          # Reference screenshots (after step 4)
│           ├── home-desktop.png
│           ├── home-tablet.png
│           └── home-mobile.png
├── tasks/                        # Packaged Harbor tasks (gitignored)
│   └── web-design-<slug>/
│       ├── instruction.md
│       ├── task.toml
│       ├── environment/Dockerfile
│       ├── tests/
│       │   ├── test.sh
│       │   ├── grader.py
│       │   └── reference_screenshots/
│       └── solution/
└── logs/                         # Pipeline logs (gitignored)
    └── pipeline-<id>.log
```

## How the Generation Loop Works

```
for each iteration (up to max_iterations):
    1. BUILDER (OpenCode agent with random model from pool)
       - Reads spec.json + feedback from previous judge
       - Writes HTML + CSS to site/
       - Uses Playwright MCP to self-check at 3 viewports
       - Saves screenshots to screenshots/ (cleaned up after)

    2. JUDGES (one OpenCode agent per model in pool)
       - Reads source code from site/
       - Takes Playwright screenshots at 3 viewports
       - Scores 0-10 against spec
       - Writes .verdict-N.json with score + actionable feedback
       - Cleaned up after reading

    3. CONSENSUS CHECK
       - If ALL judges scored 10/10 → done
       - Otherwise → aggregate feedback → next iteration
```

The builder gets a **fresh OpenCode session** each iteration. It doesn't remember previous conversations — it sees files on disk + judge feedback in its prompt.

## Models

Models are specified in `provider/model` format. The pipeline uses [OpenCode](https://opencode.ai/) which supports 75+ providers.

Default models (configured in `pipeline/config.py`):
- `anthropic/claude-opus-4-7`
- `openai/gpt-5.5`

To see available models:
```bash
opencode models anthropic
opencode models openai
```

## Credential Isolation

API keys come **only** from the `.env` file in the project root. The pipeline sets `XDG_DATA_HOME` and `XDG_CONFIG_HOME` to `.opencode/` so OpenCode never reads system-level credentials from `~/.local/share/opencode/auth.json`.

## Logs

Every pipeline run creates a log file in `logs/pipeline-<id>.log`. The log contains:

- **INFO**: High-level progress (scores, iteration results, file counts)
- **DEBUG**: Full OpenCode agent output (assistant messages, tool calls with inputs/outputs, raw events)

Console output shows INFO level only. Check the log file for full details.

## Broken Website Tasks

~25% of generated tasks (configurable) have intentional design defects:

- **Broken responsiveness**: Elements that overflow on mobile/tablet
- **Typos**: Misspelled text in prominent locations
- **Bad design**: Clashing colors, poor contrast
- **Alignment issues**: Misaligned grid items, inconsistent spacing
- **Overflow**: Text/elements breaking container boundaries
- **Inconsistency**: Components styled differently than their siblings

The evaluation agent must:
1. Replicate the design exactly (including the defects)
2. Write a `defects_report.md` identifying each defect

## Running Evaluations with Harbor

Evaluations run entirely on Modal (zero local resource usage). See step 6 above for setup and usage.

```bash
# All tasks in parallel
modal run remote_eval.py

# View downloaded results
harbor view remote-jobs
```

**Architecture:** Each task gets its own Modal machine running the Harbor orchestrator + claude-code agent. Harbor spawns child Modal sandboxes for trial environments. Your Mac only streams logs and downloads results at the end.
