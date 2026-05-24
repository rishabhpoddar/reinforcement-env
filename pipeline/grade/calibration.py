#!/usr/bin/env python3
"""Grader calibration pipeline.

Creates degraded versions of reference websites at known quality tiers,
runs the grader on each, and measures how well the grader's scores
correlate with the expected quality ordering.

Usage:
    # Generate calibration set from all generated sites
    python -m pipeline.grade.calibration generate

    # Generate for a specific site
    python -m pipeline.grade.calibration generate generated/literary-community-inkwell-\&-ember

    # Run grader on calibration set
    python -m pipeline.grade.calibration grade

    # Analyze results
    python -m pipeline.grade.calibration analyze
"""

import argparse
import asyncio
import copy
import json
import os
import random
import re
import shutil
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent.parent))

from pipeline.config import VIEWPORTS, GENERATED_DIR, PROJECT_ROOT, log
from pipeline.generate.screenshot import capture_screenshots_sync


# ──────────────────────────────────────────────────
# Tier definitions — expected quality ordering
# ──────────────────────────────────────────────────

TIERS = {
    0: {"name": "perfect",  "expected_score": 1.0,  "description": "Exact copy of reference"},
    1: {"name": "good",     "expected_score": 0.8,  "description": "Minor CSS tweaks (color shift, small spacing changes)"},
    2: {"name": "mediocre", "expected_score": 0.5,  "description": "Major CSS changes (wrong fonts, big color shifts, layout changes)"},
    3: {"name": "bad",      "expected_score": 0.2,  "description": "HTML structure only, CSS mostly stripped"},
    4: {"name": "hack",     "expected_score": 0.0,  "description": "Reference screenshot embedded as <img>"},
    5: {"name": "empty",    "expected_score": 0.0,  "description": "No files or minimal stub"},
}

CALIBRATION_DIR = PROJECT_ROOT / "calibration"


# ──────────────────────────────────────────────────
# CSS manipulation utilities
# ──────────────────────────────────────────────────

def _shift_hex_color(hex_color: str, amount: int) -> str:
    """Shift a hex color's RGB channels by amount (can be negative)."""
    hex_color = hex_color.lstrip("#")
    if len(hex_color) == 3:
        hex_color = "".join(c * 2 for c in hex_color)
    if len(hex_color) != 6:
        return f"#{hex_color}"
    r = max(0, min(255, int(hex_color[0:2], 16) + amount))
    g = max(0, min(255, int(hex_color[2:4], 16) + amount))
    b = max(0, min(255, int(hex_color[4:6], 16) + amount))
    return f"#{r:02x}{g:02x}{b:02x}"


def _shift_colors_in_css(css: str, amount: int) -> str:
    """Shift all hex colors in CSS by amount."""
    def replacer(m):
        return _shift_hex_color(m.group(0), amount)
    return re.sub(r"#[0-9a-fA-F]{3,6}\b", replacer, css)


def _scale_numeric_values(css: str, factor: float, units: list[str] = None) -> str:
    """Scale numeric values with given units in CSS."""
    if units is None:
        units = ["px", "rem", "em"]
    pattern = r"(\d+(?:\.\d+)?)\s*(" + "|".join(re.escape(u) for u in units) + r")"
    def replacer(m):
        val = float(m.group(1)) * factor
        return f"{val:.1f}{m.group(2)}"
    return re.sub(pattern, replacer, css)


def _replace_font_families(css: str) -> str:
    """Replace all font-family declarations with wrong fonts."""
    # Swap serif ↔ monospace to make it visually obvious
    css = re.sub(
        r"font-family:\s*[^;]+;",
        'font-family: "Courier New", monospace;',
        css,
    )
    # Also swap CSS variable-based font assignments
    css = re.sub(r"var\(--serif\)", '"Courier New", monospace', css)
    css = re.sub(r"var\(--sans\)", '"Times New Roman", serif', css)
    return css


def _invert_colors(css: str) -> str:
    """Drastically change colors by inverting hex values."""
    def replacer(m):
        hex_color = m.group(0).lstrip("#")
        if len(hex_color) == 3:
            hex_color = "".join(c * 2 for c in hex_color)
        if len(hex_color) != 6:
            return m.group(0)
        r = 255 - int(hex_color[0:2], 16)
        g = 255 - int(hex_color[2:4], 16)
        b = 255 - int(hex_color[4:6], 16)
        return f"#{r:02x}{g:02x}{b:02x}"
    return re.sub(r"#[0-9a-fA-F]{3,6}\b", replacer, css)


