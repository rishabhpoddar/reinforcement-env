#!/usr/bin/env python3
"""Standalone grader for local evaluation (outside Harbor container).

This mirrors the grading logic from harbor_task.py but works locally
with pre-captured screenshots. Used by the calibration pipeline.

Scoring components:
  - Dual LLM judges (Claude Opus 4.7 + GPT-5.5), averaged (70% weight)
  - Deterministic pixel metrics: SSIM + color histogram (15% weight)
  - Structural checks: files exist, nav links, stylesheet (15% weight)

All LLM calls and per-pair scoring are parallelized via asyncio.
"""

import asyncio
import base64
import io
import json
import re
import sys
from pathlib import Path

import numpy as np
from PIL import Image
from skimage.metrics import structural_similarity as ssim

sys.path.insert(0, str(Path(__file__).parent.parent.parent))

from pipeline.config import VIEWPORTS, get_anthropic_key, get_openai_key

# Max concurrent LLM calls (avoid rate limits)
MAX_CONCURRENT_LLM = 10


# ──────────────────────────────────────────────────
# Image utilities
# ──────────────────────────────────────────────────

def _load_image_rgb(path: str) -> np.ndarray:
    """Load image as RGB numpy array."""
    return np.array(Image.open(path).convert("RGB"))


def _resize_to_match(img_a: np.ndarray, img_b: np.ndarray) -> tuple[np.ndarray, np.ndarray]:
    """Resize img_b to match img_a dimensions for pixel comparison."""
    if img_a.shape == img_b.shape:
        return img_a, img_b
    h, w = img_a.shape[:2]
    img_b_pil = Image.fromarray(img_b).resize((w, h), Image.LANCZOS)
    return img_a, np.array(img_b_pil)


def _resize_image_for_api(image_path: str, max_height: int = 7000) -> bytes:
    """Read an image and resize if taller than max_height (API limit)."""
    img = Image.open(image_path)
    if img.height > max_height:
        ratio = max_height / img.height
        new_width = int(img.width * ratio)
        img = img.resize((new_width, max_height), Image.LANCZOS)
    buf = io.BytesIO()
    img.save(buf, format="PNG")
    return buf.getvalue()


def _image_to_b64(image_path: str) -> str:
    """Load image, resize for API, return base64 string."""
    return base64.b64encode(_resize_image_for_api(image_path)).decode()


# ──────────────────────────────────────────────────
# Deterministic pixel metrics
# ──────────────────────────────────────────────────

def compute_ssim(ref_path: str, sub_path: str) -> float:
    """Compute SSIM between reference and submission screenshots."""
    ref = _load_image_rgb(ref_path)
    sub = _load_image_rgb(sub_path)
    ref, sub = _resize_to_match(ref, sub)

    min_dim = min(ref.shape[0], ref.shape[1])
    win_size = min(7, min_dim if min_dim % 2 == 1 else min_dim - 1)
    if win_size < 3:
        return 0.0

    score = ssim(ref, sub, win_size=win_size, channel_axis=2, data_range=255)
    return float(max(0.0, score))


def compute_color_histogram_similarity(ref_path: str, sub_path: str) -> float:
    """Compare color distributions using histogram intersection."""
    ref = _load_image_rgb(ref_path)
    sub = _load_image_rgb(sub_path)
    ref, sub = _resize_to_match(ref, sub)

    similarity = 0.0
    for channel in range(3):
        ref_hist, _ = np.histogram(ref[:, :, channel].ravel(), bins=64, range=(0, 256))
        sub_hist, _ = np.histogram(sub[:, :, channel].ravel(), bins=64, range=(0, 256))
        ref_hist = ref_hist.astype(float) / (ref_hist.sum() + 1e-10)
        sub_hist = sub_hist.astype(float) / (sub_hist.sum() + 1e-10)
        similarity += np.minimum(ref_hist, sub_hist).sum()

    return float(similarity / 3.0)


def compute_pixel_metrics(ref_path: str, sub_path: str) -> dict:
    """Compute all deterministic pixel metrics."""
    ssim_score = compute_ssim(ref_path, sub_path)
    color_score = compute_color_histogram_similarity(ref_path, sub_path)
    combined = 0.6 * ssim_score + 0.4 * color_score
    return {
        "ssim": round(ssim_score, 4),
        "color_histogram": round(color_score, 4),
        "pixel_combined": round(combined, 4),
    }


