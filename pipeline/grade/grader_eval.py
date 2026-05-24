#!/usr/bin/env python3
"""Thin wrapper around harbor_grader.py for local evaluation.

Sets up environment variables from pipeline config and provides a
grade_submission() interface that works with pre-captured screenshots
(used by the calibration pipeline).
"""

import asyncio
import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent.parent))

from pipeline.config import get_anthropic_key, get_openai_key

# Set env vars so harbor_grader.py can read them via os.environ
os.environ["ANTHROPIC_API_KEY"] = get_anthropic_key()
os.environ["OPENAI_API_KEY"] = get_openai_key()

from pipeline.package.harbor_grader import _grade_async  # noqa: E402


def grade_submission(
    reference_dir: Path,
    submission_dir: Path,
    sub_screenshots_dir: Path,
    meta: dict,
) -> dict:
    """Grade a submission using pre-captured screenshots.

    Calls the canonical grader with sub_screenshots_dir so it skips
    Playwright capture.
    """
    try:
        loop = asyncio.get_running_loop()
    except RuntimeError:
        loop = None

    coro = _grade_async(
        reference_dir,
        submission_dir,
        meta,
        output_path=None,
        sub_screenshots_dir=sub_screenshots_dir,
    )

    if loop and loop.is_running():
        import concurrent.futures
        with concurrent.futures.ThreadPoolExecutor(max_workers=1) as pool:
            return pool.submit(asyncio.run, coro).result()
    else:
        return asyncio.run(coro)