def _strip_css_to_minimal(css: str) -> str:
    """Strip CSS down to just basic resets — no colors, fonts, layout."""
    return """* { box-sizing: border-box; margin: 0; padding: 0; }
body { font-family: sans-serif; padding: 16px; }
a { color: blue; }
img { max-width: 100%; }
"""


# ──────────────────────────────────────────────────
# Tier generators
# ──────────────────────────────────────────────────

def _create_tier_0_perfect(site_dir: Path, output_dir: Path):
    """Exact copy of reference files."""
    shutil.copytree(site_dir, output_dir, dirs_exist_ok=True)


def _create_tier_1_good(site_dir: Path, output_dir: Path):
    """Minor degradation: slight color shifts, small spacing changes."""
    shutil.copytree(site_dir, output_dir, dirs_exist_ok=True)
    css_path = output_dir / "styles.css"
    if css_path.exists():
        css = css_path.read_text()
        # Shift colors slightly (±15 on RGB channels)
        css = _shift_colors_in_css(css, 15)
        # Slightly adjust spacing (±10%)
        css = _scale_numeric_values(css, 1.1, ["px"])
        css_path.write_text(css)


def _create_tier_2_mediocre(site_dir: Path, output_dir: Path):
    """Major degradation: wrong fonts, inverted colors, doubled spacing."""
    shutil.copytree(site_dir, output_dir, dirs_exist_ok=True)
    css_path = output_dir / "styles.css"
    if css_path.exists():
        css = css_path.read_text()
        css = _replace_font_families(css)
        css = _shift_colors_in_css(css, 60)
        css = _scale_numeric_values(css, 1.8, ["px", "rem", "em"])
        # Remove border-radius to flatten design
        css = re.sub(r"border-radius:\s*[^;]+;", "border-radius: 0;", css)
        css_path.write_text(css)


def _create_tier_3_bad(site_dir: Path, output_dir: Path):
    """HTML structure only, CSS gutted to minimal reset."""
    shutil.copytree(site_dir, output_dir, dirs_exist_ok=True)
    css_path = output_dir / "styles.css"
    if css_path.exists():
        css_path.write_text(_strip_css_to_minimal(css_path.read_text()))


def _create_tier_4_hack(site_dir: Path, output_dir: Path, reference_screenshots_dir: Path):
    """Embed reference screenshots as <img> tags instead of building HTML."""
    output_dir.mkdir(parents=True, exist_ok=True)

    # Copy screenshots into the output dir for reference
    screenshots_in_output = output_dir / "_ref_imgs"
    screenshots_in_output.mkdir(exist_ok=True)
    for png in reference_screenshots_dir.glob("*.png"):
        shutil.copy2(png, screenshots_in_output / png.name)

    # Create HTML files that just show the reference screenshot
    for html_file in site_dir.glob("*.html"):
        page_name = html_file.stem
        desktop_img = f"_ref_imgs/{page_name}-desktop.png"
        hack_html = f"""<!DOCTYPE html>
<html><head><title>{page_name}</title>
<link rel="stylesheet" href="styles.css">
</head><body>
<img src="{desktop_img}" style="width:100%;height:auto;">
</body></html>"""
        (output_dir / html_file.name).write_text(hack_html)

    # Minimal CSS
    (output_dir / "styles.css").write_text("body { margin: 0; padding: 0; }")


def _create_tier_5_empty(site_dir: Path, output_dir: Path):
    """Empty submission — just a stub index."""
    output_dir.mkdir(parents=True, exist_ok=True)
    (output_dir / "home.html").write_text(
        "<!DOCTYPE html><html><body><p>TODO</p></body></html>"
    )


# ──────────────────────────────────────────────────
# Generate calibration set
# ──────────────────────────────────────────────────

