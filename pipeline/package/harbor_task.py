"""Harbor task packager.

Creates Harbor-compatible task directories from generated websites.
"""

import json
import shutil
from pathlib import Path

from pipeline.config import TASKS_DIR, VIEWPORTS


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
        category = spec.get("category", "unknown").replace(" ", "-").lower()
        site_name = (
            spec.get("site_name", "site").replace(" ", "-").lower()[:30]
        )
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

    return f"""[task]
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

# Install Python, Chromium, and grader dependencies
RUN apt-get update && apt-get install -y --no-install-recommends \\
    python3 python3-pip python3-venv chromium \\
    && rm -rf /var/lib/apt/lists/*

# Create grader virtual environment
RUN python3 -m venv /opt/grader-venv

# Install grader Python packages
RUN /opt/grader-venv/bin/pip install --no-cache-dir \\
    playwright anthropic Pillow scikit-image \\
    numpy open-clip-torch torch torchvision

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
    """Write the grader.py stub that imports from the grade module.

    The actual grading logic lives in pipeline/grade/. This stub is
    a self-contained version that gets copied into the Harbor task.
    """
    # We'll write the full grader inline since it needs to be self-contained
    # inside the Docker container (no access to pipeline/ module)
    grader_code = '''#!/usr/bin/env python3
"""Harbor task grader — evaluates design replication quality.

