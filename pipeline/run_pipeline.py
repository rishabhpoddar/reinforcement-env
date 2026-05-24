#!/usr/bin/env python3
"""Pipeline orchestrator — generates web design replication tasks end-to-end.

Usage:
    # Full pipeline: spec → build → screenshot → package
    python -m pipeline.run_pipeline --count 10
    python -m pipeline.run_pipeline --count 1 --broken
    python -m pipeline.run_pipeline --count 10 --broken-count 3

    # Run a single step on an existing workspace
    python -m pipeline.run_pipeline --step spec --clean
    python -m pipeline.run_pipeline --step build generated/my-site/
    python -m pipeline.run_pipeline --step judge generated/my-site/
    python -m pipeline.run_pipeline --step screenshot generated/my-site/
    python -m pipeline.run_pipeline --step package generated/my-site/

    # Run Harbor evaluation on a packaged task
    python -m pipeline.run_pipeline --step eval tasks/web-design-my-site/
    python -m pipeline.run_pipeline --step eval tasks/web-design-my-site/ --eval-env docker
    python -m pipeline.run_pipeline --step eval tasks/web-design-my-site/ --eval-model anthropic/claude-sonnet-4-6

    # Override models for any step
    python -m pipeline.run_pipeline --step judge generated/my-site/ --models openai/gpt-5.4-mini
"""

import argparse
import json
import sys
from pathlib import Path

# Ensure project root is in path
sys.path.insert(0, str(Path(__file__).parent.parent))

from pipeline.config import MODELS, TASKS_DIR, GENERATED_DIR, PROJECT_ROOT, log, slugify
from pipeline.generate.spec_generator import generate_spec, generate_specs_batch
from pipeline.generate.generation_loop import generate_website, judge_website
from pipeline.generate.screenshot import capture_screenshots_sync
from pipeline.package.harbor_task import package_task


# ── Individual step functions ──

def step_spec(
    spec_model: str,
    force_broken: bool | None = None,
    force_language: str | None = None,
) -> Path:
    """Generate a single website spec and create its workspace directory."""
    GENERATED_DIR.mkdir(parents=True, exist_ok=True)
    spec = generate_spec(model=spec_model, force_broken=force_broken, force_language=force_language)

    site_name = spec.get("site_name", "unknown")
    category = spec.get("category", "unknown")
    slug = slugify(f"{category}-{site_name}")
    workspace_dir = GENERATED_DIR / slug
    workspace_dir.mkdir(parents=True, exist_ok=True)
    (workspace_dir / "site").mkdir(exist_ok=True)

    (workspace_dir / "spec.json").write_text(json.dumps(spec, indent=2))
    log.info(f"Spec created: {site_name} ({category})")
    log.info(f"  Pages: {', '.join(spec.get('pages', []))}")
    log.info(f"  Broken: {spec.get('is_broken', False)}")
    log.info(f"  Workspace: {workspace_dir}")
    return workspace_dir


def step_build(workspace_dir: Path, models: list[str], max_iterations: int):
    """Run the builder+judge loop on a workspace with an existing spec."""
    spec_path = workspace_dir / "spec.json"
    if not spec_path.exists():
        log.error(f"No spec.json in {workspace_dir}")
        return
    spec = json.loads(spec_path.read_text())
    log.info(f"Building: {spec.get('site_name', '?')} ({spec.get('category', '?')})")
    generate_website(
        spec=spec,
        workspace_dir=workspace_dir,
        models=models,
        max_iterations=max_iterations,
    )
    html_files = list((workspace_dir / "site").glob("*.html"))
    log.info(f"  {len(html_files)} HTML files in site/")


def step_judge(workspace_dir: Path, models: list[str]):
    """Run judges on an existing site."""
    verdicts, _ = judge_website(workspace_dir=workspace_dir, models=models)
    log.info(f"{'='*60}")
    log.info("Results:")
    for v in verdicts:
        log.info(f"  {v.get('model', '?')}: {v['score']}/10 — {v.get('feedback', '')[:150]}")
    avg = sum(v["score"] for v in verdicts) / len(verdicts) if verdicts else 0
    log.info(f"  Average: {avg:.1f}/10")
    return verdicts


def step_screenshot(workspace_dir: Path):
    """Capture reference screenshots for an existing site."""
    site_dir = workspace_dir / "site"
    screenshots_dir = workspace_dir / "screenshots"
    screenshots_dir.mkdir(parents=True, exist_ok=True)
    if not list(site_dir.glob("*.html")):
        log.error(f"No HTML files in {site_dir}")
        return
    screenshots = capture_screenshots_sync(site_dir, screenshots_dir)
    total = sum(len(v) for v in screenshots.values())
    log.info(f"  Captured {total} screenshots across {len(screenshots)} pages")


