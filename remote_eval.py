#!/usr/bin/env python3
"""Run Harbor evaluations entirely on Modal — zero local resource usage.

The Harbor orchestrator, agent processes, and Modal sandboxes all run in the cloud.
Your local machine only streams logs.

Setup:
    modal secret create anthropic-api-key ANTHROPIC_API_KEY=sk-ant-...
    modal secret create openai-api-key OPENAI_API_KEY=sk-...

Usage:
    modal run remote_eval.py
"""

import os
import modal

# ── Configuration ──
TASKS_DIR = "/root/tasks"
EVAL_TRIALS = 10
EVAL_CONCURRENT = 10
EVAL_MODEL = "anthropic/claude-opus-4-7"

app = modal.App("harbor-eval")

results_volume = modal.Volume.from_name("harbor-eval-results", create_if_missing=True)

harbor_image = (
    modal.Image.debian_slim(python_version="3.13")
    .apt_install("curl", "git", "nodejs", "npm")
    .pip_install(
        "harbor",
        "anthropic",
        "openai",
    )
    # Claude Code agent
    .run_commands("npm install -g @anthropic-ai/claude-code")
    # Copy task directories into the image
    .add_local_dir("tasks", "/root/tasks")
)


@app.function(
    image=harbor_image,
    timeout=14400,  # 4 hours max
    cpu=4.0,
    memory=8192,
    secrets=[
        modal.Secret.from_name("anthropic-api-key"),
        modal.Secret.from_name("openai-api-key"),
    ],
    volumes={"/root/results": results_volume},
)
async def run_eval(task_name: str):
    """Run Harbor eval for a single task on a dedicated cloud machine."""
    import logging
    from pathlib import Path
    from datetime import datetime, timezone

    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(name)s %(levelname)s %(message)s")
    logging.getLogger("hpack").setLevel(logging.WARNING)
    logging.getLogger("httpcore").setLevel(logging.WARNING)
    logging.getLogger("httpx").setLevel(logging.WARNING)
    logging.getLogger("h2").setLevel(logging.WARNING)

    from harbor.job import Job
    from harbor.models.job.config import JobConfig
    from harbor.models.environment_type import EnvironmentType
    from harbor.models.trial.config import (
        AgentConfig,
        EnvironmentConfig,
        TaskConfig,
        VerifierConfig,
    )

    task_path = Path(TASKS_DIR) / task_name
    results_dir = Path("/root/results") / "jobs"
    results_dir.mkdir(parents=True, exist_ok=True)

    timestamp = datetime.now(timezone.utc).strftime("%Y%m%d-%H%M%S")

    print(
        f"Starting eval: {task_name} (trials={EVAL_TRIALS}, concurrent={EVAL_CONCURRENT})"
    )

    config = JobConfig(
        job_name=f"remote-{task_name}-{timestamp}",
        jobs_dir=results_dir,
        n_attempts=EVAL_TRIALS,
        n_concurrent_trials=EVAL_CONCURRENT,
        agents=[
            AgentConfig(
                name="claude-code",
                model_name=EVAL_MODEL,
            )
        ],
        environment=EnvironmentConfig(
            type=EnvironmentType.MODAL,
        ),
        verifier=VerifierConfig(
            env={
                "ANTHROPIC_API_KEY": os.environ.get("ANTHROPIC_API_KEY", ""),
                "OPENAI_API_KEY": os.environ.get("OPENAI_API_KEY", ""),
            }
        ),
        tasks=[TaskConfig(path=task_path)],
    )

    job = await Job.create(config)
    result = await job.run()

    print(f"Completed: {task_name}")
    print(f"  Completed trials: {result.stats.n_completed_trials}")
    print(f"  Errored trials: {result.stats.n_errored_trials}")

    for _, eval_data in result.stats.evals.items():
        for m in eval_data.metrics:
            print(f"  Metrics: {m}")

    await results_volume.commit.aio()
    return {"task": task_name, "stats": result.stats.model_dump(mode="json")}


@app.local_entrypoint()
def main():
    """Discover all tasks and fan out eval jobs on Modal."""
    import subprocess
    from pathlib import Path

    task_dirs = sorted(
        d.name
        for d in Path("tasks").iterdir()
        if d.is_dir() and (d / "task.toml").exists()
    )

    print(f"Found {len(task_dirs)} tasks to evaluate:")
    for t in task_dirs:
        print(f"  - {t}")
    print()

    # Fan out — each task runs as a separate Modal function invocation
    # They run in parallel on separate cloud machines
    results = []
    for result in run_eval.map(task_dirs):
        results.append(result)
        print(f"Done: {result['task']}")

    print(f"\nAll {len(results)} tasks completed.")

    # Download results locally
    output_dir = Path("remote-jobs")
    output_dir.mkdir(exist_ok=True)
    print(f"\nDownloading results to {output_dir}/...")
    subprocess.run(
        [
            "modal",
            "volume",
            "get",
            "harbor-eval-results",
            "jobs/",
            str(output_dir) + "/",
            "--force",
        ],
        check=True,
    )
    print(f"Results saved to {output_dir}/")
