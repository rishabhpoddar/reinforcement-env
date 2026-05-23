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
    instruction = _build_instruction(spec, screenshots_dir)
    (task_dir / "instruction.md").write_text(instruction)

    # --- task.toml ---
    task_toml = _build_task_toml(spec, task_id)
    (task_dir / "task.toml").write_text(task_toml)

    # --- Dockerfile ---
    dockerfile = _build_dockerfile()
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

    # --- grader.py (copied at eval time) ---
    _write_grader(tests_dir)

    # --- test.sh ---
    _write_test_sh(tests_dir)

    # --- grader requirements ---
    _write_grader_requirements(tests_dir)

    # --- solution/solve.sh ---
    _write_solution(solution_dir, site_dir)

    return task_dir


def _build_instruction(spec: dict, screenshots_dir: Path) -> str:
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

    screenshots_section = "\n".join(screenshot_refs) if screenshot_refs else "See reference_screenshots/ directory"

    instruction = f"""# Web Design Replication Task: {site_name}

You are given screenshots of a **{n_pages}-page {category} website** at three viewport sizes
(desktop 1280px, tablet 768px, mobile 375px).

Your task is to replicate this website's visual design as closely as possible using HTML and CSS.

## Requirements

- Create these HTML files: {page_list}
- Create a shared stylesheet: `styles.css`
- Place all files in `/app/`
- The design **must be responsive** — match the reference at all three viewport sizes
- Use placeholder content for images (CSS gradients, colored boxes, or inline SVG)
- Navigation between pages must work via relative links (e.g., `href="about.html"`)
- No external dependencies — no CDN links, no JavaScript libraries, no external fonts
- Focus on **visual design fidelity**, not functionality

## Reference Screenshots

{screenshots_section}

## Grading

Your submission will be scored on a continuous 0-1 scale based on:
- **Visual similarity** to the reference screenshots at each viewport
- **Layout fidelity** — correct positioning of sections, columns, and elements
- **Color accuracy** — matching the color scheme
- **Typography** — similar font sizes, weights, and hierarchy
- **Spacing and proportions** — correct margins, padding, whitespace
- **Responsiveness** — proper adaptation across desktop, tablet, and mobile
- **Cross-page consistency** — shared design language across all pages
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

[task]
name = "web-design-replication/{task_id}"
description = "Replicate the {site_name} ({category}) website design from screenshots"
authors = [{{ name = "RL Pipeline", email = "pipeline@example.com" }}]
keywords = ["web-design", "html", "css", "responsive", "{category}"{keywords_extra}]

[environment]
cpus = 2
memory_mb = 4096
storage_mb = 2048
allow_internet = false

[agent]
timeout_sec = 900

[verifier]
timeout_sec = 600

[verifier.env]
ANTHROPIC_API_KEY = "${{ANTHROPIC_API_KEY}}"
"""


def _build_dockerfile() -> str:
    """Build the Dockerfile for the task environment."""
    return """FROM node:20-slim

# Install Python and Chromium
RUN apt-get update && apt-get install -y --no-install-recommends \\
    python3 python3-pip python3-venv chromium \\
    && rm -rf /var/lib/apt/lists/*

# Create grader virtual environment
RUN python3 -m venv /opt/grader-venv

# Install grader Python packages (lightweight — no torch/CLIP)
RUN /opt/grader-venv/bin/pip install --no-cache-dir \\
    playwright anthropic

# Install Playwright browsers
RUN /opt/grader-venv/bin/python -m playwright install --with-deps chromium

WORKDIR /app
"""


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

def llm_judge_score(
    ref_screenshot: str,
    sub_screenshot: str,
    page_name: str,
    viewport: str,
) -> dict:
    """Score a single page/viewport pair using Claude as judge."""
    try:
        import anthropic

        client = anthropic.Anthropic(api_key=os.environ.get("ANTHROPIC_API_KEY", ""))

        ref_b64 = base64.b64encode(open(ref_screenshot, "rb").read()).decode()
        sub_b64 = base64.b64encode(open(sub_screenshot, "rb").read()).decode()

        response = client.messages.create(
            model="claude-haiku-4-5-20251001",
            max_tokens=1024,
            messages=[{
                "role": "user",
                "content": [
                    {"type": "text", "text": f"Compare these two website screenshots ({page_name} page, {viewport} viewport). The first is the REFERENCE design, the second is the SUBMISSION that attempts to replicate it.\\n\\nScore each criterion 0-10:\\n1. Layout Fidelity (sections, columns, element positioning)\\n2. Color Accuracy (color scheme match)\\n3. Typography (font sizes, weights, hierarchy)\\n4. Spacing & Proportions (margins, padding, whitespace)\\n5. Component Accuracy (buttons, cards, nav, etc.)\\n\\nReturn ONLY JSON: {{\\\"layout\\\": N, \\\"color\\\": N, \\\"typography\\\": N, \\\"spacing\\\": N, \\\"components\\\": N}}"},
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

        scores = json.loads(text)
        return {k: float(v) / 10.0 for k, v in scores.items()}

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
    sub_screenshots_dir = Path("/tmp/submission_screenshots")
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

    result = {
        "overall": round(float(overall), 3),
        "llm_judge": {k: round(v, 3) for k, v in llm_agg.items()},
        "structural": round(structural, 3),
        "per_page": per_page_scores,
    }

    if is_broken:
        result["defect_replication"] = round(
            defect_rep.get("defect_replication", 0.0), 3
        )
        result["defect_replication_per_defect"] = defect_rep.get("per_defect", [])
        result["defect_identification"] = round(
            defect_id.get("defect_identification", 0.0), 3
        )
        result["defect_report_found"] = defect_id.get("report_found", False)

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
"""
    (tests_dir / "requirements.txt").write_text(reqs)


def _write_solution(solution_dir: Path, site_dir: Path) -> None:
    """Write the solution script (copies original generated files)."""
    # Copy the original generated files as the reference solution
    solve_sh = f"""#!/bin/bash
# Reference solution: copy the original generated website files
cp /solution/site_files/* /app/ 2>/dev/null || true
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
