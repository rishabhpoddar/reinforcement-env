"""Harbor task packager.

Creates Harbor-compatible task directories from generated websites.
"""

import json
import shutil
from pathlib import Path

from pipeline.config import TASKS_DIR, VIEWPORTS, slugify


def package_task(
    spec: dict,
    site_dir: str | Path,
    screenshots_dir: str | Path,
    generation_metadata: dict,
    task_id: str | None = None,
) -> Path:
    """Package a generated website as a Harbor task.

    Args:
        spec: Website specification dict.
        site_dir: Directory containing the generated HTML/CSS files.
        screenshots_dir: Directory containing reference screenshots.
        generation_metadata: Metadata from the generation loop.
        task_id: Optional task ID. Auto-generated from spec if not provided.

    Returns:
        Path to the created task directory.
    """
    site_dir = Path(site_dir)
    screenshots_dir = Path(screenshots_dir)

    # Generate task ID
    if not task_id:
        category = slugify(spec.get("category", "unknown"))
        site_name = slugify(spec.get("site_name", "site"), max_len=30)
        task_id = f"{category}-{site_name}"

    task_dir = TASKS_DIR / f"web-design-{task_id}"
    task_dir.mkdir(parents=True, exist_ok=True)

    # Create subdirectories
    env_dir = task_dir / "environment"
    tests_dir = task_dir / "tests"
    ref_dir = tests_dir / "reference_screenshots"
    solution_dir = task_dir / "solution"

    for d in [env_dir, tests_dir, ref_dir, solution_dir]:
        d.mkdir(parents=True, exist_ok=True)

    # --- instruction.md ---
    assets_dir = site_dir / "assets"
    has_assets = assets_dir.exists() and bool(list(assets_dir.glob("*")))
    instruction = _build_instruction(spec, screenshots_dir, has_assets=has_assets)
    (task_dir / "instruction.md").write_text(instruction)

    # --- task.toml ---
    task_toml = _build_task_toml(spec, task_id)
    (task_dir / "task.toml").write_text(task_toml)

    # --- Dockerfile ---
    dockerfile = _build_dockerfile(has_assets=has_assets)
    (env_dir / "Dockerfile").write_text(dockerfile)

    # --- Copy reference screenshots into tests (for grader) and environment (for agent) ---
    for screenshot in screenshots_dir.glob("*.png"):
        shutil.copy2(screenshot, ref_dir / screenshot.name)
    env_ref_dir = env_dir / "reference_screenshots"
    if env_ref_dir.exists():
        shutil.rmtree(env_ref_dir)
    shutil.copytree(screenshots_dir, env_ref_dir)

    # --- task_meta.json ---
    meta = {
        "spec": spec,
        "is_broken": spec.get("is_broken", False),
        "defects": spec.get("defects", []),
        "pages": spec.get("pages", []),
        "viewports": {k: v for k, v in VIEWPORTS.items()},
        "generation": {
            "converged": generation_metadata.get("converged", False),
            "iterations": len(generation_metadata.get("iterations", [])),
        },
    }
    (tests_dir / "task_meta.json").write_text(json.dumps(meta, indent=2))

    # --- Copy image assets into environment ---
    assets_dir = site_dir / "assets"
    if assets_dir.exists() and list(assets_dir.glob("*")):
        env_assets_dir = env_dir / "assets"
        if env_assets_dir.exists():
            shutil.rmtree(env_assets_dir)
        shutil.copytree(assets_dir, env_assets_dir)

    # --- grader.py (copied at eval time) ---
    _write_grader(tests_dir)

    # --- test.sh ---
    _write_test_sh(tests_dir)

    # --- grader requirements ---
    _write_grader_requirements(tests_dir)

    # --- solution/solve.sh ---
    _write_solution(solution_dir, site_dir)

    return task_dir