def generate_calibration_set(workspace_dir: Path) -> Path:
    """Generate all quality tiers for a single reference site.

    Args:
        workspace_dir: Path to generated workspace (contains site/ and screenshots/).

    Returns:
        Path to the calibration directory for this site.
    """
    site_dir = workspace_dir / "site"
    screenshots_dir = workspace_dir / "screenshots"
    site_name = workspace_dir.name

    if not site_dir.exists() or not list(site_dir.glob("*.html")):
        raise FileNotFoundError(f"No HTML files in {site_dir}")

    # Generate screenshots if missing
    if not screenshots_dir.exists() or not list(screenshots_dir.glob("*.png")):
        log.info(f"  Capturing reference screenshots for {site_name}...")
        capture_screenshots_sync(site_dir, screenshots_dir)

    cal_site_dir = CALIBRATION_DIR / site_name
    cal_site_dir.mkdir(parents=True, exist_ok=True)

    # Copy reference screenshots
    ref_screenshots_dir = cal_site_dir / "reference_screenshots"
    if ref_screenshots_dir.exists():
        shutil.rmtree(ref_screenshots_dir)
    shutil.copytree(screenshots_dir, ref_screenshots_dir)

    # Save metadata
    spec_path = workspace_dir / "spec.json"
    pages = [f.stem for f in sorted(site_dir.glob("*.html"))]
    spec = {}
    if spec_path.exists():
        spec = json.loads(spec_path.read_text())

    meta = {
        "pages": pages,
        "viewports": {k: v for k, v in VIEWPORTS.items()},
        "is_broken": spec.get("is_broken", False),
        "defects": spec.get("defects", []),
        "source_workspace": str(workspace_dir),
        "spec": spec,
    }
    (cal_site_dir / "task_meta.json").write_text(json.dumps(meta, indent=2))

    # Generate each tier
    generators = {
        0: lambda out: _create_tier_0_perfect(site_dir, out),
        1: lambda out: _create_tier_1_good(site_dir, out),
        2: lambda out: _create_tier_2_mediocre(site_dir, out),
        3: lambda out: _create_tier_3_bad(site_dir, out),
        4: lambda out: _create_tier_4_hack(site_dir, out, screenshots_dir),
        5: lambda out: _create_tier_5_empty(site_dir, out),
    }

    for tier_id, generator in generators.items():
        tier_info = TIERS[tier_id]
        tier_dir = cal_site_dir / f"tier-{tier_id}-{tier_info['name']}"

        # Clean and regenerate
        if tier_dir.exists():
            shutil.rmtree(tier_dir)

        submission_dir = tier_dir / "submission"
        submission_dir.mkdir(parents=True, exist_ok=True)

        log.info(f"  Tier {tier_id} ({tier_info['name']}): {tier_info['description']}")
        generator(submission_dir)

        # Capture screenshots of the degraded submission
        screenshots_out = tier_dir / "screenshots"
        try:
            capture_screenshots_sync(submission_dir, screenshots_out)
        except Exception as e:
            log.warning(f"    Screenshot capture failed for tier {tier_id}: {e}")
            screenshots_out.mkdir(exist_ok=True)

        # Save tier metadata
        tier_meta = {
            "tier": tier_id,
            "name": tier_info["name"],
            "expected_score": tier_info["expected_score"],
            "description": tier_info["description"],
        }
        (tier_dir / "tier_meta.json").write_text(json.dumps(tier_meta, indent=2))

    log.info(f"  Calibration set created: {cal_site_dir}")
    return cal_site_dir


def generate_all_calibration_sets():
    """Generate calibration sets for all generated sites."""
    gen_dirs = sorted(
        d for d in GENERATED_DIR.iterdir()
        if d.is_dir() and (d / "site").exists() and d.name != "spec_history.json"
    )

    if not gen_dirs:
        log.error("No generated sites found in generated/")
        return

    log.info(f"Generating calibration sets for {len(gen_dirs)} sites...")
    for workspace_dir in gen_dirs:
        log.info(f"\n{'='*60}")
        log.info(f"Site: {workspace_dir.name}")
        log.info(f"{'='*60}")
        try:
            generate_calibration_set(workspace_dir)
        except Exception as e:
            log.error(f"  Failed: {e}")


# ──────────────────────────────────────────────────
# Run grader on calibration set
# ──────────────────────────────────────────────────

