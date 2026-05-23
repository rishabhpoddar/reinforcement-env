"""Python wrapper for invoking OpenCode coding agents via CLI subprocess.

Uses `opencode run` CLI directly — no SDK server needed.
API keys are loaded from the project's .env file and passed via env vars.
"""

import json
import os
import signal
import subprocess
import sys
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional

from pipeline.config import PROJECT_ROOT


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

    def __init__(self, timeout_sec: int = 300, verbose: bool = True):
        self.timeout_sec = timeout_sec
        self.verbose = verbose
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
                        "command": ["npx", "-y", "@playwright/mcp@latest"],
                        "enabled": True,
                    }
                },
            }, indent=2))

    def _log(self, msg: str) -> None:
        if self.verbose:
            print(f"      [opencode] {msg}", flush=True)

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

        self._log(f"Starting: model={model} dir={working_dir}")
        self._log(f"Prompt length: {len(prompt)} chars")
        start_time = time.time()

        try:
            # Stream output in real-time for visibility
            # start_new_session=True creates a new process group so we can
            # kill opencode AND all its children (Playwright, etc.) on timeout
            proc = subprocess.Popen(
                cmd,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True,
                env=env,
                start_new_session=True,
            )

            stdout_lines: list[str] = []
            events: list[dict] = []
            has_error = False
            error_msg = ""

            # Read stdout line by line as it comes
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

                    # Log meaningful events
                    if etype == "text":
                        text = event.get("part", {}).get("text", "")
                        if text:
                            preview = text[:80].replace("\n", " ")
                            self._log(f"text: {preview}...")
                    elif etype == "tool_call":
                        tool = event.get("part", {}).get("name", "?")
                        self._log(f"tool_call: {tool}")
                    elif etype == "tool_result":
                        self._log("tool_result received")
                    elif etype == "step_start":
                        self._log("step started")
                    elif etype == "step_finish":
                        tokens = event.get("part", {}).get("tokens", {})
                        cost = event.get("part", {}).get("cost", 0)
                        self._log(
                            f"step finished — tokens: {tokens.get('total', '?')}, "
                            f"cost: ${cost:.4f}"
                        )
                    elif etype == "error":
                        has_error = True
                        error_data = event.get("error", {})
                        error_msg = error_data.get("data", {}).get(
                            "message", error_data.get("name", "Unknown error")
                        )
                        self._log(f"ERROR: {error_msg}")
                except json.JSONDecodeError:
                    # Non-JSON line (e.g., migration messages)
                    self._log(f"stderr/info: {line[:100]}")

                # Check timeout
                elapsed = time.time() - start_time
                if elapsed > self.timeout_sec:
                    # Kill entire process group (opencode + children)
                    os.killpg(os.getpgid(proc.pid), signal.SIGTERM)
                    time.sleep(2)
                    try:
                        os.killpg(os.getpgid(proc.pid), signal.SIGKILL)
                    except ProcessLookupError:
                        pass
                    proc.wait()
                    duration = time.time() - start_time
                    self._log(f"TIMEOUT after {duration:.1f}s")
                    return AgentResult(
                        success=False,
                        raw_output="\n".join(stdout_lines),
                        error=f"Agent timed out after {duration:.1f}s",
                        duration_sec=duration,
                        events=events,
                    )

            # Wait for process to finish
            proc.wait()
            stderr = proc.stderr.read().strip()
            duration = time.time() - start_time

            stdout = "\n".join(stdout_lines)

            self._log(f"Finished in {duration:.1f}s (exit code: {proc.returncode})")

            if proc.returncode != 0 and not stdout:
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
            self._log(f"EXCEPTION after {duration:.1f}s: {e}")
            return AgentResult(
                success=False,
                error=str(e),
                duration_sec=duration,
            )


def parse_model_string(model_string: str) -> tuple[str, str]:
    """Parse 'provider/model' string into (provider, model) tuple.

    Example: 'anthropic/claude-sonnet-4-6' -> ('anthropic', 'claude-sonnet-4-6')
    """
    parts = model_string.split("/", 1)
    if len(parts) != 2:
        raise ValueError(
            f"Invalid model string '{model_string}'. Expected 'provider/model'."
        )
    return parts[0], parts[1]
