#!/usr/bin/env python3
"""Harbor task grader — evaluates design replication quality.

Self-contained grader that runs inside the Harbor verifier container.
Compares the agent's submission against reference screenshots using:
1. Dual LLM judges (Claude Opus 4.7 + GPT-5.5), averaged (70% weight)
2. Deterministic pixel metrics: SSIM + color histogram (15% weight)
3. Structural checks (pages exist, nav links, stylesheet) (15% weight)
4. Anti-hack detection (screenshot embedding → score 0)
5. Defect grading for broken sites (replication + identification)

All LLM calls are parallelized via asyncio for speed.
"""

import argparse
import asyncio
import base64
import io
import json
import os
import re
import sys
from pathlib import Path

import numpy as np
from PIL import Image
from skimage.metrics import structural_similarity as compute_ssim_raw

MAX_CONCURRENT_LLM = 10

VIEWPORTS_DEFAULT = {
    "desktop": {"width": 1280, "height": 900},
    "tablet": {"width": 768, "height": 1024},
    "mobile": {"width": 375, "height": 812},
}


# ──────────────────────────────────────────────────
# Image utilities
# ──────────────────────────────────────────────────

def _load_image_rgb(path):
    return np.array(Image.open(path).convert("RGB"))


def _resize_to_match(img_a, img_b):
    if img_a.shape == img_b.shape:
        return img_a, img_b
    h, w = img_a.shape[:2]
    img_b_pil = Image.fromarray(img_b).resize((w, h), Image.LANCZOS)
    return img_a, np.array(img_b_pil)


def _resize_image_for_api(image_path, max_height=7000):
    img = Image.open(image_path)
    if img.height > max_height:
        ratio = max_height / img.height
        new_width = int(img.width * ratio)
        img = img.resize((new_width, max_height), Image.LANCZOS)
    buf = io.BytesIO()
    img.save(buf, format="PNG")
    return buf.getvalue()


def _image_to_b64(image_path):
    return base64.b64encode(_resize_image_for_api(image_path)).decode()


# ──────────────────────────────────────────────────
# Deterministic pixel metrics
# ──────────────────────────────────────────────────

def compute_ssim(ref_path, sub_path):
    ref = _load_image_rgb(ref_path)
    sub = _load_image_rgb(sub_path)
    ref, sub = _resize_to_match(ref, sub)
    min_dim = min(ref.shape[0], ref.shape[1])
    win_size = min(7, min_dim if min_dim % 2 == 1 else min_dim - 1)
    if win_size < 3:
        return 0.0
    score = compute_ssim_raw(ref, sub, win_size=win_size, channel_axis=2, data_range=255)
    return float(max(0.0, score))


def compute_color_histogram_similarity(ref_path, sub_path):
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


def compute_pixel_metrics(ref_path, sub_path):
    ssim_score = compute_ssim(ref_path, sub_path)
    color_score = compute_color_histogram_similarity(ref_path, sub_path)
    combined = 0.6 * ssim_score + 0.4 * color_score
    return {"ssim": round(ssim_score, 4), "color_histogram": round(color_score, 4), "pixel_combined": round(combined, 4)}


# ──────────────────────────────────────────────────
# LLM judge prompts
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
    "layout": {"type": "integer", "minimum": 0, "maximum": 10, "description": "Layout fidelity: sections, columns, grid structure, element positioning. 0=completely different structure, 5=right sections but wrong arrangement/proportions, 10=identical layout"},
    "color": {"type": "integer", "minimum": 0, "maximum": 10, "description": "Color accuracy: background colors, text colors, accent colors, gradients. 0=completely different palette, 5=some colors match but scheme is off, 10=identical colors"},
    "typography": {"type": "integer", "minimum": 0, "maximum": 10, "description": "Typography: font family (serif/sans/mono), sizes, weights, line-height, hierarchy. 0=wrong font family entirely, 5=right family but wrong sizes/weights, 10=identical typography"},
    "spacing": {"type": "integer", "minimum": 0, "maximum": 10, "description": "Spacing: margins, padding, gaps between elements, whitespace proportions. 0=no spacing resemblance, 5=roughly proportional but visibly different, 10=identical spacing"},
    "components": {"type": "integer", "minimum": 0, "maximum": 10, "description": "UI components: nav bars, cards, buttons, badges, dividers, footers, forms. 0=components missing or unrecognizable, 5=present but wrong style, 10=identical components"},
}

