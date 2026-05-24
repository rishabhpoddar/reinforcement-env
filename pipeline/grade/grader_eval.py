#!/usr/bin/env python3
"""Thin wrapper around harbor_grader.py for local evaluation.

Sets up environment variables from pipeline config and provides a
grade_submission() interface that works with pre-captured screenshots
(used by the calibration pipeline).
"""

import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent.parent))

from pipeline.config import get_anthropic_key, get_openai_key

# Set env vars so harbor_grader.py can read them via os.environ
os.environ["ANTHROPIC_API_KEY"] = get_anthropic_key()
os.environ["OPENAI_API_KEY"] = get_openai_key()

# Import from the canonical grader
from pipeline.package.harbor_grader import (  # noqa: E402
    check_for_hacks,
    check_structural,
)

import asyncio


def grade_submission(
    reference_dir: Path,
    submission_dir: Path,
    sub_screenshots_dir: Path,
    meta: dict,
) -> dict:
    """Grade a submission using pre-captured screenshots.

    This wraps harbor_grader's async grading but skips Playwright screenshot
    capture (since screenshots are already provided).
    """
    # harbor_grader._grade_async captures screenshots itself, but for local
    # calibration we already have them. We use the same async core but point
    # the submission screenshots dir to the pre-captured one.
    #
    # The simplest approach: temporarily symlink or just call _grade_async
    # with a dummy output path, since it captures screenshots to
    # /logs/verifier/screenshots which doesn't exist locally.
    #
    # Instead, we re-implement the orchestration thinly using harbor_grader's
    # building blocks.
    from pipeline.package.harbor_grader import (
        ZERO_SCORES,
        VIEWPORTS_DEFAULT,
        MAX_CONCURRENT_LLM,
        _score_single_pair,
        _grade_defect_replication,
        _grade_defect_identification,
    )
    import numpy as np

    async def _run():
        pages = meta.get("pages", [])
        viewports = meta.get("viewports", VIEWPORTS_DEFAULT)

        if check_for_hacks(submission_dir):
            return {
                "overall": 0.0,
                "hack_detected": True,
                "structural": 0.0,
                "pixel_ssim": 0.0,
                "pixel_color": 0.0,
                "pixel_combined": 0.0,
                "llm_layout": 0.0,
                "llm_color": 0.0,
                "llm_typography": 0.0,
                "llm_spacing": 0.0,
                "llm_components": 0.0,
                "llm_avg": 0.0,
            }

        structural = check_structural(submission_dir, pages)
        semaphore = asyncio.Semaphore(MAX_CONCURRENT_LLM)

        tasks = []
        pair_keys = []
        for page in pages:
            for vp_name in viewports:
                ref_path = reference_dir / f"{page}-{vp_name}.png"
                sub_path = sub_screenshots_dir / f"{page}-{vp_name}.png"
                if not ref_path.exists() or not sub_path.exists():
                    pair_keys.append((page, vp_name, False))
                    tasks.append(None)
                else:
                    pair_keys.append((page, vp_name, True))
                    tasks.append(_score_single_pair(str(ref_path), str(sub_path), page, vp_name, semaphore))

        real_tasks = [t for t in tasks if t is not None]
        real_results = await asyncio.gather(*real_tasks, return_exceptions=True) if real_tasks else []

        all_llm, all_pixel = [], []
        real_idx = 0
        per_page_scores = {}
        for page, vp_name, valid in pair_keys:
            if page not in per_page_scores:
                per_page_scores[page] = {}
            if not valid:
                per_page_scores[page][vp_name] = 0.0
                all_llm.append(dict(ZERO_SCORES))
                all_pixel.append({"ssim": 0.0, "color_histogram": 0.0, "pixel_combined": 0.0})
            else:
                r = real_results[real_idx]
                real_idx += 1
                if isinstance(r, Exception):
                    print(f"Scoring failed for {page}/{vp_name}: {r}", file=sys.stderr)
                    all_llm.append(dict(ZERO_SCORES))
                    all_pixel.append({"ssim": 0.0, "color_histogram": 0.0, "pixel_combined": 0.0})
                    per_page_scores[page][vp_name] = 0.0
                else:
                    llm_scores, pixel_scores = r
                    all_llm.append(llm_scores)
                    all_pixel.append(pixel_scores)
                    llm_avg = sum(llm_scores.values()) / len(llm_scores) if llm_scores else 0.0
                    per_page_scores[page][vp_name] = round(float(llm_avg), 3)

        llm_agg = {k: float(sum(s.get(k, 0.0) for s in all_llm) / len(all_llm)) for k in ZERO_SCORES} if all_llm else dict(ZERO_SCORES)
        avg_llm = float(sum(llm_agg.values()) / len(llm_agg)) if llm_agg else 0.0
        avg_ssim = float(np.mean([p["ssim"] for p in all_pixel])) if all_pixel else 0.0
        avg_color = float(np.mean([p["color_histogram"] for p in all_pixel])) if all_pixel else 0.0
        avg_pixel = float(np.mean([p["pixel_combined"] for p in all_pixel])) if all_pixel else 0.0

        visual_fidelity = 0.70 * avg_llm + 0.15 * avg_pixel + 0.15 * structural

        result = {
            "hack_detected": False,
            "structural": round(structural, 4),
            "pixel_ssim": round(avg_ssim, 4),
            "pixel_color": round(avg_color, 4),
            "pixel_combined": round(avg_pixel, 4),
            "llm_layout": round(llm_agg.get("layout", 0), 4),
            "llm_color": round(llm_agg.get("color", 0), 4),
            "llm_typography": round(llm_agg.get("typography", 0), 4),
            "llm_spacing": round(llm_agg.get("spacing", 0), 4),
            "llm_components": round(llm_agg.get("components", 0), 4),
            "llm_avg": round(avg_llm, 4),
            "visual_fidelity": round(float(visual_fidelity), 4),
            "per_page": per_page_scores,
        }

        is_broken = meta.get("is_broken", False)
        defects = meta.get("defects", [])
        if is_broken and defects:
            defect_rep, defect_id = await asyncio.gather(
                _grade_defect_replication(reference_dir, sub_screenshots_dir, defects, semaphore),
                _grade_defect_identification(submission_dir, defects, semaphore),
            )
            rep_score = defect_rep.get("defect_replication", 0.0)
            id_score = defect_id.get("defect_identification", 0.0)
            overall = 0.50 * visual_fidelity + 0.25 * rep_score + 0.25 * id_score
            result["defect_replication"] = round(rep_score, 4)
            result["defect_replication_per_defect"] = defect_rep.get("per_defect", [])
            result["defect_identification"] = round(id_score, 4)
            result["defect_id_details"] = {k: v for k, v in defect_id.items() if k != "defect_identification"}
        else:
            overall = visual_fidelity

        result["overall"] = round(float(overall), 4)
        return result

    try:
        loop = asyncio.get_running_loop()
    except RuntimeError:
        loop = None

    if loop and loop.is_running():
        import concurrent.futures
        with concurrent.futures.ThreadPoolExecutor(max_workers=1) as pool:
            return pool.submit(asyncio.run, _run()).result()
    else:
        return asyncio.run(_run())
