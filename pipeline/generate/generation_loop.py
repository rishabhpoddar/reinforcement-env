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
import threading
from concurrent.futures import ThreadPoolExecutor, as_completed
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

    class QuietServer(http.server.HTTPServer):
        def handle_error(self, request, client_address):
            # Suppress BrokenPipeError from clients disconnecting early
            import sys
            exc = sys.exc_info()[1]
            if isinstance(exc, BrokenPipeError):
                return
            super().handle_error(request, client_address)

    server = QuietServer(("127.0.0.1", port), QuietHandler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    return thread, port


# ──────────────────────────────────────────────────
# Prompts
# ──────────────────────────────────────────────────


def _is_image_too_large_error(error: str | None) -> bool:
    """Check if an error is the Anthropic many-image dimension limit."""
    if not error:
        return False
    return "image dimensions exceed max allowed size" in error.lower() or \
           "exceed max allowed size for many-image" in error.lower()


SCREENSHOT_RESIZE_INSTRUCTION = (
    "IMPORTANT: Before reading any screenshot PNG file, you MUST first check its "
    "dimensions using: sips -g pixelWidth -g pixelHeight <path-to-screenshot.png>\n"
    "If EITHER dimension exceeds 1900 pixels, resize it first using:\n"
    "  sips --resampleHeightWidthMax 1900 <path-to-screenshot.png>\n"
    "This avoids API errors with large images. Always check and resize BEFORE reading the file."
)


def _clear_screenshots(workspace_dir: Path, subdir: str = "screenshots") -> None:
    """Remove a screenshots folder from the workspace after an OpenCode session."""
    screenshots_dir = workspace_dir / subdir
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

    # Build image assets instruction if spec has them
    image_assets = spec.get("image_assets", [])
    image_section = ""
    if image_assets:
        image_lines = []
        for img in image_assets:
            image_lines.append(
                f"  - {img['filename']}: \"{img['prompt']}\" (size: {img['size']}, "
                f"used on: {img['used_on']}, purpose: {img['purpose']})"
            )
        image_list = "\n".join(image_lines)
        image_section = f"""
## Image Assets (IMPORTANT)
You have a `generate_image` tool available. Use it to generate these images BEFORE writing HTML.
Generate each image and save it to site/assets/. Then reference them in your HTML as src="assets/filename.png".

Images to generate:
{image_list}

Generate ALL images first, then write your HTML and CSS files referencing them.
"""

    # Build language/direction/dark mode notes
    lang = spec.get("language", "en")
    direction = spec.get("text_direction", "ltr")
    dark_mode = spec.get("dark_mode", False)
    design_style = spec.get("design_style", "")
    nav_style = spec.get("nav_style", "top-bar")

    lang_note = ""
    if lang != "en":
        lang_note = f"\n- Language: All text content must be in {lang}. Set the `lang` attribute on the `<html>` tag accordingly."
    if direction == "rtl":
        lang_note += "\n- RTL: Set `dir=\"rtl\"` on the `<html>` tag. Mirror all layouts — sidebars swap sides, text aligns right, flex/grid direction reverses. Use `margin-inline-start`/`end` instead of left/right where possible."
    if dark_mode:
        lang_note += "\n- Dark mode: Use dark backgrounds and light text throughout. Ensure sufficient contrast for readability."
    if design_style:
        lang_note += f"\n- Design style: {design_style} — follow this aesthetic consistently across all pages."
    if nav_style:
        lang_note += f"\n- Navigation: Use a {nav_style} navigation pattern as described in the spec."

    return f"""You are an expert web developer. Build a website matching this specification.

## Specification
{spec_json}

## Rules
- Write ALL source files into the site/ subfolder (e.g., site/home.html, site/styles.css)
- ONLY create .html files and ONE styles.css — nothing else
- One HTML file per page (e.g., site/home.html, site/about.html)
- No external dependencies (no CDN, no Google Fonts, no JS)
- System font stacks only
- For images: Use the `generate_image` tool to create AI-generated images. Save them to site/assets/ and reference as src="assets/filename.png". For decorative elements, you can still use CSS gradients or inline SVG.{lang_note}
- All pages share navigation and footer
- Responsive: desktop (1280px), tablet (768px), mobile (375px)
- Use CSS custom properties for the color palette
- Use CSS Grid and Flexbox
{image_section}{broken_note}
## Visual Verification (IMPORTANT)
A local server is running. After writing your files, you MUST visually verify your work:
1. Use Playwright to navigate to each page: {page_urls}
2. Take screenshots at desktop (1280px), tablet (768px), and mobile (375px) widths
3. Save screenshots into the screenshots/ subfolder (e.g., screenshots/home-desktop.png)
4. IMPORTANT: After saving each screenshot, use the read tool to open the PNG file and actually LOOK at it
5. Compare what you see in the screenshot against the spec — check colors, layout, typography, spacing
6. Fix any issues you find, then re-screenshot and re-verify

{SCREENSHOT_RESIZE_INSTRUCTION}
{feedback_section}"""


def _build_judge_prompt(spec: dict, port: int, verdict_path: str, screenshots_subdir: str = "screenshots") -> str:
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
Images are in site/assets/ — check that images referenced in HTML actually exist.

## Pages to Review (via Playwright)
{page_urls}

## Your Task
1. Read the HTML and CSS source files in site/
2. Use Playwright to navigate to each page URL above
3. For each page, take screenshots at these viewport widths: 1280, 768, 375
4. Save screenshots into the {screenshots_subdir}/ subfolder (e.g., {screenshots_subdir}/home-desktop.png)
5. IMPORTANT: After saving each screenshot, use the read tool to open the PNG file and actually LOOK at it
6. Base your scoring on what you VISUALLY SEE in the screenshots, not just the source code
7. Evaluate: layout, colors, typography, responsiveness, components, consistency

IMPORTANT: For screenshots, use ONLY these Playwright tools in sequence:
  - playwright_browser_resize to set viewport width
  - playwright_browser_navigate to load the page
  - playwright_browser_take_screenshot to capture it
Do NOT use playwright_browser_run_code_unsafe for taking screenshots — it will silently fail.

## Scoring
- 10 = perfect match to spec at all viewports
- 8-9 = minor issues (small spacing, slight color differences)
- 6-7 = noticeable gaps (missing sections, wrong layout)
- 4-5 = significant problems (missing pages, broken responsive)
- 0-3 = fundamentally wrong or missing

## CRITICAL: Write your verdict to the file {verdict_path}
The file must contain exactly this JSON structure:
{{"score": <number 0-10>, "feedback": "<specific actionable feedback>"}}

If you give a score of 10, set feedback to an empty string "".

You MUST create this file. This is the most important part of your task.

{SCREENSHOT_RESIZE_INSTRUCTION}
"""


def _build_judge_followup_prompt(verdict_path: str, screenshots_subdir: str = "screenshots") -> str:
    """Create the prompt for continuing a judge session after builder fixes."""
    return f"""The builder has attempted to fix the issues you raised in your previous review.

Re-check the website now:
1. Re-read the spec from spec.json to refresh your memory of the requirements
2. Use Playwright to navigate to each page again
2. Take fresh screenshots at all viewport widths (1280, 768, 375)
3. Save screenshots into the {screenshots_subdir}/ subfolder
4. After saving each screenshot, use the read tool to open the PNG file and actually LOOK at it
5. Compare what you see against the spec and your previous feedback

If the issues are fixed, increase the score accordingly. If new issues appeared, note them.

IMPORTANT: If you notice you have been raising the same core issues for more than 3 iterations
and the builder is not making meaningful progress on them, the builder is stuck. In that case,
set your feedback to an empty string "" to signal that further iteration won't help.

OVERWRITE the existing verdict file at {verdict_path} with your updated scores.
The file must contain exactly this JSON structure:
{{"score": <number 0-10>, "feedback": "<specific actionable feedback>"}}

If the score is 10 or the builder is stuck on the same issues, set feedback to "".
You MUST overwrite this file.

{SCREENSHOT_RESIZE_INSTRUCTION}
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

    # Pick the builder model once — same model across all iterations
    # so we can preserve the session (conversation history)
    builder_model = random.choice(models)
    builder_session_id: str | None = None
    log.info(f"  Builder model: {builder_model} (fixed for all iterations)")

    feedback = None
    verdicts: list[dict] = []
    judge_session_ids: dict[str, str | None] = {m: None for m in models}
    metadata = {
        "spec": spec,
        "iterations": [],
        "final_scores": [],
        "converged": False,
    }

    for iteration in range(1, max_iterations + 1):
        log.info(f"\n  Iteration {iteration}/{max_iterations}")

        # --- BUILDER ---
        log.info(f"    Builder: {builder_model}" +
                 (f" (continuing session {builder_session_id})" if builder_session_id else " (new session)"))

        if builder_session_id is None:
            # First iteration: full prompt with spec
            builder_prompt = _build_builder_prompt(spec, port, feedback)
        else:
            # Subsequent iterations: continue session with feedback
            builder_prompt = (
                f"The judges reviewed your work and found issues. "
                f"Re-read the spec in spec.json and fix the following:\n\n"
                f"{feedback}\n\n"
                f"After fixing, use Playwright to verify your changes visually — "
                f"take screenshots, read them, and confirm the issues are resolved.\n\n"
                f"{SCREENSHOT_RESIZE_INSTRUCTION}"
            )

        builder_result = agent.run(
            prompt=builder_prompt,
            model=builder_model,
            working_dir=workspace_dir,
            session_id=builder_session_id,
            label=f"iter{iteration}/builder",
        )
        _clear_screenshots(workspace_dir)

        # Capture session ID for continuation
        if builder_result.session_id:
            builder_session_id = builder_result.session_id

        if not builder_result.success:
            # If the error is due to oversized images in the session history,
            # drop the session and retry with a fresh one that includes
            # resize instructions so future screenshots stay under the limit.
            if _is_image_too_large_error(builder_result.error):
                log.info(f"    Builder hit image size limit — retrying with fresh session + resize instructions")
                builder_session_id = None
                builder_prompt = _build_builder_prompt(spec, port, feedback)
                builder_prompt += f"\n\n{SCREENSHOT_RESIZE_INSTRUCTION}"
                builder_result = agent.run(
                    prompt=builder_prompt,
                    model=builder_model,
                    working_dir=workspace_dir,
                    session_id=None,
                    label=f"iter{iteration}/builder-retry",
                )
                _clear_screenshots(workspace_dir)
                if builder_result.session_id:
                    builder_session_id = builder_result.session_id

            if not builder_result.success:
                log.info(f"    Builder failed: {builder_result.error}")
                metadata["iterations"].append({
                    "iteration": iteration,
                    "builder_model": builder_model,
                    "builder_success": False,
                    "builder_error": builder_result.error,
                })
                continue

        # Skip judges on the last iteration — verdict can't be acted on
        if iteration == max_iterations:
            metadata["iterations"].append({
                "iteration": iteration,
                "builder_model": builder_model,
                "builder_success": True,
            })
            log.info(f"    Last iteration — skipping judges (no further builder rounds)")
            break

        # --- JUDGES ---
        verdicts, judge_session_ids = judge_website(
            workspace_dir=workspace_dir,
            spec=spec,
            models=models,
            port=port,
            agent=agent,
            iteration=iteration,
            judge_session_ids=judge_session_ids,
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

        # Check if all judges signaled "stuck" via empty feedback
        all_stuck = all(
            not v.get("feedback", "").strip()
            for v in verdicts
            if v.get("score", 0) < 10
        )
        if all_stuck and verdicts:
            log.info(f"  All judges signaled stuck — builder cannot fix remaining issues. Exiting loop early.")
            metadata["early_exit"] = "judges_signaled_stuck"
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
    iteration: int | None = None,
    judge_session_ids: dict[str, str | None] | None = None,
) -> tuple[list[dict], dict[str, str | None]]:
    """Run the judge phase on a website.

    Used both standalone (--step judge) and from within generate_website().

    Args:
        workspace_dir: The generation workspace (must have site/ with HTML+CSS).
        spec: Website spec. If None, loaded from workspace_dir/spec.json.
        models: List of model strings. Defaults to config MODELS.
        port: HTTP server port serving site/. If None, starts a new one.
        agent: OpenCodeAgent instance. If None, creates a new one.
        iteration: Current iteration number (for log labels).
        judge_session_ids: Dict mapping model name to session ID for continuing
            judge sessions. If None, all judges start fresh.

    Returns:
        Tuple of (list of verdict dicts, updated judge_session_ids dict).
    """
    models = models or MODELS
    workspace_dir = Path(workspace_dir)
    site_dir = workspace_dir / "site"

    if judge_session_ids is None:
        judge_session_ids = {m: None for m in models}

    if not site_dir.exists() or not list(site_dir.glob("*.html")):
        log.error(f"No HTML files found in {site_dir}")
        return [], judge_session_ids

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

    def _run_single_judge(judge_idx: int, judge_model: str) -> dict:
        """Run a single judge. Returns a dict with verdict and updated session_id."""
        # Give each judge its own working directory so each gets an independent
        # Playwright MCP server. Symlink site/ and spec.json from the real workspace.
        judge_workdir = workspace_dir / f".judge-workdir-{judge_idx}"
        judge_workdir.mkdir(parents=True, exist_ok=True)
        for name in ("site", "spec.json"):
            link = judge_workdir / name
            target = workspace_dir / name
            if target.exists() and not link.exists():
                link.symlink_to(target.resolve())

        screenshots_subdir = "screenshots"
        verdict_filename = ".verdict.json"
        verdict_path = str(judge_workdir / verdict_filename)
        session_id = judge_session_ids.get(judge_model)
        log.info(f"    Judge: {judge_model} → {verdict_filename}" +
                 (f" (continuing session {session_id})" if session_id else " (new session)"))

        # First iteration: full prompt; subsequent: followup prompt
        if session_id is None:
            judge_prompt = _build_judge_prompt(spec, port, verdict_filename, screenshots_subdir)
        else:
            judge_prompt = _build_judge_followup_prompt(verdict_filename, screenshots_subdir)

        iter_prefix = f"iter{iteration}/" if iteration else ""
        judge_result = agent.run(
            prompt=judge_prompt,
            model=judge_model,
            working_dir=judge_workdir,
            session_id=session_id,
            label=f"{iter_prefix}judge-{judge_idx}",
        )
        _clear_screenshots(judge_workdir, screenshots_subdir)

        # If image-too-large error, drop session and retry fresh with resize instructions
        if not judge_result.success and _is_image_too_large_error(judge_result.error):
            log.info(f"      → Judge hit image size limit — retrying with fresh session + resize instructions")
            judge_prompt_retry = _build_judge_prompt(spec, port, verdict_filename, screenshots_subdir)
            judge_prompt_retry += f"\n\n{SCREENSHOT_RESIZE_INSTRUCTION}"
            judge_result = agent.run(
                prompt=judge_prompt_retry,
                model=judge_model,
                working_dir=judge_workdir,
                session_id=None,
                label=f"{iter_prefix}judge-{judge_idx}-retry",
            )
            _clear_screenshots(judge_workdir, screenshots_subdir)

        # Build result
        new_session_id = judge_result.session_id or session_id
        if judge_result.success:
            verdict = _read_judge_verdict(verdict_path)
            verdict["model"] = judge_model
            log.info(
                f"      → score={verdict['score']}/10: "
                f"{verdict.get('feedback', '')[:100]}"
            )
        else:
            log.info(f"      → Judge failed: {judge_result.error}")
            verdict = {
                "model": judge_model,
                "score": 0,
                "feedback": f"Judge failed: {judge_result.error}",
            }
            # Drop session on image-too-large so next iteration starts fresh
            if _is_image_too_large_error(judge_result.error):
                new_session_id = None

        return {
            "verdict": verdict,
            "judge_model": judge_model,
            "session_id": new_session_id,
        }

    # Run all judges in parallel
    verdicts = []
    with ThreadPoolExecutor(max_workers=len(models)) as executor:
        futures = {
            executor.submit(_run_single_judge, idx, model): (idx, model)
            for idx, model in enumerate(models)
        }
        # Collect results in index order
        results_by_idx = {}
        for future in as_completed(futures):
            idx, model = futures[future]
            results_by_idx[idx] = future.result()

    for idx in sorted(results_by_idx):
        result = results_by_idx[idx]
        verdicts.append(result["verdict"])
        judge_session_ids[result["judge_model"]] = result["session_id"]

    return verdicts, judge_session_ids