def run_grader_on_calibration():
    """Run the grader on all calibration submissions and save results."""
    # Import grader functions from harbor_task.py (they're embedded as strings there,
    # so we need to use the standalone grader logic)
    from pipeline.grade.grader_eval import grade_submission

    if not CALIBRATION_DIR.exists():
        log.error("No calibration directory found. Run 'generate' first.")
        return

    results = []

    for site_dir in sorted(CALIBRATION_DIR.iterdir()):
        if not site_dir.is_dir():
            continue

        meta_path = site_dir / "task_meta.json"
        ref_dir = site_dir / "reference_screenshots"
        if not meta_path.exists() or not ref_dir.exists():
            continue

        meta = json.loads(meta_path.read_text())
        log.info(f"\n{'='*60}")
        log.info(f"Grading: {site_dir.name}")
        log.info(f"{'='*60}")

        for tier_dir in sorted(site_dir.iterdir()):
            if not tier_dir.is_dir() or not tier_dir.name.startswith("tier-"):
                continue

            tier_meta = json.loads((tier_dir / "tier_meta.json").read_text())
            submission_dir = tier_dir / "submission"
            sub_screenshots_dir = tier_dir / "screenshots"

            log.info(f"  Tier {tier_meta['tier']} ({tier_meta['name']})...")

            try:
                grader_result = grade_submission(
                    reference_dir=ref_dir,
                    submission_dir=submission_dir,
                    sub_screenshots_dir=sub_screenshots_dir,
                    meta=meta,
                )
            except Exception as e:
                log.error(f"    Grader failed: {e}")
                grader_result = {"overall": -1, "error": str(e)}

            result_entry = {
                "site": site_dir.name,
                "tier": tier_meta["tier"],
                "tier_name": tier_meta["name"],
                "expected_score": tier_meta["expected_score"],
                "actual_score": grader_result.get("overall", -1),
                "grader_details": grader_result,
            }
            results.append(result_entry)
            log.info(f"    Expected: {tier_meta['expected_score']:.2f}  "
                     f"Actual: {grader_result.get('overall', -1):.3f}")

            # Save per-tier result
            (tier_dir / "grader_result.json").write_text(
                json.dumps(grader_result, indent=2)
            )

    # Save all results
    results_path = CALIBRATION_DIR / "grader_results.json"
    results_path.write_text(json.dumps(results, indent=2))
    log.info(f"\nResults saved to {results_path}")
    return results


# ──────────────────────────────────────────────────
# Analyze grader quality
# ──────────────────────────────────────────────────

