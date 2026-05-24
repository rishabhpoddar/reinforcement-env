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

    # --- Copy reference screenshots ---
    for screenshot in screenshots_dir.glob("*.png"):
        shutil.copy2(screenshot, ref_dir / screenshot.name)

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
## Important: Design Defect Analysis

This website contains **intentional design defects**. You must:

1. **Replicate the design EXACTLY as shown** in the screenshots (including the defects)
2. Create a file `defects_report.md` listing each defect you observe:
   - What the defect is
   - Which page and viewport it appears on
   - Why it's a problem from a design perspective
   - How you would fix it if asked to

Your ability to identify design issues will be part of your score.
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

# Install grader Python packages (lightweight — no torch/CLIP)
RUN /opt/grader-venv/bin/pip install --no-cache-dir \\
    playwright anthropic Pillow

# Install Playwright browsers
RUN /opt/grader-venv/bin/python -m playwright install --with-deps chromium

WORKDIR /app
"""
    if has_assets:
        base += """
# Copy image assets into the working directory
COPY assets/ /app/assets/
"""
    return base


def _write_test_sh(tests_dir: Path) -> None:
    """Write the test.sh grading script."""
    script = """#!/bin/bash
set -e

cd /tests

# Run the grader
/opt/grader-venv/bin/python grader.py \\
    --reference /tests/reference_screenshots \\
    --submission /app \\
    --meta /tests/task_meta.json \\
    --output /logs/verifier/reward.json

echo "Grading complete. Results:"
cat /logs/verifier/reward.json
"""
    test_sh = tests_dir / "test.sh"
    test_sh.write_text(script)
    test_sh.chmod(0o755)


def _write_grader(tests_dir: Path) -> None:
    """Write the self-contained grader.py for the Harbor task."""
    grader_code = '''#!/usr/bin/env python3
"""Harbor task grader — evaluates design replication quality.

