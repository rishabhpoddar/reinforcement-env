"""Python wrapper for invoking OpenCode coding agents via CLI subprocess.

Uses `opencode run` CLI directly — no SDK server needed.
API keys are loaded from the project's .env file and passed via env vars.
"""

import atexit
import json
import logging
import os
import signal
import subprocess
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional

from pipeline.config import PROJECT_ROOT, log

# Track active opencode process groups so we can kill them on exit
_active_pgids: set[int] = set()


def _cleanup_opencode_processes():
    """Kill any active opencode process groups."""
    for pgid in list(_active_pgids):
        try:
            os.killpg(pgid, signal.SIGTERM)
        except (ProcessLookupError, PermissionError):
            pass
    time.sleep(1)
    for pgid in list(_active_pgids):
        try:
            os.killpg(pgid, signal.SIGKILL)
        except (ProcessLookupError, PermissionError):
            pass
    _active_pgids.clear()


def _signal_handler(signum, frame):
    """Handle SIGINT/SIGTERM by cleaning up opencode processes then exiting."""
    _cleanup_opencode_processes()
    raise SystemExit(128 + signum)


# Register cleanup for normal exit and signals
atexit.register(_cleanup_opencode_processes)
signal.signal(signal.SIGINT, _signal_handler)
signal.signal(signal.SIGTERM, _signal_handler)

logger = logging.getLogger("pipeline.opencode")


def _load_dotenv() -> dict[str, str]:
    """Load .env file from project root and return as dict."""
    env_vars: dict[str, str] = {}
    env_path = PROJECT_ROOT / ".env"
    if not env_path.exists():
        return env_vars

    for line in env_path.read_text().splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        key = key.strip()
        value = value.strip().strip("\"'")
        if key:
            env_vars[key] = value

    return env_vars


@dataclass
class AgentResult:
    success: bool
    raw_output: str = ""
    error: Optional[str] = None
    duration_sec: float = 0.0
    events: list[dict] = field(default_factory=list)