ZERO_SCORES = {"layout": 0.0, "color": 0.0, "typography": 0.0, "spacing": 0.0, "components": 0.0}


# ──────────────────────────────────────────────────
# Async LLM judges
# ──────────────────────────────────────────────────

async def _judge_claude_async(ref_b64, sub_b64, page_name, viewport, semaphore):
    import anthropic
    def _call():
        client = anthropic.Anthropic(api_key=os.environ.get("ANTHROPIC_API_KEY", ""))
        response = client.messages.create(
            model="claude-opus-4-7", max_tokens=16000, system=JUDGE_SYSTEM_PROMPT,
            messages=[{"role": "user", "content": [
                {"type": "text", "text": JUDGE_USER_PROMPT.format(page_name=page_name, viewport=viewport)},
                {"type": "image", "source": {"type": "base64", "media_type": "image/png", "data": ref_b64}},
                {"type": "image", "source": {"type": "base64", "media_type": "image/png", "data": sub_b64}},
            ]}],
            tool_choice={"type": "tool", "name": "score_design"},
            tools=[{"name": "score_design", "description": "Score the design replication quality on 5 criteria, each 0-10",
                     "input_schema": {"type": "object", "properties": SCORE_TOOL_SCHEMA, "required": list(SCORE_TOOL_SCHEMA.keys())}}],
        )
        for block in response.content:
            if block.type == "tool_use":
                return {k: float(v) / 10.0 for k, v in block.input.items()}
        raise ValueError("Claude did not return tool_use")
    async with semaphore:
        return await asyncio.get_event_loop().run_in_executor(None, _call)


async def _judge_openai_async(ref_b64, sub_b64, page_name, viewport, semaphore):
    from openai import OpenAI
    def _call():
        client = OpenAI(api_key=os.environ.get("OPENAI_API_KEY", ""))
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
            tools=[{"type": "function", "name": "score_design", "description": "Score the design replication quality on 5 criteria, each 0-10",
                     "parameters": {"type": "object", "properties": SCORE_TOOL_SCHEMA, "required": list(SCORE_TOOL_SCHEMA.keys())}}],
            tool_choice={"type": "function", "name": "score_design"},
        )
        for item in response.output:
            if item.type == "function_call" and item.name == "score_design":
                scores = json.loads(item.arguments)
                return {k: float(v) / 10.0 for k, v in scores.items()}
        raise ValueError("GPT did not return function_call")
    async with semaphore:
        return await asyncio.get_event_loop().run_in_executor(None, _call)


async def _score_single_pair(ref_path, sub_path, page_name, viewport, semaphore):
    try:
        pixel = compute_pixel_metrics(ref_path, sub_path)
    except Exception as e:
        print(f"Pixel metrics failed for {page_name}/{viewport}: {e}", file=sys.stderr)
        pixel = {"ssim": 0.0, "color_histogram": 0.0, "pixel_combined": 0.0}

    ref_b64 = _image_to_b64(ref_path)
    sub_b64 = _image_to_b64(sub_path)

    results = await asyncio.gather(
        _judge_claude_async(ref_b64, sub_b64, page_name, viewport, semaphore),
        _judge_openai_async(ref_b64, sub_b64, page_name, viewport, semaphore),
        return_exceptions=True,
    )

    scores_list = []
    for i, result in enumerate(results):
        if isinstance(result, Exception):
            print(f"{'Claude' if i == 0 else 'GPT'} judge failed for {page_name}/{viewport}: {result}", file=sys.stderr)
        else:
            scores_list.append(result)

    if not scores_list:
        return dict(ZERO_SCORES), pixel

    averaged = {k: sum(s.get(k, 0.0) for s in scores_list) / len(scores_list) for k in ZERO_SCORES}
    return averaged, pixel


# ──────────────────────────────────────────────────
# Defect grading (broken sites)
# ──────────────────────────────────────────────────