# ──────────────────────────────────────────────────
# Shared judge prompt (used by both Claude and GPT)
# ──────────────────────────────────────────────────

JUDGE_SYSTEM_PROMPT = """You are a precise visual comparison judge for website design replication. You compare a REFERENCE screenshot against a SUBMISSION screenshot and score how accurately the submission replicates the reference.

IMPORTANT: Be consistent and calibrated. Use the full 0-10 scale. Do NOT default to middle scores.

Scoring anchors (apply these strictly):
- 0: The element is completely absent or bears no resemblance
- 1-2: Fundamentally different — wrong structure, wrong colors, wrong content
- 3-4: Vaguely similar theme but major structural or visual differences
- 5-6: Correct general structure but noticeable issues (wrong proportions, shifted colors, different fonts)
- 7-8: Good match — same structure, similar colors/fonts, but visible differences on close inspection
- 9: Nearly identical — only minor pixel-level differences visible on very close inspection
- 10: Visually indistinguishable from the reference

Key rules:
- If the submission is just a blank page or stub, ALL scores should be 0-1
- If the submission uses a completely different color scheme, color score should be 0-3
- If the submission uses monospace/wrong font family, typography score should be 0-3
- If the general layout structure matches but details differ, layout should be 5-7
- Only give 10 if you genuinely cannot tell the images apart for that criterion"""

JUDGE_USER_PROMPT = """Compare these two website screenshots. Image 1 is the REFERENCE. Image 2 is the SUBMISSION attempting to replicate it.

Page: {page_name} | Viewport: {viewport}

Score each criterion 0-10 using the scoring anchors from your instructions. Call the score_design function with your scores."""

SCORE_TOOL_SCHEMA = {
    "layout": {
        "type": "integer", "minimum": 0, "maximum": 10,
        "description": "Layout fidelity: sections, columns, grid structure, element positioning. 0=completely different structure, 5=right sections but wrong arrangement/proportions, 10=identical layout",
    },
    "color": {
        "type": "integer", "minimum": 0, "maximum": 10,
        "description": "Color accuracy: background colors, text colors, accent colors, gradients. 0=completely different palette, 5=some colors match but scheme is off, 10=identical colors",
    },
    "typography": {
        "type": "integer", "minimum": 0, "maximum": 10,
        "description": "Typography: font family (serif/sans/mono), sizes, weights, line-height, hierarchy. 0=wrong font family entirely, 5=right family but wrong sizes/weights, 10=identical typography",
    },
    "spacing": {
        "type": "integer", "minimum": 0, "maximum": 10,
        "description": "Spacing: margins, padding, gaps between elements, whitespace proportions. 0=no spacing resemblance, 5=roughly proportional but visibly different, 10=identical spacing",
    },
    "components": {
        "type": "integer", "minimum": 0, "maximum": 10,
        "description": "UI components: nav bars, cards, buttons, badges, dividers, footers, forms. 0=components missing or unrecognizable, 5=present but wrong style, 10=identical components",
    },
}

ZERO_SCORES = {"layout": 0.0, "color": 0.0, "typography": 0.0, "spacing": 0.0, "components": 0.0}


# ──────────────────────────────────────────────────
# Async LLM judges
# ──────────────────────────────────────────────────

async def _judge_claude_async(ref_b64: str, sub_b64: str, page_name: str, viewport: str, semaphore: asyncio.Semaphore) -> dict:
    """Score using Claude Opus 4.7 (async via thread)."""
    import anthropic

    def _call():
        client = anthropic.Anthropic(api_key=get_anthropic_key())
        response = client.messages.create(
            model="claude-opus-4-7",
            max_tokens=16000,
            system=JUDGE_SYSTEM_PROMPT,
            messages=[{
                "role": "user",
                "content": [
                    {"type": "text", "text": JUDGE_USER_PROMPT.format(page_name=page_name, viewport=viewport)},
                    {"type": "image", "source": {"type": "base64", "media_type": "image/png", "data": ref_b64}},
                    {"type": "image", "source": {"type": "base64", "media_type": "image/png", "data": sub_b64}},
                ],
            }],
            tool_choice={"type": "tool", "name": "score_design"},
            tools=[{
                "name": "score_design",
                "description": "Score the design replication quality on 5 criteria, each 0-10",
                "input_schema": {
                    "type": "object",
                    "properties": SCORE_TOOL_SCHEMA,
                    "required": ["layout", "color", "typography", "spacing", "components"],
                },
            }],
        )
        for block in response.content:
            if block.type == "tool_use":
                return {k: float(v) / 10.0 for k, v in block.input.items()}
        raise ValueError("Claude did not return tool_use")

    async with semaphore:
        return await asyncio.get_event_loop().run_in_executor(None, _call)