def _build_instruction(
    spec: dict, screenshots_dir: Path, has_assets: bool = False
) -> str:
    """Build the instruction.md content."""
    pages = spec.get("pages", [])
    page_list = ", ".join(f"`{p}.html`" for p in pages)
    category = spec.get("category", "unknown")
    site_name = spec.get("site_name", "Website")
    n_pages = len(pages)

    # Build screenshot reference section
    screenshot_refs = []
    for page in pages:
        for viewport in VIEWPORTS:
            fname = f"{page}-{viewport}.png"
            if (screenshots_dir / fname).exists():
                screenshot_refs.append(
                    f"- `reference_screenshots/{fname}` — "
                    f"{page} page, {viewport} viewport"
                )

    screenshots_section = (
        "\n".join(screenshot_refs)
        if screenshot_refs
        else "See reference_screenshots/ directory"
    )

    instruction = f"""# Web Design Replication Task: {site_name}

You are given screenshots of a **{n_pages}-page {category} website** at three viewport sizes
(desktop 1280px, tablet 768px, mobile 375px).

Your task is to create a **pixel-perfect replication** of this website using HTML and CSS.

## CRITICAL: What "pixel-perfect" means

This is NOT about creating a "similar looking" website. You must reproduce the EXACT layout, structure, and visual design shown in the screenshots:

- **Study each screenshot carefully** before writing any code
- **Count the exact number of columns, cards, sections** on each page
- **Match the precise layout structure** — if the hero has a 2-column split with text left and image right, yours must too
- **Reproduce specific design elements** — drop caps, sidebars, decorative dividers, card styles, badges, overlays
- **Match the color palette exactly** — extract colors from the screenshots and use them
- **Match the typography hierarchy** — heading sizes, font weights, italic vs regular, serif vs sans-serif
- **Match spacing and proportions** — margins, padding, gaps between elements
- **Match the responsive behavior** — compare desktop vs tablet vs mobile screenshots to understand how the layout adapts

Do NOT take creative liberties. Do NOT simplify the design. Do NOT substitute your own layout ideas. Your output should look identical to the screenshots when rendered in a browser.

## Files to Create

- HTML files: {page_list}
- Shared stylesheet: `styles.css`
- Place all files in `/app/`

## Constraints

- Navigation between pages must work via relative links (e.g., `href="about.html"`)
- No external dependencies — no CDN links, no JavaScript libraries, no external fonts
- Use system font stacks that match the visual style (serif, sans-serif, monospace as appropriate)
- Focus entirely on visual fidelity — functionality is not required
"""

    if has_assets:
        instruction += """
## Image Assets

The required media files for the website are provided in the `/app/assets/` folder. Use these images in your HTML with relative paths like `<img src="assets/filename.png">`. Do NOT generate or create new images — use only the provided assets.
"""

    instruction += f"""

## Reference Screenshots

{screenshots_section}

## How to Approach This

1. **Start by examining ALL screenshots** — understand the full site design before writing code
2. **Identify the design system** — colors, fonts, spacing scale, shared components (nav, footer)
3. **Build the shared CSS first** — variables, resets, typography, layout utilities, component styles
4. **Build each page** — match the exact structure shown in the desktop screenshot
5. **Add responsive styles** — compare tablet and mobile screenshots to understand breakpoint behavior
6. **Review your work** — compare your output against each screenshot and fix discrepancies

## Grading

You will be graded by an LLM judge that compares your rendered pages against the reference screenshots side by side. The judge scores:
- **Layout** (0-10) — are sections, columns, and elements positioned exactly as shown?
- **Color** (0-10) — does the color scheme match precisely?
- **Typography** (0-10) — are font sizes, weights, and styles correct?
- **Spacing** (0-10) — are margins, padding, and whitespace proportions right?
- **Components** (0-10) — are UI elements (cards, buttons, nav, badges, dividers) visually accurate?

A score of 10 means your page is visually indistinguishable from the reference. Aim for 10/10 on every criterion.
"""

    # Add broken website section if applicable
    if spec.get("is_broken"):
        instruction += """
## Important: This Website Has Intentional Design Defects

This website contains **intentional design defects**. You must **replicate the design EXACTLY as shown** in the screenshots, including any defects you notice. Do NOT fix or improve the design — reproduce it faithfully.
"""

    return instruction