async def _check_defect_replication_async(ref_b64, sub_b64, defect_description, page_name, viewport, semaphore):
    import anthropic
    def _call():
        client = anthropic.Anthropic(api_key=os.environ.get("ANTHROPIC_API_KEY", ""))
        response = client.messages.create(
            model="claude-opus-4-7", max_tokens=16000,
            system="You are a precise visual inspector checking whether a specific design defect has been replicated in a website submission.",
            messages=[{"role": "user", "content": [
                {"type": "text", "text": f'The reference website has this INTENTIONAL defect:\n"{defect_description}"\n\nPage: {page_name} | Viewport: {viewport}\n\nImage 1 is the REFERENCE (has the defect). Image 2 is the SUBMISSION (should also have the defect).\n\nIs the defect present in the submission? Use the check_defect tool.'},
                {"type": "image", "source": {"type": "base64", "media_type": "image/png", "data": ref_b64}},
                {"type": "image", "source": {"type": "base64", "media_type": "image/png", "data": sub_b64}},
            ]}],
            tool_choice={"type": "tool", "name": "check_defect"},
            tools=[{"name": "check_defect", "description": "Report whether the defect is present in the submission",
                     "input_schema": {"type": "object", "properties": {
                         "present": {"type": "boolean", "description": "True if the defect is present in the submission"},
                         "confidence": {"type": "integer", "minimum": 1, "maximum": 5, "description": "Confidence level: 1=very unsure, 5=certain"},
                         "reason": {"type": "string", "description": "Brief explanation"},
                     }, "required": ["present", "confidence", "reason"]}}],
        )
        for block in response.content:
            if block.type == "tool_use":
                return block.input.get("present", False)
        return False
    async with semaphore:
        return await asyncio.get_event_loop().run_in_executor(None, _call)


async def _grade_defect_replication(reference_dir, sub_screenshots_dir, defects, semaphore):
    if not defects:
        return {"defect_replication": 1.0, "per_defect": []}
    tasks = []
    for defect in defects:
        page = defect.get("page", "")
        viewport = defect.get("viewport", "all")
        vp = "desktop" if viewport == "all" else viewport
        ref_path = reference_dir / f"{page}-{vp}.png"
        sub_path = sub_screenshots_dir / f"{page}-{vp}.png"
        if not ref_path.exists() or not sub_path.exists():
            async def _f():
                return False
            tasks.append(_f())
            continue
        ref_b64 = _image_to_b64(str(ref_path))
        sub_b64 = _image_to_b64(str(sub_path))
        tasks.append(_check_defect_replication_async(ref_b64, sub_b64, defect.get("description", ""), page, vp, semaphore))
    results = await asyncio.gather(*tasks, return_exceptions=True)
    per_defect = [1.0 if (not isinstance(r, Exception) and r) else 0.0 for r in results]
    avg = sum(per_defect) / len(per_defect) if per_defect else 0.0
    return {"defect_replication": round(avg, 4), "per_defect": per_defect}