async def _judge_openai_async(ref_b64: str, sub_b64: str, page_name: str, viewport: str, semaphore: asyncio.Semaphore) -> dict:
    """Score using GPT-5.5 (async via thread)."""
    from openai import OpenAI

    def _call():
        client = OpenAI(api_key=get_openai_key())
        response = client.responses.create(
            model="gpt-5.5",
            input=[
                {"role": "system", "content": JUDGE_SYSTEM_PROMPT},
                {"role": "user", "content": [
                    {"type": "input_text", "text": JUDGE_USER_PROMPT.format(page_name=page_name, viewport=viewport)},
                    {"type": "input_image", "image_url": f"data:image/png;base64,{ref_b64}"},
                    {"type": "input_image", "image_url": f"data:image/png;base64,{sub_b64}"},
                ]},
            ],
            tools=[{
                "type": "function",
                "name": "score_design",
                "description": "Score the design replication quality on 5 criteria, each 0-10",
                "parameters": {
                    "type": "object",
                    "properties": SCORE_TOOL_SCHEMA,
                    "required": ["layout", "color", "typography", "spacing", "components"],
                },
            }],
            tool_choice={"type": "function", "name": "score_design"},
        )
        for item in response.output:
            if item.type == "function_call" and item.name == "score_design":
                scores = json.loads(item.arguments)
                return {k: float(v) / 10.0 for k, v in scores.items()}
        raise ValueError("GPT did not return function_call")

    async with semaphore:
        return await asyncio.get_event_loop().run_in_executor(None, _call)


async def _score_single_pair(
    ref_path: str,
    sub_path: str,
    page_name: str,
    viewport: str,
    semaphore: asyncio.Semaphore,
) -> tuple[dict, dict]:
    """Score a single page/viewport pair: pixel metrics + dual LLM judges.

    Returns (llm_scores, pixel_scores).
    """
    # Pixel metrics (instant, no semaphore needed)
    try:
        pixel = compute_pixel_metrics(ref_path, sub_path)
    except Exception as e:
        print(f"Pixel metrics failed for {page_name}/{viewport}: {e}", file=sys.stderr)
        pixel = {"ssim": 0.0, "color_histogram": 0.0, "pixel_combined": 0.0}

    # Prepare images once for both judges
    ref_b64 = _image_to_b64(ref_path)
    sub_b64 = _image_to_b64(sub_path)

    # Run both LLM judges concurrently
    claude_task = _judge_claude_async(ref_b64, sub_b64, page_name, viewport, semaphore)
    gpt_task = _judge_openai_async(ref_b64, sub_b64, page_name, viewport, semaphore)

    results = await asyncio.gather(claude_task, gpt_task, return_exceptions=True)

    scores_list = []
    for i, result in enumerate(results):
        judge_name = "Claude" if i == 0 else "GPT"
        if isinstance(result, Exception):
            print(f"{judge_name} judge failed for {page_name}/{viewport}: {result}", file=sys.stderr)
        else:
            scores_list.append(result)

    if not scores_list:
        return dict(ZERO_SCORES), pixel

    # Average across judges
    averaged = {}
    for key in ZERO_SCORES:
        averaged[key] = sum(s.get(key, 0.0) for s in scores_list) / len(scores_list)

    return averaged, pixel


# ──────────────────────────────────────────────────
# Structural Checks
# ──────────────────────────────────────────────────

def check_structural(submission_dir: Path, expected_pages: list[str]) -> float:
    """Check structural requirements (pages exist, nav links, stylesheet)."""
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
# Anti-hack checks
# ──────────────────────────────────────────────────

def check_for_hacks(submission_dir: Path) -> bool:
    """Return True if the submission appears to be gaming the grader."""
    for html_file in submission_dir.glob("*.html"):
        content = html_file.read_text()
        if "reference_screenshot" in content or "_ref_imgs" in content:
            return True
        base64_blocks = re.findall(r'base64,([A-Za-z0-9+/=]{10000,})', content)
        if base64_blocks:
            return True
        img_pngs = re.findall(
            r'<img[^>]+src=["\'][^"\']*(?:screenshot|reference|_ref)[^"\']*\.png["\']',
            content, re.IGNORECASE,
        )
        if img_pngs:
            return True
    return False