Self-contained grader that runs inside the Harbor verifier container.
Compares the agent's submission against reference screenshots using:
1. LLM judge (multi-criteria visual comparison)
2. Structural checks (pages exist, nav links, stylesheet)
3. Defect replication check (for broken tasks)
4. Defect identification check (for broken tasks)
"""

import argparse
import asyncio
import base64
import json
import os
import sys
from pathlib import Path


# ──────────────────────────────────────────────────
# LLM Judge
# ──────────────────────────────────────────────────

def _resize_image_for_api(image_path: str, max_height: int = 7000) -> bytes:
    """Read an image and resize if taller than max_height (Claude API limit is 8000px)."""
    from PIL import Image
    import io

    img = Image.open(image_path)
    if img.height > max_height:
        ratio = max_height / img.height
        new_width = int(img.width * ratio)
        img = img.resize((new_width, max_height), Image.LANCZOS)

    buf = io.BytesIO()
    img.save(buf, format="PNG")
    return buf.getvalue()


def llm_judge_score(
    ref_screenshot: str,
    sub_screenshot: str,
    page_name: str,
    viewport: str,
) -> dict:
    """Score a single page/viewport pair using Claude as judge with structured output."""
    try:
        import anthropic

        client = anthropic.Anthropic(api_key=os.environ.get("ANTHROPIC_API_KEY", ""))

        ref_bytes = _resize_image_for_api(ref_screenshot)
        sub_bytes = _resize_image_for_api(sub_screenshot)
        ref_b64 = base64.b64encode(ref_bytes).decode()
        sub_b64 = base64.b64encode(sub_bytes).decode()

        response = client.messages.create(
            model="claude-haiku-4-5-20251001",
            max_tokens=1024,
            messages=[{
                "role": "user",
                "content": [
                    {"type": "text", "text": f"Compare these two website screenshots ({page_name} page, {viewport} viewport). The first is the REFERENCE design, the second is the SUBMISSION that attempts to replicate it. Score each criterion 0-10."},
                    {"type": "image", "source": {"type": "base64", "media_type": "image/png", "data": ref_b64}},
                    {"type": "image", "source": {"type": "base64", "media_type": "image/png", "data": sub_b64}},
                ],
            }],
            tool_choice={"type": "tool", "name": "score_design"},
            tools=[{
                "name": "score_design",
                "description": "Score the design replication quality",
                "input_schema": {
                    "type": "object",
                    "properties": {
                        "layout": {"type": "integer", "minimum": 0, "maximum": 10, "description": "Layout fidelity: sections, columns, element positioning"},
                        "color": {"type": "integer", "minimum": 0, "maximum": 10, "description": "Color accuracy: color scheme match"},
                        "typography": {"type": "integer", "minimum": 0, "maximum": 10, "description": "Typography: font sizes, weights, hierarchy"},
                        "spacing": {"type": "integer", "minimum": 0, "maximum": 10, "description": "Spacing and proportions: margins, padding, whitespace"},
                        "components": {"type": "integer", "minimum": 0, "maximum": 10, "description": "Component accuracy: buttons, cards, nav, etc."},
                    },
                    "required": ["layout", "color", "typography", "spacing", "components"],
                },
            }],
        )

        # Extract tool use result
        for block in response.content:
            if block.type == "tool_use":
                scores = block.input
                return {k: float(v) / 10.0 for k, v in scores.items()}

        # Fallback if no tool use
        print(f"LLM judge did not use tool, falling back", file=sys.stderr)
        return {"layout": 0.5, "color": 0.5, "typography": 0.5, "spacing": 0.5, "components": 0.5}

    except Exception as e:
        print(f"LLM judge failed ({e}), using fallback scores", file=sys.stderr)
        return {"layout": 0.5, "color": 0.5, "typography": 0.5, "spacing": 0.5, "components": 0.5}


# ──────────────────────────────────────────────────
# Structural Checks
# ──────────────────────────────────────────────────

def check_structural(submission_dir: Path, expected_pages: list[str]) -> float:
    """Check structural requirements (pages exist, nav links, etc.)."""
    score = 0.0
    total_checks = 0

    for page in expected_pages:
        total_checks += 1
        html_file = submission_dir / f"{page}.html"
        if html_file.exists():
            score += 1.0
            content = html_file.read_text()
            if "styles.css" in content:
                score += 0.5
                total_checks += 0.5
            nav_links = sum(1 for p in expected_pages if f"{p}.html" in content)
            if nav_links >= len(expected_pages) - 1:
                score += 0.5
                total_checks += 0.5

    total_checks += 1
    if (submission_dir / "styles.css").exists():
        score += 1.0

    return score / total_checks if total_checks > 0 else 0.0


# ──────────────────────────────────────────────────
# Defect Grading
# ──────────────────────────────────────────────────

def grade_defect_replication(
    reference_dir: Path,
    sub_screenshots: dict[str, dict[str, str]],
    expected_defects: list[dict],
) -> dict:
    """Grade whether the agent replicated each defect by comparing screenshots."""
    try:
        import anthropic

        client = anthropic.Anthropic(api_key=os.environ.get("ANTHROPIC_API_KEY", ""))
        scores = []

        for defect in expected_defects:
            page = defect.get("page", "")
            viewport = defect.get("viewport", "all")
            description = defect.get("description", "")

            viewports_to_check = ["desktop", "tablet", "mobile"] if viewport == "all" else [viewport]

            defect_found = False
            for vp in viewports_to_check:
                ref_path = reference_dir / f"{page}-{vp}.png"
                sub_path = sub_screenshots.get(page, {}).get(vp)

                if not ref_path.exists() or not sub_path or not Path(sub_path).exists():
                    continue

                ref_b64 = base64.b64encode(open(str(ref_path), "rb").read()).decode()
                sub_b64 = base64.b64encode(open(sub_path, "rb").read()).decode()

                response = client.messages.create(
                    model="claude-haiku-4-5-20251001",
                    max_tokens=256,
                    messages=[{
                        "role": "user",
                        "content": [
                            {"type": "text", "text": f"The reference website has this intentional defect: \\"{description}\\"\\n\\nImage 1 is the REFERENCE (has the defect). Image 2 is the SUBMISSION (should also have the defect).\\n\\nIs the defect present in the submission? Reply ONLY with JSON: {{\\\"present\\\": true/false, \\\"reason\\\": \\\"...\\\"}}"},
                            {"type": "image", "source": {"type": "base64", "media_type": "image/png", "data": ref_b64}},
                            {"type": "image", "source": {"type": "base64", "media_type": "image/png", "data": sub_b64}},
                        ],
                    }],
                )

                text = response.content[0].text.strip()
                if text.startswith("```"):
                    text = text.split("\\n", 1)[1]
                    if text.endswith("```"):
                        text = text[:text.rfind("```")]
                    text = text.strip()

                try:
                    result = json.loads(text)
                    if result.get("present", False):
                        defect_found = True
                        break
                except json.JSONDecodeError:
                    if "true" in text.lower():
                        defect_found = True
                        break

            scores.append(1.0 if defect_found else 0.0)

        avg_score = sum(scores) / len(scores) if scores else 0.0
        return {"defect_replication": avg_score, "per_defect": scores}

    except Exception as e:
        print(f"Defect replication grading failed ({e}), using 0.5", file=sys.stderr)
        return {"defect_replication": 0.5, "per_defect": []}


def grade_defect_identification(
    submission_dir: Path,
    expected_defects: list[dict],
) -> dict:
    """Grade the agent's defect report."""
    report_path = submission_dir / "defects_report.md"

    if not report_path.exists():
        return {"defect_identification": 0.0, "report_found": False}

    report_text = report_path.read_text()
    if not report_text.strip():
        return {"defect_identification": 0.0, "report_found": True, "report_empty": True}

    try:
        import anthropic
        client = anthropic.Anthropic(api_key=os.environ.get("ANTHROPIC_API_KEY", ""))

        defects_json = json.dumps(expected_defects, indent=2)

        response = client.messages.create(
            model="claude-haiku-4-5-20251001",
            max_tokens=512,
            messages=[{
                "role": "user",
                "content": f"The following are the ACTUAL defects in a website:\\n{defects_json}\\n\\nThe agent wrote this defect report:\\n{report_text}\\n\\nScore 0.0-1.0: how well did the agent identify the defects? Consider precision (no false positives) and recall (found all real defects). Return ONLY a JSON: {{\\\"score\\\": 0.X, \\\"reason\\\": \\\"...\\\"}}",
            }],
        )

        text = response.content[0].text.strip()
        if text.startswith("```"):
            text = text.split("\\n", 1)[1]
            if text.endswith("```"):
                text = text[:text.rfind("```")]
            text = text.strip()

        result = json.loads(text)
        return {
            "defect_identification": float(result.get("score", 0.5)),
            "report_found": True,
            "reason": result.get("reason", ""),
        }

    except Exception as e:
        print(f"Defect grading failed ({e}), using 0.5", file=sys.stderr)
        return {"defect_identification": 0.5, "report_found": True}