def _build_task_toml(spec: dict, task_id: str) -> str:
    """Build the task.toml content."""
    category = spec.get("category", "unknown")
    site_name = spec.get("site_name", "Website")
    keywords_extra = ""
    if spec.get("is_broken"):
        keywords_extra = ', "broken-design", "defect-analysis"'

    return f"""schema_version = "1.2"
artifacts = ["/app"]

[task]
name = "web-design-replication/{task_id}"
description = "Replicate the {site_name} ({category}) website design from screenshots"
authors = [{{ name = "RL Pipeline", email = "pipeline@example.com" }}]
keywords = ["web-design", "html", "css", "responsive", "{category}"{keywords_extra}]

[environment]
cpus = 2
memory_mb = 4096
storage_mb = 2048
allow_internet = true

[agent]
timeout_sec = 900

[verifier]
timeout_sec = 600

[verifier.env]
ANTHROPIC_API_KEY = "${{ANTHROPIC_API_KEY}}"
OPENAI_API_KEY = "${{OPENAI_API_KEY}}"
"""


def _build_dockerfile(has_assets: bool = False) -> str:
    """Build the Dockerfile for the task environment."""
    base = """FROM node:20-slim

# Install Python and Chromium
RUN apt-get update && apt-get install -y --no-install-recommends \\
    python3 python3-pip python3-venv chromium \\
    && rm -rf /var/lib/apt/lists/*

# Create grader virtual environment
RUN python3 -m venv /opt/grader-venv

# Install grader Python packages
RUN /opt/grader-venv/bin/pip install --no-cache-dir \\
    playwright anthropic openai Pillow numpy scikit-image

# Install Playwright browsers
RUN /opt/grader-venv/bin/python -m playwright install --with-deps chromium

WORKDIR /app
"""
    if has_assets:
        base += """
# Copy image assets into the working directory
COPY assets/ /app/assets/
"""
    base += """
# Copy reference screenshots so the agent can view them
COPY reference_screenshots/ /app/reference_screenshots/
"""
    return base


def _write_test_sh(tests_dir: Path) -> None:
    """Write the test.sh grading script."""
    script = """#!/bin/bash
set -e

cd /tests

# Run the grader (stderr merged so judge failures appear in test output)
/opt/grader-venv/bin/python grader.py \\
    --reference /tests/reference_screenshots \\
    --submission /app \\
    --meta /tests/task_meta.json \\
    --output /logs/verifier/reward.json \\
    2>&1

echo "Grading complete. Results:"
cat /logs/verifier/reward.json
"""
    test_sh = tests_dir / "test.sh"
    test_sh.write_text(script)
    test_sh.chmod(0o755)


def _write_grader(tests_dir: Path) -> None:
    """Copy the self-contained grader.py into the Harbor task."""
    grader_source = Path(__file__).parent / "harbor_grader.py"
    shutil.copy2(grader_source, tests_dir / "grader.py")


def _write_grader_requirements(tests_dir: Path) -> None:
    """Write requirements.txt for the grader."""
    reqs = """anthropic>=0.40.0
openai>=2.0.0
playwright>=1.40.0
Pillow>=10.0.0
numpy>=1.24.0
scikit-image>=0.20.0
"""
    (tests_dir / "requirements.txt").write_text(reqs)


def _write_solution(solution_dir: Path, site_dir: Path) -> None:
    """Write the solution script (copies original generated files)."""
    # Copy the original generated files as the reference solution
    solve_sh = """#!/bin/bash
# Reference solution: copy the original generated website files
cp /solution/site_files/* /app/ 2>/dev/null || true
# Copy assets if they exist in the solution
if [ -d /solution/site_files/assets ]; then
    cp -r /solution/site_files/assets /app/assets 2>/dev/null || true
fi
"""
    (solution_dir / "solve.sh").write_text(solve_sh)
    (solution_dir / "solve.sh").chmod(0o755)

    # Copy site files into solution
    site_files_dir = solution_dir / "site_files"
    site_files_dir.mkdir(exist_ok=True)
    for f in site_dir.glob("*.html"):
        shutil.copy2(f, site_files_dir / f.name)
    for f in site_dir.glob("*.css"):
        shutil.copy2(f, site_files_dir / f.name)
    # Copy assets directory if it exists
    assets_dir = site_dir / "assets"
    if assets_dir.exists() and list(assets_dir.glob("*")):
        dest_assets = site_files_dir / "assets"
        if dest_assets.exists():
            shutil.rmtree(dest_assets)
        shutil.copytree(assets_dir, dest_assets)