class OpenCodeAgent:
    """Runs an OpenCode coding agent via `opencode run` CLI.

    API keys are loaded from the project's .env file and passed to the
    subprocess — no system-level credentials are used.
    """

    # All OpenCode state lives in .opencode/ at the repo root
    _OPENCODE_DIR = PROJECT_ROOT / ".opencode"
    _DATA_DIR = _OPENCODE_DIR / "data"
    _CONFIG_DIR = _OPENCODE_DIR / "config" / "opencode"

    def __init__(self, timeout_sec: int = 300):
        self.timeout_sec = timeout_sec
        self._dotenv = _load_dotenv()
        self._DATA_DIR.mkdir(parents=True, exist_ok=True)
        self._CONFIG_DIR.mkdir(parents=True, exist_ok=True)
        # Write Playwright MCP config once into isolated config dir
        config_file = self._CONFIG_DIR / "opencode.jsonc"
        if not config_file.exists():
            config_file.write_text(json.dumps({
                "$schema": "https://opencode.ai/config.json",
                "mcp": {
                    "playwright": {
                        "type": "local",
                        "command": ["npx", "-y", "@playwright/mcp@latest", "--headless"],
                        "enabled": True,
                    }
                },
            }, indent=2))

    def run(
        self,
        prompt: str,
        model: str,
        working_dir: str | Path,
    ) -> AgentResult:
        """Run an OpenCode agent and return the result."""
        working_dir = Path(working_dir)
        working_dir.mkdir(parents=True, exist_ok=True)

        cmd = [
            "opencode", "run",
            "--model", model,
            "--format", "json",
            "--dir", str(working_dir),
            prompt,
        ]

        env = {
            **os.environ,
            **self._dotenv,
            "XDG_DATA_HOME": str(self._DATA_DIR),
            "XDG_CONFIG_HOME": str(self._CONFIG_DIR.parent),
        }

        logger.info(f"[opencode] Starting: model={model} dir={working_dir}")
        logger.debug(f"[opencode] Prompt ({len(prompt)} chars): {prompt[:200]}...")
        start_time = time.time()

        pgid = None
        try:
            proc = subprocess.Popen(
                cmd,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True,
                env=env,
                start_new_session=True,
            )
            pgid = os.getpgid(proc.pid)
            _active_pgids.add(pgid)

            stdout_lines: list[str] = []
            events: list[dict] = []
            has_error = False
            error_msg = ""

            while True:
                line = proc.stdout.readline()
                if not line and proc.poll() is not None:
                    break
                if not line:
                    continue

                line = line.strip()
                if not line:
                    continue

                stdout_lines.append(line)

                try:
                    event = json.loads(line)
                    events.append(event)
                    etype = event.get("type", "")
                    part = event.get("part", {})

                    if etype == "text":
                        text = part.get("text", "")
                        if text:
                            preview = text[:120].replace("\n", " ")
                            logger.info(f"[opencode] assistant: {preview}")
                            logger.debug(f"[opencode] assistant (full):\n{text}")

                    elif etype == "tool_use":
                        tool = part.get("tool", "?")
                        state = part.get("state", {})
                        tool_input = state.get("input", {})
                        tool_output = state.get("output", "")
                        status = state.get("status", "?")

                        # Log tool call with input
                        input_summary = json.dumps(tool_input, indent=2) if tool_input else ""
                        logger.info(f"[opencode] tool: {tool} ({status})")
                        if input_summary:
                            logger.debug(f"[opencode] tool input:\n{input_summary}")
                        if tool_output:
                            output_str = str(tool_output)
                            logger.debug(f"[opencode] tool output:\n{output_str[:2000]}")

                    elif etype == "step_start":
                        logger.debug("[opencode] --- step start ---")

                    elif etype == "step_finish":
                        tokens = part.get("tokens", {})
                        cost = part.get("cost", 0)
                        reason = part.get("reason", "?")
                        logger.info(
                            f"[opencode] step done ({reason}) — "
                            f"tokens: {tokens.get('total', '?')}, cost: ${cost:.4f}"
                        )

                    elif etype == "error":
                        has_error = True
                        error_data = event.get("error", {})
                        error_msg = error_data.get("data", {}).get(
                            "message", error_data.get("name", "Unknown error")
                        )
                        logger.error(f"[opencode] ERROR: {error_msg}")
                        logger.debug(f"[opencode] error detail: {json.dumps(error_data, indent=2)}")

                    else:
                        logger.debug(f"[opencode] event({etype}): {line[:300]}")

                except json.JSONDecodeError:
                    logger.debug(f"[opencode] non-json: {line[:200]}")

                elapsed = time.time() - start_time
                if elapsed > self.timeout_sec:
                    os.killpg(os.getpgid(proc.pid), signal.SIGTERM)
                    time.sleep(2)
                    try:
                        os.killpg(os.getpgid(proc.pid), signal.SIGKILL)
                    except ProcessLookupError:
                        pass
                    proc.wait()
                    duration = time.time() - start_time
                    logger.warning(f"[opencode] TIMEOUT after {duration:.1f}s")
                    return AgentResult(
                        success=False,
                        raw_output="\n".join(stdout_lines),
                        error=f"Agent timed out after {duration:.1f}s",
                        duration_sec=duration,
                        events=events,
                    )

            proc.wait()
            stderr = proc.stderr.read().strip()
            duration = time.time() - start_time

            stdout = "\n".join(stdout_lines)

            logger.info(f"[opencode] Finished in {duration:.1f}s (exit code: {proc.returncode})")

            if proc.returncode != 0 and not stdout:
                logger.error(f"[opencode] Failed: {stderr[:500]}")
                return AgentResult(
                    success=False,
                    error=f"opencode exited {proc.returncode}: {stderr[:500]}",
                    duration_sec=duration,
                    events=events,
                )

            if has_error:
                return AgentResult(
                    success=False,
                    raw_output=stdout,
                    error=error_msg,
                    duration_sec=duration,
                    events=events,
                )

            return AgentResult(
                success=True,
                raw_output=stdout,
                duration_sec=duration,
                events=events,
            )

        except Exception as e:
            duration = time.time() - start_time
            logger.exception(f"[opencode] EXCEPTION after {duration:.1f}s: {e}")
            return AgentResult(
                success=False,
                error=str(e),
                duration_sec=duration,
            )
        finally:
            if pgid is not None:
                _active_pgids.discard(pgid)


def parse_model_string(model_string: str) -> tuple[str, str]:
    """Parse 'provider/model' string into (provider, model) tuple."""
    parts = model_string.split("/", 1)
    if len(parts) != 2:
        raise ValueError(
            f"Invalid model string '{model_string}'. Expected 'provider/model'."
        )
    return parts[0], parts[1]
