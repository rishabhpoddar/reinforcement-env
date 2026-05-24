"""Pipeline configuration."""

import logging
import os
import re
import uuid
from pathlib import Path


# Paths
PIPELINE_ROOT = Path(__file__).parent
PROJECT_ROOT = PIPELINE_ROOT.parent
TASKS_DIR = PROJECT_ROOT / "tasks"
GENERATED_DIR = PROJECT_ROOT / "generated"  # Intermediate generated websites
LOGS_DIR = PROJECT_ROOT / "logs"


# ── Shared logger ──
# Single log file per pipeline run, stored in logs/ at the repo root
def setup_logger() -> logging.Logger:
    LOGS_DIR.mkdir(parents=True, exist_ok=True)
    log_file = LOGS_DIR / f"pipeline-{uuid.uuid4().hex[:8]}.log"

    logger = logging.getLogger("pipeline")
    if logger.handlers:
        return logger  # Already set up

    logger.setLevel(logging.DEBUG)

    # File handler — everything goes to the log file
    fh = logging.FileHandler(log_file)
    fh.setLevel(logging.DEBUG)
    fh.setFormatter(logging.Formatter(
        "%(asctime)s [%(levelname)s] %(name)s: %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
    ))
    logger.addHandler(fh)

    # Console handler — INFO and above to stdout
    ch = logging.StreamHandler()
    ch.setLevel(logging.INFO)
    ch.setFormatter(logging.Formatter("%(message)s"))
    logger.addHandler(ch)

    logger.info(f"Log file: {log_file}")
    return logger


log = setup_logger()
SEED_SPECS_PATH = PIPELINE_ROOT / "generate" / "seed_specs.json"


def slugify(text: str, max_len: int = 50) -> str:
    """Convert text to a filesystem-safe slug."""
    slug = text.lower().replace(" ", "-")
    slug = re.sub(r"[^a-z0-9\-]", "", slug)  # Remove anything that's not alphanumeric or dash
    slug = re.sub(r"-+", "-", slug).strip("-")  # Collapse multiple dashes
    return slug[:max_len]
# LLM Models available for generation (provider/model format for OpenCode)
# Always use latest models for each provider
MODELS = [
    "anthropic/claude-opus-4-7",
    "openai/gpt-5.5",
]

# Spec generator model (used via direct API call for structured output)
SPEC_GENERATOR_MODEL = "claude-opus-4-7"

# Viewports for screenshots
VIEWPORTS = {
    "desktop": {"width": 1280, "height": 900},
    "tablet": {"width": 768, "height": 1024},
    "mobile": {"width": 375, "height": 812},
}

# Generation loop
MAX_GENERATION_ITERATIONS = 10  # Keep iterating until all judges give 10/10
BROKEN_WEBSITE_PROBABILITY = 0.25  # 25% of generated sites have defects

# API Keys — loaded from project .env file, NOT system env
def _load_project_env() -> dict[str, str]:
    """Load .env from project root."""
    env_path = PROJECT_ROOT / ".env"
    env_vars: dict[str, str] = {}
    if not env_path.exists():
        return env_vars
    for line in env_path.read_text().splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        key = key.strip()
        value = value.strip().strip("\"'")
        if key:
            env_vars[key] = value
    return env_vars


def get_anthropic_key() -> str:
    # Check os.environ first (may have been set explicitly), then .env
    key = os.environ.get("ANTHROPIC_API_KEY") or _load_project_env().get("ANTHROPIC_API_KEY", "")
    if not key:
        raise ValueError("ANTHROPIC_API_KEY not found in environment or .env")
    return key


def get_openai_key() -> str:
    key = os.environ.get("OPENAI_API_KEY") or _load_project_env().get("OPENAI_API_KEY", "")
    if not key:
        raise ValueError("OPENAI_API_KEY not found in environment or .env")
    return key