# ──────────────────────────────────────────────────
# Screenshot Capture (for submission)
# ──────────────────────────────────────────────────

async def capture_submission_screenshots(
    submission_dir: Path,
    output_dir: Path,
    viewports: dict,
) -> dict[str, dict[str, str]]:
    """Capture screenshots of the submission at all viewports."""
    from playwright.async_api import async_playwright

    output_dir.mkdir(parents=True, exist_ok=True)
    screenshots: dict[str, dict[str, str]] = {}

    html_files = sorted(submission_dir.glob("*.html"))
    if not html_files:
        return screenshots

    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=True)

        for html_file in html_files:
            page_name = html_file.stem
            screenshots[page_name] = {}

            for vp_name, vp_size in viewports.items():
                ctx = await browser.new_context(
                    viewport={"width": vp_size["width"], "height": vp_size["height"]},
                    device_scale_factor=1,
                )
                page = await ctx.new_page()
                await page.goto(f"file://{html_file.resolve()}", wait_until="networkidle")
                await page.wait_for_timeout(500)

                fname = f"{page_name}-{vp_name}.png"
                path = output_dir / fname
                await page.screenshot(path=str(path), full_page=True)
                screenshots[page_name][vp_name] = str(path)

                await ctx.close()

        await browser.close()

    return screenshots


# ──────────────────────────────────────────────────
# Main Grader
# ──────────────────────────────────────────────────

