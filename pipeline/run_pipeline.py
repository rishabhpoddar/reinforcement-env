#!/usr/bin/env python3
"""Pipeline orchestrator — generates web design replication tasks end-to-end.

Usage:
    python -m pipeline.run_pipeline --count 10
    python -m pipeline.run_pipeline --count 1 --broken  # Force broken website
    python -m pipeline.run_pipeline --count 10 --broken-count 3  # 3 of 10 are broken
"""

import argparse
import json
import sys
from pathlib import Path

# Ensure project root is in path
sys.path.insert(0, str(Path(__file__).parent.parent))

from pipeline.config import MODELS, TASKS_DIR, GENERATED_DIR
from pipeline.generate.spec_generator import generate_spec, generate_specs_batch
from pipeline.generate.generation_loop import generate_website
from pipeline.generate.screenshot import capture_screenshots_sync
from pipeline.package.harbor_task import package_task


def generate_single_task(
    spec: dict,
    models: list[str] | None = None,
    max_iterations: int = 5,
) -> Path | None:
    """Generate a single Harbor task from a website spec.

    Returns the task directory path, or None on failure.
    """
    models = models or MODELS
    site_name = spec.get("site_name", "unknown")
    category = spec.get("category", "unknown")

    print(f"\n{'='*60}")
    print(f"Generating: {site_name} ({category})")
    print(f"  Pages: {', '.join(spec.get('pages', []))}")
    print(f"  Broken: {spec.get('is_broken', False)}")
    print(f"{'='*60}")

    # Use a persistent directory under generated/ so files are inspectable
    slug = f"{category}-{site_name}".replace(" ", "-").lower()[:50]
    gen_dir = GENERATED_DIR / slug
    site_dir = gen_dir / "site"
    screenshots_dir = gen_dir / "screenshots"
    site_dir.mkdir(parents=True, exist_ok=True)
    screenshots_dir.mkdir(parents=True, exist_ok=True)

    # Save spec for reference
    (gen_dir / "spec.json").write_text(json.dumps(spec, indent=2))

    # Step 1: Generate website via builder+judge loop
    print("\n[1/3] Running builder + judge generation loop...")
    gen_metadata = generate_website(
        spec=spec,
        output_dir=site_dir,
        models=models,
        max_iterations=max_iterations,
    )

    # Verify we got some HTML files
    html_files = list(site_dir.glob("*.html"))
    if not html_files:
        print(f"  ERROR: No HTML files generated. Skipping.")
        return None

    css_files = list(site_dir.glob("*.css"))
    print(f"  Generated {len(html_files)} HTML files + {len(css_files)} CSS file(s)")

    # Step 2: Capture reference screenshots
    print("\n[2/3] Capturing reference screenshots...")
    try:
        screenshots = capture_screenshots_sync(site_dir, screenshots_dir)
        total = sum(len(v) for v in screenshots.values())
        print(f"  Captured {total} screenshots across {len(screenshots)} pages")
    except Exception as e:
        print(f"  ERROR capturing screenshots: {e}")
        return None

    # Step 3: Package as Harbor task
    print("\n[3/3] Packaging Harbor task...")
    try:
        task_dir = package_task(
            spec=spec,
            site_dir=site_dir,
            screenshots_dir=screenshots_dir,
            generation_metadata=gen_metadata,
        )
        print(f"  Task created: {task_dir}")
        return task_dir
    except Exception as e:
        print(f"  ERROR packaging task: {e}")
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
        "--spec-model", type=str, default="claude-sonnet-4-6",
        help="Anthropic model for spec generation",
    )
    args = parser.parse_args()

    models = args.models or MODELS
    TASKS_DIR.mkdir(parents=True, exist_ok=True)

    print(f"Pipeline Configuration:")
    print(f"  Tasks to generate: {args.count}")
    print(f"  Models: {models}")
    print(f"  Max iterations: {args.max_iterations}")
    print(f"  Output: {TASKS_DIR}")

    # Step 1: Generate specs
    print(f"\n{'='*60}")
    print(f"Phase 1: Generating {args.count} website specifications...")
    print(f"{'='*60}")

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
        )
        specs = [spec]
    else:
        specs = generate_specs_batch(
            count=args.count,
            model=args.spec_model,
            broken_count=broken_count,
        )

    print(f"\nGenerated {len(specs)} specs")
    for i, s in enumerate(specs):
        print(f"  {i+1}. {s['site_name']} ({s['category']}) "
              f"{'[BROKEN]' if s.get('is_broken') else '[CLEAN]'}")

    # Step 2: Generate websites and package tasks
    print(f"\n{'='*60}")
    print(f"Phase 2: Generating websites and packaging tasks...")
    print(f"{'='*60}")

    successful_tasks = []
    for i, spec in enumerate(specs):
        print(f"\n--- Task {i+1}/{len(specs)} ---")
        task_dir = generate_single_task(
            spec=spec,
            models=models,
            max_iterations=args.max_iterations,
        )
        if task_dir:
            successful_tasks.append(task_dir)

    # Summary
    print(f"\n{'='*60}")
    print(f"Pipeline Complete!")
    print(f"{'='*60}")
    print(f"  Attempted: {len(specs)}")
    print(f"  Successful: {len(successful_tasks)}")
    print(f"  Failed: {len(specs) - len(successful_tasks)}")
    print(f"\nGenerated tasks:")
    for t in successful_tasks:
        print(f"  - {t}")

    print(f"\nTo run evaluation:")
    print(f"  harbor run -p {TASKS_DIR} --agent claude-code "
          f"--model anthropic/claude-opus-4-7 --n-concurrent 4")


if __name__ == "__main__":
    main()