async def _grade_defect_identification(submission_dir, defects, semaphore):
    report_path = submission_dir / "defects_report.md"
    if not report_path.exists():
        return {"defect_identification": 0.0, "report_found": False}
    report_text = report_path.read_text()
    if not report_text.strip():
        return {"defect_identification": 0.0, "report_found": True, "report_empty": True}
    import anthropic
    defects_json = json.dumps(defects, indent=2)
    def _call():
        client = anthropic.Anthropic(api_key=os.environ.get("ANTHROPIC_API_KEY", ""))
        response = client.messages.create(
            model="claude-opus-4-7", max_tokens=16000,
            system="You evaluate how well a defect report identifies intentional design defects in a website.",
            messages=[{"role": "user", "content": f"The following are the ACTUAL intentional defects in a website:\n{defects_json}\n\nThe agent wrote this defect report:\n{report_text}\n\nScore how well the agent identified the defects. Use the score_report tool."}],
            tool_choice={"type": "tool", "name": "score_report"},
            tools=[{"name": "score_report", "description": "Score the defect report quality",
                     "input_schema": {"type": "object", "properties": {
                         "recall": {"type": "integer", "minimum": 0, "maximum": 10, "description": "How many real defects were found? 0=none, 5=about half, 10=all found"},
                         "precision": {"type": "integer", "minimum": 0, "maximum": 10, "description": "How many reported defects are real? 0=all false positives, 5=mixed, 10=no false positives"},
                         "detail": {"type": "integer", "minimum": 0, "maximum": 10, "description": "Quality of defect descriptions? 0=vague, 5=identified but poorly described, 10=precise and actionable"},
                     }, "required": ["recall", "precision", "detail"]}}],
        )
        for block in response.content:
            if block.type == "tool_use":
                s = block.input
                weighted = (0.5 * s["recall"] + 0.3 * s["precision"] + 0.2 * s["detail"]) / 10.0
                return {"defect_identification": round(weighted, 4), "report_found": True, "recall": s["recall"], "precision": s["precision"], "detail": s["detail"]}
        return {"defect_identification": 0.0, "report_found": True}
    async with semaphore:
        try:
            return await asyncio.get_event_loop().run_in_executor(None, _call)
        except Exception as e:
            print(f"Defect identification grading failed: {e}", file=sys.stderr)
            return {"defect_identification": 0.0, "report_found": True}


# ──────────────────────────────────────────────────
# Structural checks
# ──────────────────────────────────────────────────

def check_structural(submission_dir, expected_pages):
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


def check_for_hacks(submission_dir, reference_dir=None):
    """Check if the submission embeds reference screenshots as images.

    Extracts all images from the HTML (file references and base64 data URIs),
    loads them, and compares each against every reference screenshot via SSIM.
    If any embedded image is very similar to a reference screenshot (SSIM > 0.85),
    it's flagged as a hack.
    """
    if reference_dir is None:
        return False

    reference_dir = Path(reference_dir)
    ref_images = list(reference_dir.glob("*.png"))
    if not ref_images:
        return False

    # Collect all images embedded in or referenced by the submission HTML
    embedded_images = []

    for html_file in submission_dir.glob("*.html"):
        content = html_file.read_text()
        html_dir = html_file.parent

        # Extract <img src="..."> file paths
        img_srcs = re.findall(r'<img[^>]+src=["\']([^"\']+)["\']', content)
        for src in img_srcs:
            if src.startswith("data:"):
                continue  # handled below
            img_path = html_dir / src
            if img_path.exists() and img_path.suffix.lower() in ('.png', '.jpg', '.jpeg', '.webp', '.gif'):
                try:
                    embedded_images.append(np.array(Image.open(img_path).convert("RGB")))
                except Exception:
                    pass

        # Extract base64 data URI images
        data_uris = re.findall(r'data:image/[^;]+;base64,([A-Za-z0-9+/=]+)', content)
        for data in data_uris:
            if len(data) < 1000:
                continue  # too small to be a screenshot
            try:
                img_bytes = base64.b64decode(data)
                img = Image.open(io.BytesIO(img_bytes)).convert("RGB")
                embedded_images.append(np.array(img))
            except Exception:
                pass

    if not embedded_images:
        return False

    # Compare each embedded image against each reference screenshot
    for embedded in embedded_images:
        for ref_path in ref_images:
            try:
                ref = np.array(Image.open(ref_path).convert("RGB"))
                ref_resized, emb_resized = _resize_to_match(ref, embedded)
                min_dim = min(ref_resized.shape[0], ref_resized.shape[1])
                win_size = min(7, min_dim if min_dim % 2 == 1 else min_dim - 1)
                if win_size < 3:
                    continue
                score = compute_ssim_raw(ref_resized, emb_resized, win_size=win_size, channel_axis=2, data_range=255)
                if score > 0.85:
                    print(f"Hack detected: embedded image matches {ref_path.name} (SSIM={score:.3f})", file=sys.stderr)
                    return True
            except Exception:
                pass

    return False


# ──────────────────────────────────────────────────
# Screenshot capture
# ──────────────────────────────────────────────────