def step_eval(task_dir: Path, model: str = "anthropic/claude-opus-4-7", env: str = "modal", trials: int = 1):
    """Run a Harbor evaluation on a packaged task."""
    import subprocess

    if not (task_dir / "task.toml").exists():
        log.error(f"No task.toml in {task_dir} — run --step package first")
        return

    env_file = PROJECT_ROOT / ".env"
    cmd = [
        "harbor", "run",
        "-p", str(task_dir),
        "--agent", "claude-code",
        "--model", model,
        "-e", env,
        "--env-file", str(env_file),
        "-k", str(trials),
        "-n", str(trials),
    ]

    log.info(f"Running Harbor eval: {' '.join(cmd)}")
    result = subprocess.run(cmd, cwd=str(PROJECT_ROOT))

    if result.returncode != 0:
        log.error(f"Harbor run failed with exit code {result.returncode}")
    else:
        # Find latest job and show results
        jobs_dir = PROJECT_ROOT / "jobs"
        if jobs_dir.exists():
            latest_job = sorted(jobs_dir.iterdir())[-1]
            result_file = latest_job / "result.json"
            if result_file.exists():
                r = json.loads(result_file.read_text())
                log.info(f"Job: {latest_job.name}")
                log.info(f"Finished: {r.get('finished_at')}")
                for eval_name, eval_data in r.get("stats", {}).get("evals", {}).items():
                    for m in eval_data.get("metrics", []):
                        log.info(f"Results: {json.dumps(m, indent=2)}")
                    if eval_data.get("exception_stats"):
                        log.info(f"Exceptions: {eval_data['exception_stats']}")
                cost = r.get("stats", {}).get("cost_usd")
                if cost:
                    log.info(f"Cost: ${cost:.2f}")


def step_package(workspace_dir: Path):
    """Package an existing site as a Harbor task."""
    site_dir = workspace_dir / "site"
    screenshots_dir = workspace_dir / "screenshots"
    spec_path = workspace_dir / "spec.json"

    if not spec_path.exists():
        log.error(f"No spec.json in {workspace_dir}")
        return
    if not list(site_dir.glob("*.html")):
        log.error(f"No HTML files in {site_dir}")
        return
    if not list(screenshots_dir.glob("*.png")):
        log.error(f"No screenshots in {screenshots_dir} — run --step screenshot first")
        return

    spec = json.loads(spec_path.read_text())
    task_dir = package_task(
        spec=spec,
        site_dir=site_dir,
        screenshots_dir=screenshots_dir,
        generation_metadata={"converged": False, "iterations": []},
    )
    log.info(f"  Task created: {task_dir}")


# ── Full pipeline ──

def generate_single_task(
    spec: dict,
    models: list[str] | None = None,
    max_iterations: int = 5,
) -> Path | None:
    """Generate a single Harbor task from a website spec."""
    models = models or MODELS
    site_name = spec.get("site_name", "unknown")
    category = spec.get("category", "unknown")

    log.info(f"{'='*60}")
    log.info(f"Generating: {site_name} ({category})")
    log.info(f"  Pages: {', '.join(spec.get('pages', []))}")
    log.info(f"  Broken: {spec.get('is_broken', False)}")
    log.info(f"{'='*60}")

    slug = slugify(f"{category}-{site_name}")
    gen_dir = GENERATED_DIR / slug
    site_dir = gen_dir / "site"
    screenshots_dir = gen_dir / "screenshots"
    site_dir.mkdir(parents=True, exist_ok=True)
    screenshots_dir.mkdir(parents=True, exist_ok=True)

    (gen_dir / "spec.json").write_text(json.dumps(spec, indent=2))

    # Step 1: Build
    log.info("[1/3] Running builder + judge generation loop...")
    gen_metadata = generate_website(
        spec=spec,
        workspace_dir=gen_dir,
        models=models,
        max_iterations=max_iterations,
    )

    html_files = list(site_dir.glob("*.html"))
    if not html_files:
        log.error("No HTML files generated. Skipping.")
        return None

    css_files = list(site_dir.glob("*.css"))
    log.info(f"  Generated {len(html_files)} HTML files + {len(css_files)} CSS file(s)")

    # Step 2: Screenshots
    log.info("[2/3] Capturing reference screenshots...")
    try:
        screenshots = capture_screenshots_sync(site_dir, screenshots_dir)
        total = sum(len(v) for v in screenshots.values())
        log.info(f"  Captured {total} screenshots across {len(screenshots)} pages")
    except Exception as e:
        log.error(f"Error capturing screenshots: {e}")
        return None

    # Step 3: Package
    log.info("[3/3] Packaging Harbor task...")
    try:
        task_dir = package_task(
            spec=spec,
            site_dir=site_dir,
            screenshots_dir=screenshots_dir,
            generation_metadata=gen_metadata,
        )
        log.info(f"  Task created: {task_dir}")
        return task_dir
    except Exception as e:
        log.error(f"Error packaging task: {e}")
        return None