# ──────────────────────────────────────────────────
# Main grading function (async core)
# ──────────────────────────────────────────────────

async def _grade_submission_async(
    reference_dir: Path,
    submission_dir: Path,
    sub_screenshots_dir: Path,
    meta: dict,
) -> dict:
    """Async core of grade_submission. All LLM calls run in parallel."""
    pages = meta.get("pages", [])
    viewports = meta.get("viewports", VIEWPORTS)

    # Anti-hack check
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

    # Structural score
    structural = check_structural(submission_dir, pages)

    # Build list of all (page, viewport) pairs to score
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
                tasks.append(
                    _score_single_pair(str(ref_path), str(sub_path), page, vp_name, semaphore)
                )

    # Run all scoring tasks in parallel
    real_tasks = [t for t in tasks if t is not None]
    if real_tasks:
        real_results = await asyncio.gather(*real_tasks, return_exceptions=True)
    else:
        real_results = []

    # Reassemble results
    all_llm = []
    all_pixel = []
    per_page_scores = {}
    real_idx = 0

    for page, vp_name, valid in pair_keys:
        if page not in per_page_scores:
            per_page_scores[page] = {}

        if not valid:
            per_page_scores[page][vp_name] = 0.0
            all_llm.append(dict(ZERO_SCORES))
            all_pixel.append({"ssim": 0.0, "color_histogram": 0.0, "pixel_combined": 0.0})
        else:
            result = real_results[real_idx]
            real_idx += 1

            if isinstance(result, Exception):
                print(f"Scoring failed for {page}/{vp_name}: {result}", file=sys.stderr)
                all_llm.append(dict(ZERO_SCORES))
                all_pixel.append({"ssim": 0.0, "color_histogram": 0.0, "pixel_combined": 0.0})
                per_page_scores[page][vp_name] = 0.0
            else:
                llm_scores, pixel_scores = result
                all_llm.append(llm_scores)
                all_pixel.append(pixel_scores)
                llm_avg = sum(llm_scores.values()) / len(llm_scores) if llm_scores else 0.0
                per_page_scores[page][vp_name] = round(float(llm_avg), 3)

    # Aggregate LLM scores
    llm_agg = {}
    if all_llm:
        for key in ZERO_SCORES:
            llm_agg[key] = float(sum(s.get(key, 0.0) for s in all_llm) / len(all_llm))
    avg_llm = float(sum(llm_agg.values()) / len(llm_agg)) if llm_agg else 0.0

    # Aggregate pixel metrics
    avg_ssim = float(np.mean([p["ssim"] for p in all_pixel])) if all_pixel else 0.0
    avg_color = float(np.mean([p["color_histogram"] for p in all_pixel])) if all_pixel else 0.0
    avg_pixel = float(np.mean([p["pixel_combined"] for p in all_pixel])) if all_pixel else 0.0

    # Final weighted score: 70% LLM + 15% pixel + 15% structural
    overall = 0.70 * avg_llm + 0.15 * avg_pixel + 0.15 * structural

    return {
        "overall": round(float(overall), 4),
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
        "per_page": per_page_scores,
    }


# ──────────────────────────────────────────────────
# Sync wrapper
# ──────────────────────────────────────────────────

def grade_submission(
    reference_dir: Path,
    submission_dir: Path,
    sub_screenshots_dir: Path,
    meta: dict,
) -> dict:
    """Grade a submission against reference screenshots.

    Scoring: 70% dual-LLM judge + 15% pixel metrics + 15% structural checks.
    All LLM calls are parallelized.
    """
    try:
        loop = asyncio.get_running_loop()
    except RuntimeError:
        loop = None

    if loop and loop.is_running():
        # Already in an async context — use nest_asyncio or create new thread
        import concurrent.futures
        with concurrent.futures.ThreadPoolExecutor(max_workers=1) as pool:
            future = pool.submit(
                asyncio.run,
                _grade_submission_async(reference_dir, submission_dir, sub_screenshots_dir, meta),
            )
            return future.result()
    else:
        return asyncio.run(
            _grade_submission_async(reference_dir, submission_dir, sub_screenshots_dir, meta)
        )