async def capture_submission_screenshots(submission_dir, output_dir, viewports):
    from playwright.async_api import async_playwright
    output_dir.mkdir(parents=True, exist_ok=True)
    screenshots = {}
    html_files = sorted(submission_dir.glob("*.html"))
    if not html_files:
        return screenshots
    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=True)
        for html_file in html_files:
            page_name = html_file.stem
            screenshots[page_name] = {}
            for vp_name, vp_size in viewports.items():
                ctx = await browser.new_context(viewport={"width": vp_size["width"], "height": vp_size["height"]}, device_scale_factor=1)
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
# Main grading
# ──────────────────────────────────────────────────

async def _grade_async(reference_dir, submission_dir, meta, output_path=None, sub_screenshots_dir=None):
    """Core grading logic. All LLM calls run in parallel.

    Args:
        reference_dir: Directory with reference screenshots.
        submission_dir: Directory with submitted HTML/CSS files.
        meta: Task metadata dict.
        output_path: If provided, write reward.json here (Harbor mode).
        sub_screenshots_dir: If provided, use pre-captured screenshots instead
            of running Playwright (local/calibration mode).
    """
    pages = meta.get("pages", [])
    viewports = meta.get("viewports", VIEWPORTS_DEFAULT)
    is_broken = meta.get("is_broken", False)
    defects = meta.get("defects", [])

    # Capture submission screenshots if not pre-provided
    if sub_screenshots_dir is None:
        sub_screenshots_dir = Path("/logs/verifier/screenshots")
        await capture_submission_screenshots(submission_dir, sub_screenshots_dir, viewports)

    # Anti-hack check
    if check_for_hacks(submission_dir, reference_dir):
        result = {"overall": 0.0, "hack_detected": True}
        if output_path:
            output_path.parent.mkdir(parents=True, exist_ok=True)
            output_path.write_text(json.dumps(result, indent=2))
        return result

    structural = check_structural(submission_dir, pages)
    semaphore = asyncio.Semaphore(MAX_CONCURRENT_LLM)

    # Score all pairs in parallel
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
    for page, vp_name, valid in pair_keys:
        if not valid:
            all_llm.append(dict(ZERO_SCORES))
            all_pixel.append({"ssim": 0.0, "color_histogram": 0.0, "pixel_combined": 0.0})
        else:
            r = real_results[real_idx]
            real_idx += 1
            if isinstance(r, Exception):
                print(f"Scoring failed for {page}/{vp_name}: {r}", file=sys.stderr)
                all_llm.append(dict(ZERO_SCORES))
                all_pixel.append({"ssim": 0.0, "color_histogram": 0.0, "pixel_combined": 0.0})
            else:
                all_llm.append(r[0])
                all_pixel.append(r[1])

    # Aggregate
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
    }

    if is_broken and defects:
        defect_rep, defect_id = await asyncio.gather(
            _grade_defect_replication(reference_dir, sub_screenshots_dir, defects, semaphore),
            _grade_defect_identification(submission_dir, defects, semaphore),
        )
        rep_score = defect_rep.get("defect_replication", 0.0)
        id_score = defect_id.get("defect_identification", 0.0)
        overall = 0.50 * visual_fidelity + 0.25 * rep_score + 0.25 * id_score
        result["defect_replication"] = round(rep_score, 4)
        result["defect_identification"] = round(id_score, 4)
    else:
        overall = visual_fidelity

    result["overall"] = round(float(overall), 4)

    if output_path:
        output_path.parent.mkdir(parents=True, exist_ok=True)
        output_path.write_text(json.dumps(result, indent=2))
    return result


def grade(reference_dir, submission_dir, meta, output_path):
    return asyncio.run(_grade_async(Path(reference_dir), Path(submission_dir), meta, Path(output_path)))


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Grade web design replication")
    parser.add_argument("--reference", required=True, help="Reference screenshots dir")
    parser.add_argument("--submission", required=True, help="Submission dir")
    parser.add_argument("--meta", required=True, help="Task metadata JSON file")
    parser.add_argument("--output", required=True, help="Output reward JSON path")
    args = parser.parse_args()

    with open(args.meta) as f:
        meta = json.load(f)

    result = grade(args.reference, args.submission, meta, args.output)
    print(f"Overall score: {result['overall']}")