def grade(
    reference_dir: Path,
    submission_dir: Path,
    meta: dict,
    output_path: Path,
) -> dict:
    """Run the full grading pipeline."""
    pages = meta.get("pages", [])
    viewports = meta.get("viewports", {
        "desktop": {"width": 1280, "height": 900},
        "tablet": {"width": 768, "height": 1024},
        "mobile": {"width": 375, "height": 812},
    })
    is_broken = meta.get("is_broken", False)
    defects = meta.get("defects", [])

    # Capture submission screenshots
    sub_screenshots_dir = Path("/logs/verifier/screenshots")
    sub_screenshots = asyncio.run(
        capture_submission_screenshots(submission_dir, sub_screenshots_dir, viewports)
    )

    # Collect per-page, per-viewport LLM judge scores
    all_llm = []
    per_page_scores = {}

    for page in pages:
        per_page_scores[page] = {}
        for vp_name in viewports:
            ref_path = reference_dir / f"{page}-{vp_name}.png"
            sub_path = sub_screenshots.get(page, {}).get(vp_name)

            if not ref_path.exists() or not sub_path or not Path(sub_path).exists():
                per_page_scores[page][vp_name] = 0.0
                all_llm.append({"layout": 0, "color": 0, "typography": 0, "spacing": 0, "components": 0})
                continue

            judge_scores = llm_judge_score(str(ref_path), sub_path, page, vp_name)
            all_llm.append(judge_scores)

            page_vp_score = sum(judge_scores.values()) / len(judge_scores) if judge_scores else 0.0
            per_page_scores[page][vp_name] = round(float(page_vp_score), 3)

    # Aggregate LLM scores
    llm_agg = {}
    if all_llm:
        for key in ["layout", "color", "typography", "spacing", "components"]:
            llm_agg[key] = float(sum(s.get(key, 0) for s in all_llm) / len(all_llm))
    avg_llm = float(sum(llm_agg.values()) / len(llm_agg)) if llm_agg else 0.0

    # Structural score
    structural = check_structural(submission_dir, pages)

    # Final score
    if is_broken:
        visual_fidelity = 0.85 * avg_llm + 0.15 * structural
        defect_rep = grade_defect_replication(reference_dir, sub_screenshots, defects)
        defect_id = grade_defect_identification(submission_dir, defects)
        overall = (0.50 * visual_fidelity +
                  0.25 * defect_rep.get("defect_replication", 0.0) +
                  0.25 * defect_id.get("defect_identification", 0.0))
    else:
        overall = 0.85 * avg_llm + 0.15 * structural
        defect_rep = {}
        defect_id = {}

    # Harbor expects flat float/int values in reward.json — no nested dicts
    result = {
        "overall": round(float(overall), 3),
        "structural": round(structural, 3),
        "llm_layout": round(llm_agg.get("layout", 0), 3),
        "llm_color": round(llm_agg.get("color", 0), 3),
        "llm_typography": round(llm_agg.get("typography", 0), 3),
        "llm_spacing": round(llm_agg.get("spacing", 0), 3),
        "llm_components": round(llm_agg.get("components", 0), 3),
        "llm_avg": round(avg_llm, 3),
    }

    if is_broken:
        result["defect_replication"] = round(
            defect_rep.get("defect_replication", 0.0), 3
        )
        result["defect_identification"] = round(
            defect_id.get("defect_identification", 0.0), 3
        )

    # Write output
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(json.dumps(result, indent=2))

    return result


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Grade web design replication")
    parser.add_argument("--reference", required=True, help="Reference screenshots dir")
    parser.add_argument("--submission", required=True, help="Submission dir")
    parser.add_argument("--meta", required=True, help="Task metadata JSON file")
    parser.add_argument("--output", required=True, help="Output reward JSON path")
    args = parser.parse_args()

    with open(args.meta) as f:
        meta = json.load(f)

    result = grade(
        reference_dir=Path(args.reference),
        submission_dir=Path(args.submission),
        meta=meta,
        output_path=Path(args.output),
    )

    print(f"Overall score: {result[\'overall\']}")
'''
    (tests_dir / "grader.py").write_text(grader_code)


def _write_grader_requirements(tests_dir: Path) -> None:
    """Write requirements.txt for the grader."""
    reqs = """anthropic>=0.40.0
playwright>=1.40.0
Pillow>=10.0.0
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