This is a self-contained grader that runs inside the Harbor verifier container.
It compares the agent's submission against reference screenshots using:
1. Visual metrics (CLIP similarity, SSIM, color histogram)
2. LLM judge (multi-criteria rubric)
3. Structural checks
4. Responsiveness evaluation
5. Defect grading (for broken website tasks)
"""

import argparse
import asyncio
import json
import os
import sys
from pathlib import Path

import numpy as np
from PIL import Image
from skimage.metrics import structural_similarity as ssim


# ──────────────────────────────────────────────────
# Visual Metrics
# ──────────────────────────────────────────────────

def compute_ssim(img1_path: str, img2_path: str) -> float:
    """Compute SSIM between two images."""
    img1 = Image.open(img1_path).convert("L")
    img2 = Image.open(img2_path).convert("L")

    # Resize to common size
    target_size = (min(img1.width, img2.width), min(img1.height, img2.height))
    img1 = img1.resize(target_size, Image.LANCZOS)
    img2 = img2.resize(target_size, Image.LANCZOS)

    arr1 = np.array(img1)
    arr2 = np.array(img2)

    score, _ = ssim(arr1, arr2, full=True)
    return float(max(0.0, min(1.0, score)))


def compute_color_histogram_similarity(img1_path: str, img2_path: str) -> float:
    """Compute color histogram intersection similarity."""
    img1 = Image.open(img1_path).convert("RGB")
    img2 = Image.open(img2_path).convert("RGB")

    def get_histogram(img: Image.Image) -> np.ndarray:
        arr = np.array(img)
        hist = np.zeros(768)  # 256 * 3 channels
        for c in range(3):
            channel_hist, _ = np.histogram(arr[:, :, c], bins=256, range=(0, 256))
            hist[c * 256 : (c + 1) * 256] = channel_hist
        # Normalize
        total = hist.sum()
        if total > 0:
            hist = hist / total
        return hist

    h1 = get_histogram(img1)
    h2 = get_histogram(img2)

    # Histogram intersection
    intersection = np.minimum(h1, h2).sum()
    return float(max(0.0, min(1.0, intersection)))


def compute_clip_similarity(img1_path: str, img2_path: str) -> float:
    """Compute CLIP cosine similarity between two images.

    Falls back to 0.5 if CLIP model fails to load.
    """
    try:
        import open_clip
        import torch

        model, _, preprocess = open_clip.create_model_and_transforms(
            "ViT-B-32", pretrained="openai"
        )
        model.eval()

        img1 = preprocess(Image.open(img1_path).convert("RGB")).unsqueeze(0)
        img2 = preprocess(Image.open(img2_path).convert("RGB")).unsqueeze(0)

        with torch.no_grad():
            feat1 = model.encode_image(img1)
            feat2 = model.encode_image(img2)
            feat1 = feat1 / feat1.norm(dim=-1, keepdim=True)
            feat2 = feat2 / feat2.norm(dim=-1, keepdim=True)
            similarity = (feat1 @ feat2.T).item()

        return float(max(0.0, min(1.0, similarity)))
    except Exception as e:
        print(f"CLIP failed ({e}), using fallback score 0.5", file=sys.stderr)
        return 0.5


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
        import base64

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

    # Check each expected page exists
    for page in expected_pages:
        total_checks += 1
        html_file = submission_dir / f"{page}.html"
        if html_file.exists():
            score += 1.0

            # Check for stylesheet link
            content = html_file.read_text()
            if "styles.css" in content:
                score += 0.5
                total_checks += 0.5

            # Check for nav links to other pages
            nav_links = sum(1 for p in expected_pages if f"{p}.html" in content)
            if nav_links >= len(expected_pages) - 1:
                score += 0.5
                total_checks += 0.5

    # Check styles.css exists
    total_checks += 1
    if (submission_dir / "styles.css").exists():
        score += 1.0

    return score / total_checks if total_checks > 0 else 0.0


# ──────────────────────────────────────────────────
# Defect Grading
# ──────────────────────────────────────────────────

def grade_defect_identification(
    submission_dir: Path,
    expected_defects: list[dict],
) -> dict:
    """Grade the agent's defect identification (for broken tasks)."""
    report_path = submission_dir / "defects_report.md"

    if not report_path.exists():
        return {"defect_identification": 0.0, "report_found": False}

    report_text = report_path.read_text()

    if not report_text.strip():
        return {"defect_identification": 0.0, "report_found": True, "report_empty": True}

    # Use LLM to evaluate the defect report
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
    viewports = meta.get("viewports", {"desktop": {"width": 1280, "height": 900}, "tablet": {"width": 768, "height": 1024}, "mobile": {"width": 375, "height": 812}})
    is_broken = meta.get("is_broken", False)
    defects = meta.get("defects", [])

    # Capture submission screenshots
    sub_screenshots_dir = Path("/tmp/submission_screenshots")
    sub_screenshots = asyncio.run(
        capture_submission_screenshots(submission_dir, sub_screenshots_dir, viewports)
    )

    # Collect per-page, per-viewport scores
    all_clip = []
    all_ssim = []
    all_color = []
    all_llm = []
    per_page_scores = {}

    for page in pages:
        per_page_scores[page] = {}
        for vp_name in viewports:
            ref_path = reference_dir / f"{page}-{vp_name}.png"
            sub_path = sub_screenshots.get(page, {}).get(vp_name)

            if not ref_path.exists() or not sub_path or not Path(sub_path).exists():
                per_page_scores[page][vp_name] = 0.0
                all_clip.append(0.0)
                all_ssim.append(0.0)
                all_color.append(0.0)
                all_llm.append({"layout": 0, "color": 0, "typography": 0, "spacing": 0, "components": 0})
                continue

            # Visual metrics
            clip_score = compute_clip_similarity(str(ref_path), sub_path)
            ssim_score = compute_ssim(str(ref_path), sub_path)
            color_score = compute_color_histogram_similarity(str(ref_path), sub_path)

            all_clip.append(clip_score)
            all_ssim.append(ssim_score)
            all_color.append(color_score)

            # LLM judge
            judge_scores = llm_judge_score(str(ref_path), sub_path, page, vp_name)
            all_llm.append(judge_scores)

            # Per-page score (simple average for now)
            page_vp_score = (clip_score * 0.3 + ssim_score * 0.2 + color_score * 0.15 +
                           np.mean(list(judge_scores.values())) * 0.35)
            per_page_scores[page][vp_name] = round(float(page_vp_score), 3)

    # Aggregate
    avg_clip = float(np.mean(all_clip)) if all_clip else 0.0
    avg_ssim = float(np.mean(all_ssim)) if all_ssim else 0.0
    avg_color = float(np.mean(all_color)) if all_color else 0.0

    llm_agg = {}
    if all_llm:
        for key in ["layout", "color", "typography", "spacing", "components"]:
            llm_agg[key] = float(np.mean([s.get(key, 0) for s in all_llm]))
    avg_llm = float(np.mean(list(llm_agg.values()))) if llm_agg else 0.0

    # Structural score
    structural = check_structural(submission_dir, pages)

    # Responsiveness score (compare how scores differ across viewports)
    responsive_score = 0.7  # Default
    if per_page_scores:
        vp_scores = {vp: [] for vp in viewports}
        for page_scores in per_page_scores.values():
            for vp, score in page_scores.items():
                vp_scores[vp].append(score)
        vp_means = [float(np.mean(scores)) for scores in vp_scores.values() if scores]
        if len(vp_means) >= 2:
            # Low variance across viewports = good responsiveness
            variance = float(np.var(vp_means))
            responsive_score = max(0.0, min(1.0, 1.0 - variance * 10))

    # Final score
    if is_broken:
        visual_fidelity = (0.20 * avg_clip + 0.10 * avg_ssim + 0.10 * avg_color +
                          0.40 * avg_llm + 0.10 * responsive_score + 0.10 * structural)
        defect_id = grade_defect_identification(submission_dir, defects)
        overall = (0.60 * visual_fidelity +
                  0.20 * visual_fidelity +  # defect replication approximated by visual fidelity
                  0.20 * defect_id.get("defect_identification", 0.0))
    else:
        overall = (0.20 * avg_clip + 0.10 * avg_ssim + 0.10 * avg_color +
                  0.40 * avg_llm + 0.10 * responsive_score + 0.10 * structural)
        defect_id = {}

    result = {
        "overall": round(float(overall), 3),
        "visual_metrics": {
            "clip": round(avg_clip, 3),
            "ssim": round(avg_ssim, 3),
            "color": round(avg_color, 3),
        },
        "llm_judge": {k: round(v, 3) for k, v in llm_agg.items()},
        "responsiveness": round(responsive_score, 3),
        "structural": round(structural, 3),
        "per_page": per_page_scores,
    }

    if is_broken:
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

    print(f"Overall score: {result['overall']}")
'''
    (tests_dir / "grader.py").write_text(grader_code)


def _write_grader_requirements(tests_dir: Path) -> None:
    """Write requirements.txt for the grader."""
    reqs = """anthropic>=0.40.0
Pillow>=10.0.0
numpy>=1.26.0
scikit-image>=0.22.0
open-clip-torch>=2.26.0
torch>=2.1.0
torchvision>=0.16.0
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