def analyze_results():
    """Analyze grader calibration results and produce a quality report."""
    results_path = CALIBRATION_DIR / "grader_results.json"
    if not results_path.exists():
        log.error("No results found. Run 'grade' first.")
        return

    results = json.loads(results_path.read_text())

    # Filter out errors
    valid = [r for r in results if r["actual_score"] >= 0]
    if not valid:
        log.error("No valid results to analyze.")
        return

    # ── 1. Rank correlation (Spearman's rho) ──
    # Group by site, compute per-site correlation, then average
    from collections import defaultdict
    by_site = defaultdict(list)
    for r in valid:
        by_site[r["site"]].append(r)

    correlations = []
    for site, site_results in by_site.items():
        # Sort by tier (expected ordering)
        site_results.sort(key=lambda x: x["tier"])
        expected_ranks = list(range(len(site_results)))
        # Rank by actual score (descending — higher score = better = lower tier)
        actual_scores = [r["actual_score"] for r in site_results]
        actual_ranked = sorted(range(len(actual_scores)),
                               key=lambda i: -actual_scores[i])
        actual_ranks = [0] * len(actual_ranked)
        for rank, idx in enumerate(actual_ranked):
            actual_ranks[idx] = rank

        # Spearman correlation
        n = len(expected_ranks)
        if n < 3:
            continue
        d_sq = sum((e - a) ** 2 for e, a in zip(expected_ranks, actual_ranks))
        rho = 1 - (6 * d_sq) / (n * (n**2 - 1))
        correlations.append(rho)

    avg_correlation = sum(correlations) / len(correlations) if correlations else 0

    # ── 2. Tier separation ──
    tier_scores = defaultdict(list)
    for r in valid:
        tier_scores[r["tier"]].append(r["actual_score"])

    tier_means = {}
    for tier in sorted(tier_scores.keys()):
        scores = tier_scores[tier]
        tier_means[tier] = sum(scores) / len(scores)

    # Check monotonicity: each tier should score lower than the previous
    monotonic_pairs = 0
    total_pairs = 0
    tiers_sorted = sorted(tier_means.keys())
    for i in range(len(tiers_sorted) - 1):
        total_pairs += 1
        if tier_means[tiers_sorted[i]] > tier_means[tiers_sorted[i + 1]]:
            monotonic_pairs += 1
    monotonicity = monotonic_pairs / total_pairs if total_pairs > 0 else 0

    # Average gap between adjacent tiers
    gaps = []
    for i in range(len(tiers_sorted) - 1):
        gap = tier_means[tiers_sorted[i]] - tier_means[tiers_sorted[i + 1]]
        gaps.append(gap)
    avg_gap = sum(gaps) / len(gaps) if gaps else 0

    # ── 3. Hack rejection ──
    hack_scores = tier_scores.get(4, [])
    hack_rejected = sum(1 for s in hack_scores if s < 0.1) / len(hack_scores) if hack_scores else 0

    # ── 4. Empty rejection ──
    empty_scores = tier_scores.get(5, [])
    empty_rejected = sum(1 for s in empty_scores if s < 0.1) / len(empty_scores) if empty_scores else 0

    # ── 5. Perfect recognition ──
    perfect_scores = tier_scores.get(0, [])
    perfect_high = sum(1 for s in perfect_scores if s > 0.8) / len(perfect_scores) if perfect_scores else 0

    # ── Report ──
    report = f"""
{'='*60}
GRADER CALIBRATION REPORT
{'='*60}

OVERALL QUALITY
  Rank correlation (Spearman ρ):  {avg_correlation:.3f}  (1.0 = perfect)
  Monotonicity:                   {monotonicity:.1%}  (% of adjacent tiers correctly ordered)
  Avg gap between tiers:          {avg_gap:.3f}  (higher = better separation)

TIER SCORES (mean)
"""
    for tier in tiers_sorted:
        scores = tier_scores[tier]
        mean = tier_means[tier]
        std = (sum((s - mean)**2 for s in scores) / len(scores)) ** 0.5 if len(scores) > 1 else 0
        tier_name = TIERS[tier]["name"]
        expected = TIERS[tier]["expected_score"]
        report += f"  Tier {tier} ({tier_name:>8}):  {mean:.3f} ± {std:.3f}  (expected ~{expected})\n"

    report += f"""
CRITICAL CHECKS
  Hack rejection (tier 4 < 0.1):  {hack_rejected:.0%}  ({len(hack_scores)} samples)
  Empty rejection (tier 5 < 0.1): {empty_rejected:.0%}  ({len(empty_scores)} samples)
  Perfect recognition (tier 0 > 0.8): {perfect_high:.0%}  ({len(perfect_scores)} samples)

SCORE DISTRIBUTION BY TIER
"""
    for tier in tiers_sorted:
        scores = tier_scores[tier]
        tier_name = TIERS[tier]["name"]
        bar_scores = sorted(scores)
        report += f"  Tier {tier} ({tier_name:>8}): {' '.join(f'{s:.2f}' for s in bar_scores)}\n"

    report += f"""
{'='*60}
SITES ANALYZED: {len(by_site)}
TOTAL SUBMISSIONS GRADED: {len(valid)}
{'='*60}
"""

    print(report)

    # Save report
    report_path = CALIBRATION_DIR / "calibration_report.txt"
    report_path.write_text(report)

    # Save structured summary
    summary = {
        "rank_correlation": avg_correlation,
        "monotonicity": monotonicity,
        "avg_tier_gap": avg_gap,
        "hack_rejection_rate": hack_rejected,
        "empty_rejection_rate": empty_rejected,
        "perfect_recognition_rate": perfect_high,
        "tier_means": {str(k): v for k, v in tier_means.items()},
        "n_sites": len(by_site),
        "n_submissions": len(valid),
    }
    (CALIBRATION_DIR / "calibration_summary.json").write_text(
        json.dumps(summary, indent=2)
    )
    log.info(f"Report saved to {report_path}")


# ──────────────────────────────────────────────────
# CLI
# ──────────────────────────────────────────────────

def main():
    parser = argparse.ArgumentParser(description="Grader calibration pipeline")
    parser.add_argument(
        "command",
        choices=["generate", "grade", "analyze", "all"],
        help="generate = create degraded submissions, grade = run grader, analyze = compute metrics, all = do everything",
    )
    parser.add_argument(
        "workspace",
        nargs="?",
        default=None,
        help="Optional: specific workspace to generate calibration for",
    )
    args = parser.parse_args()

    if args.command == "generate":
        if args.workspace:
            workspace = Path(args.workspace)
            if not workspace.exists():
                log.error(f"Workspace not found: {workspace}")
                sys.exit(1)
            generate_calibration_set(workspace)
        else:
            generate_all_calibration_sets()

    elif args.command == "grade":
        run_grader_on_calibration()

    elif args.command == "analyze":
        analyze_results()

    elif args.command == "all":
        if args.workspace:
            generate_calibration_set(Path(args.workspace))
        else:
            generate_all_calibration_sets()
        run_grader_on_calibration()
        analyze_results()


if __name__ == "__main__":
    main()