def main():
    parser = argparse.ArgumentParser(
        description="Generate web design replication tasks for RL training"
    )
    parser.add_argument(
        "--count", type=int, default=1,
        help="Number of tasks to generate",
    )
    parser.add_argument(
        "--broken", action="store_true",
        help="Force all generated tasks to be broken websites",
    )
    parser.add_argument(
        "--clean", action="store_true",
        help="Force all generated tasks to be clean (no defects)",
    )
    parser.add_argument(
        "--broken-count", type=int, default=None,
        help="Exact number of broken tasks (out of --count)",
    )
    parser.add_argument(
        "--models", nargs="+", default=None,
        help="LLM models to use (provider/model format)",
    )
    parser.add_argument(
        "--max-iterations", type=int, default=5,
        help="Max builder-judge iterations per task",
    )
    parser.add_argument(
        "--spec-model", type=str, default="claude-opus-4-7",
        help="Anthropic model for spec generation",
    )
    parser.add_argument(
        "--language", type=str, default=None,
        help="Force website language (e.g. en, es, fr, ja, ar, ko, de, pt, hi, zh, mixed-en-es, mixed-en-ja)",
    )
    parser.add_argument(
        "--step", type=str, default=None,
        choices=["spec", "build", "judge", "screenshot", "package", "eval"],
        help="Run a single step. 'spec' creates a new workspace; others require a workspace arg. 'eval' requires a task dir.",
    )
    parser.add_argument(
        "workspace", nargs="?", default=None,
        help="Workspace or task directory (required for all steps except 'spec')",
    )
    parser.add_argument(
        "--eval-env", type=str, default="modal",
        choices=["docker", "modal"],
        help="Environment for eval step (default: modal)",
    )
    parser.add_argument(
        "--eval-model", type=str, default="anthropic/claude-opus-4-7",
        help="Model for the evaluation agent (default: claude-opus-4-7)",
    )
    parser.add_argument(
        "--eval-trials", type=int, default=1,
        help="Number of parallel eval trials to run (default: 1)",
    )
    args = parser.parse_args()

    models = args.models or MODELS

    # ── Single step mode ──
    if args.step:
        if args.step == "spec":
            force_broken = True if args.broken else (False if args.clean else None)
            step_spec(args.spec_model, force_broken, force_language=args.language)
            return

        if not args.workspace:
            log.error(f"--step {args.step} requires a workspace directory argument")
            sys.exit(1)
        workspace = Path(args.workspace)
        if not workspace.exists():
            log.error(f"Workspace not found: {workspace}")
            sys.exit(1)

        log.info(f"Running step '{args.step}' on {workspace}")
        if args.step == "build":
            step_build(workspace, models, args.max_iterations)
        elif args.step == "judge":
            step_judge(workspace, models)
        elif args.step == "screenshot":
            step_screenshot(workspace)
        elif args.step == "package":
            step_package(workspace)
        elif args.step == "eval":
            step_eval(workspace, model=args.eval_model, env=args.eval_env, trials=args.eval_trials)
        return

    # ── Full pipeline ──
    TASKS_DIR.mkdir(parents=True, exist_ok=True)

    log.info("Pipeline Configuration:")
    log.info(f"  Tasks to generate: {args.count}")
    log.info(f"  Models: {models}")
    log.info(f"  Max iterations: {args.max_iterations}")
    log.info(f"  Output: {TASKS_DIR}")

    # Phase 1: Generate specs
    log.info(f"{'='*60}")
    log.info(f"Phase 1: Generating {args.count} website specifications...")
    log.info(f"{'='*60}")

    if args.broken:
        force_broken = True
        broken_count = None
    elif args.clean:
        force_broken = False
        broken_count = 0
    else:
        force_broken = None
        broken_count = args.broken_count

    if args.count == 1:
        spec = generate_spec(
            model=args.spec_model,
            force_broken=force_broken if force_broken is not None else None,
            force_language=args.language,
        )
        specs = [spec]
    else:
        specs = generate_specs_batch(
            count=args.count,
            model=args.spec_model,
            broken_count=broken_count,
            force_language=args.language,
        )

    log.info(f"Generated {len(specs)} specs")
    for i, s in enumerate(specs):
        log.info(f"  {i+1}. {s['site_name']} ({s['category']}) "
                 f"{'[BROKEN]' if s.get('is_broken') else '[CLEAN]'}")

    # Phase 2: Generate websites and package tasks
    log.info(f"{'='*60}")
    log.info(f"Phase 2: Generating websites and packaging tasks...")
    log.info(f"{'='*60}")

    successful_tasks = []
    for i, spec in enumerate(specs):
        log.info(f"--- Task {i+1}/{len(specs)} ---")
        task_dir = generate_single_task(
            spec=spec,
            models=models,
            max_iterations=args.max_iterations,
        )
        if task_dir:
            successful_tasks.append(task_dir)

    # Summary
    log.info(f"{'='*60}")
    log.info("Pipeline Complete!")
    log.info(f"{'='*60}")
    log.info(f"  Attempted: {len(specs)}")
    log.info(f"  Successful: {len(successful_tasks)}")
    log.info(f"  Failed: {len(specs) - len(successful_tasks)}")
    log.info("Generated tasks:")
    for t in successful_tasks:
        log.info(f"  - {t}")

    log.info(f"To run evaluation:")
    log.info(f"  harbor run -p {TASKS_DIR} --agent claude-code "
             f"--model anthropic/claude-opus-4-7 --n-concurrent 4")


if __name__ == "__main__":
    main()
