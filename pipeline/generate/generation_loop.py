"""Website generation loop using OpenCode coding agents.

Orchestrates builder agent + multi-LLM judge agents (both via OpenCode)
to produce high-quality websites from specifications.

A local HTTP server runs on the site directory so both builder and judge
can use Playwright MCP to take screenshots (Playwright blocks file:// URLs).
"""

import http.server
import json
import random
import shutil
import socket
import tempfile
import threading
from pathlib import Path

from pipeline.agents.opencode_wrapper import OpenCodeAgent
from pipeline.config import MAX_GENERATION_ITERATIONS, MODELS, log


# ──────────────────────────────────────────────────
# Local HTTP server for Playwright
# ──────────────────────────────────────────────────

def _find_free_port() -> int:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        s.bind(("", 0))
        return s.getsockname()[1]


def _start_http_server(directory: Path) -> tuple[threading.Thread, int]:
    """Start a background HTTP server serving `directory`. Returns (thread, port)."""
    port = _find_free_port()

    handler = http.server.SimpleHTTPRequestHandler

    class QuietHandler(handler):
        def __init__(self, *args, **kwargs):
            super().__init__(*args, directory=str(directory), **kwargs)
        def log_message(self, format, *args):
            pass  # Suppress request logs

    server = http.server.HTTPServer(("127.0.0.1", port), QuietHandler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    return thread, port


# ──────────────────────────────────────────────────
# Prompts
# ──────────────────────────────────────────────────


def _clear_screenshots(workspace_dir: Path) -> None:
    """Remove the screenshots/ folder from the workspace after an OpenCode session."""
    screenshots_dir = workspace_dir / "screenshots"
    if screenshots_dir.exists():
        shutil.rmtree(screenshots_dir)


def _build_builder_prompt(
    spec: dict,
    port: int,
    feedback: str | None = None,
) -> str:
    """Create the prompt for the builder coding agent."""
    spec_json = json.dumps(spec, indent=2)
    pages = spec.get("pages", [])
    page_urls = ", ".join(f"http://localhost:{port}/{p}.html" for p in pages)

    broken_note = ""
    if spec.get("is_broken") and spec.get("defects"):
        defects_json = json.dumps(spec["defects"], indent=2)
        broken_note = f"""
## CRITICAL: Intentional Defects
Implement these defects exactly. The rest of the site should be well-designed.
{defects_json}
"""

    feedback_section = ""
    if feedback:
        feedback_section = f"""
## Feedback from Reviewers — FIX THESE ISSUES
{feedback}
"""

    return f"""You are an expert web developer. Build a website matching this specification.

## Specification
{spec_json}

## Rules
- Write ALL source files into the site/ subfolder (e.g., site/home.html, site/styles.css)
- ONLY create .html files and ONE styles.css — nothing else
- One HTML file per page (e.g., site/home.html, site/about.html)
- No external dependencies (no CDN, no Google Fonts, no JS)
- System font stacks only
- Images: CSS gradients, inline SVG, or colored placeholder divs
- All pages share navigation and footer
- Responsive: desktop (1280px), tablet (768px), mobile (375px)
- Use CSS custom properties for the color palette
- Use CSS Grid and Flexbox
{broken_note}
## Visual Verification (IMPORTANT)
A local server is running. After writing your files, you MUST visually verify your work:
1. Use Playwright to navigate to each page: {page_urls}
2. Take screenshots at desktop (1280px), tablet (768px), and mobile (375px) widths
3. Save screenshots into the screenshots/ subfolder (e.g., screenshots/home-desktop.png)
4. IMPORTANT: After saving each screenshot, use the read tool to open the PNG file and actually LOOK at it
5. Compare what you see in the screenshot against the spec — check colors, layout, typography, spacing
6. Fix any issues you find, then re-screenshot and re-verify
{feedback_section}"""


def _build_judge_prompt(spec: dict, port: int, verdict_path: str) -> str:
    """Create the prompt for the judge coding agent."""
    spec_json = json.dumps(spec, indent=2)
    pages = spec.get("pages", [])
    page_urls = "\n".join(f"  - http://localhost:{port}/{p}.html" for p in pages)

    broken_note = ""
    if spec.get("is_broken") and spec.get("defects"):
        defects_json = json.dumps(spec["defects"], indent=2)
        broken_note = f"""
## Intentional Defects
These defects are EXPECTED — do NOT penalize for them:
{defects_json}
Only penalize if they are MISSING or wrong.
"""

    return f"""You are a website design judge. Score this website 0-10 against its specification.

## Specification
{spec_json}
{broken_note}
## Source Files
The website source files are in the site/ subfolder. Read them from there.

## Pages to Review (via Playwright)
{page_urls}

## Your Task
1. Read the HTML and CSS source files in site/
2. Use Playwright to navigate to each page URL above
3. For each page, take screenshots at these viewport widths: 1280, 768, 375
4. Save screenshots into the screenshots/ subfolder (e.g., screenshots/home-desktop.png)
5. IMPORTANT: After saving each screenshot, use the read tool to open the PNG file and actually LOOK at it
6. Base your scoring on what you VISUALLY SEE in the screenshots, not just the source code
7. Evaluate: layout, colors, typography, responsiveness, components, consistency

## Scoring
- 10 = perfect match to spec at all viewports
- 8-9 = minor issues (small spacing, slight color differences)
- 6-7 = noticeable gaps (missing sections, wrong layout)
- 4-5 = significant problems (missing pages, broken responsive)
- 0-3 = fundamentally wrong or missing

## CRITICAL: Write your verdict to the file {verdict_path}
The file must contain exactly this JSON structure:
{{"score": <number 0-10>, "feedback": "<specific actionable feedback>"}}

You MUST create this file. This is the most important part of your task.
"""


def _read_judge_verdict(verdict_path: str) -> dict:
    """Read the verdict file written by the judge agent.

    Returns {"score": 0-10, "feedback": "..."}.
    Falls back to score 0 if file is missing or malformed.
    """
    verdict_file = Path(verdict_path)
    if not verdict_file.exists():
        log.warning(f"Judge did not write {verdict_path}")
        return {"score": 0, "feedback": "Judge did not write verdict file"}

    content = verdict_file.read_text().strip()
    verdict_file.unlink()

    if not content:
        log.warning(f"Verdict file is empty: {verdict_path}")
        return {"score": 0, "feedback": "Verdict file was empty"}

    try:
        verdict = json.loads(content)
        score = int(verdict.get("score", 0))
        score = max(0, min(10, score))  # Clamp to 0-10
        return {
            "score": score,
            "feedback": str(verdict.get("feedback", "No feedback")),
        }
    except (json.JSONDecodeError, ValueError) as e:
        log.warning(f"Failed to parse verdict: {e}, content: {content[:500]}")
        return {"score": 0, "feedback": f"Invalid verdict file: {content[:300]}"}


# ──────────────────────────────────────────────────
# Main generation loop
# ──────────────────────────────────────────────────

def _aggregate_judge_feedback(verdicts: list[dict]) -> str:
    """Combine feedback from multiple judges."""
    lines = []
    for i, verdict in enumerate(verdicts):
        model = verdict.get("model", f"Judge {i+1}")
        score = verdict.get("score", "?")
        feedback = verdict.get("feedback", "No feedback")
        lines.append(f"### {model} (score: {score}/10)\n{feedback}")
    return "\n\n".join(lines)


def generate_website(
    spec: dict,
    workspace_dir: str | Path,
    models: list[str] | None = None,
    max_iterations: int | None = None,
) -> dict:
    """Generate a website from a spec using the builder+judge loop.

    Args:
        workspace_dir: The generation workspace (e.g., generated/<slug>/).
            Source files go in workspace_dir/site/.
            OpenCode artifacts stay in workspace_dir/.
        models: List of model strings (provider/model). Defaults to config MODELS.
        max_iterations: Max builder-judge iterations. Defaults to config.

    Returns:
        Dict with generation metadata.
    """
    models = models or MODELS
    max_iterations = max_iterations or MAX_GENERATION_ITERATIONS
    workspace_dir = Path(workspace_dir)
    site_dir = workspace_dir / "site"
    site_dir.mkdir(parents=True, exist_ok=True)

    # Start HTTP server serving the site/ subfolder
    _, port = _start_http_server(site_dir)
    log.info(f"  HTTP server on http://localhost:{port}/ (serving {site_dir})")

    agent = OpenCodeAgent(timeout_sec=1800)  # 30 min per session

    feedback = None
    verdicts: list[dict] = []
    metadata = {
        "spec": spec,
        "iterations": [],
        "final_scores": [],
        "converged": False,
    }

    for iteration in range(1, max_iterations + 1):
        log.info(f"\n  Iteration {iteration}/{max_iterations}")

        # --- BUILDER ---
        builder_model = random.choice(models)
        log.info(f"    Builder: {builder_model}")

        builder_prompt = _build_builder_prompt(spec, port, feedback)
        builder_result = agent.run(
            prompt=builder_prompt,
            model=builder_model,
            working_dir=workspace_dir,
        )
        _clear_screenshots(workspace_dir)

        if not builder_result.success:
            log.info(f"    Builder failed: {builder_result.error}")
            metadata["iterations"].append({
                "iteration": iteration,
                "builder_model": builder_model,
                "builder_success": False,
                "builder_error": builder_result.error,
            })
            continue

        # --- JUDGES ---
        verdicts = judge_website(
            workspace_dir=workspace_dir,
            spec=spec,
            models=models,
            port=port,
            agent=agent,
        )

        # --- CONSENSUS ---
        all_perfect = all(v.get("score", 0) == 10 for v in verdicts)
        min_score = min((v.get("score", 0) for v in verdicts), default=0)
        avg_score = (
            sum(v.get("score", 0) for v in verdicts) / len(verdicts)
            if verdicts else 0
        )

        metadata["iterations"].append({
            "iteration": iteration,
            "builder_model": builder_model,
            "builder_success": True,
            "verdicts": verdicts,
            "all_perfect": all_perfect,
            "avg_score": avg_score,
        })

        log.info(
            f"    Scores: {[v.get('score', 0) for v in verdicts]} "
            f"(avg: {avg_score:.1f}, min: {min_score})"
        )

        if all_perfect:
            metadata["converged"] = True
            metadata["final_scores"] = verdicts
            log.info(f"  PERFECT 10/10 — finalized after {iteration} iteration(s)")
            break

        log.info(f"    Not yet perfect — iterating...")
        feedback = _aggregate_judge_feedback(verdicts)

    if not metadata["converged"]:
        best_avg = max(
            (it["avg_score"] for it in metadata["iterations"] if it.get("builder_success")),
            default=0,
        )
        log.info(
            f"  Did not reach 10/10 after {max_iterations} iterations. "
            f"Best avg: {best_avg:.1f}/10. Using last version."
        )
        metadata["final_scores"] = verdicts

    return metadata


def judge_website(
    workspace_dir: str | Path,
    spec: dict | None = None,
    models: list[str] | None = None,
    port: int | None = None,
    agent: OpenCodeAgent | None = None,
) -> list[dict]:
    """Run the judge phase on a website.

    Used both standalone (--judge-only) and from within generate_website().

    Args:
        workspace_dir: The generation workspace (must have site/ with HTML+CSS).
        spec: Website spec. If None, loaded from workspace_dir/spec.json.
        models: List of model strings. Defaults to config MODELS.
        port: HTTP server port serving site/. If None, starts a new one.
        agent: OpenCodeAgent instance. If None, creates a new one.

    Returns:
        List of verdict dicts from each judge.
    """
    models = models or MODELS
    workspace_dir = Path(workspace_dir)
    site_dir = workspace_dir / "site"

    if not site_dir.exists() or not list(site_dir.glob("*.html")):
        log.error(f"No HTML files found in {site_dir}")
        return []

    # Load spec if not provided
    if spec is None:
        spec_path = workspace_dir / "spec.json"
        if spec_path.exists():
            spec = json.loads(spec_path.read_text())
        else:
            pages = [f.stem for f in sorted(site_dir.glob("*.html"))]
            spec = {"pages": pages, "site_name": workspace_dir.name, "is_broken": False}
            log.warning(f"No spec.json found, using minimal spec with pages: {pages}")

    # Start HTTP server if not provided
    if port is None:
        _, port = _start_http_server(site_dir)
        log.info(f"  HTTP server on http://localhost:{port}/ (serving {site_dir})")

    if agent is None:
        agent = OpenCodeAgent(timeout_sec=1800)

    verdicts = []
    for judge_idx, judge_model in enumerate(models):
        verdict_filename = f".verdict-{judge_idx}.json"
        verdict_path = str(workspace_dir / verdict_filename)
        log.info(f"    Judge: {judge_model} → {verdict_filename}")

        judge_prompt = _build_judge_prompt(spec, port, verdict_filename)
        judge_result = agent.run(
            prompt=judge_prompt,
            model=judge_model,
            working_dir=workspace_dir,
        )
        _clear_screenshots(workspace_dir)

        if judge_result.success:
            verdict = _read_judge_verdict(verdict_path)
            verdict["model"] = judge_model
            verdicts.append(verdict)
            log.info(
                f"      → score={verdict['score']}/10: "
                f"{verdict.get('feedback', '')[:100]}"
            )
        else:
            log.info(f"      → Judge failed: {judge_result.error}")
            verdicts.append({
                "model": judge_model,
                "score": 0,
                "feedback": f"Judge failed: {judge_result.error}",
            })

    return verdicts
