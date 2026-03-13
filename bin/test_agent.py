#!/usr/bin/env python3
"""
Ollama-powered unit testing agent.

Runs pytest, then — on any failure — queries a local Ollama LLM for a
structured analysis of root causes and suggested fixes.

Usage:
    poetry run python bin/test_agent.py
    poetry run python bin/test_agent.py --model gemma3:latest
    poetry run python bin/test_agent.py --pytest-args "-k test_analysis -v"
"""

import argparse
import json
import logging
import subprocess
import sys
from pathlib import Path
from typing import Any

import requests
import yaml
from pydantic import BaseModel, ValidationError

logger = logging.getLogger(__name__)

CONFIG_PATH = Path(__file__).parent.parent / "config.yaml"

_DEFAULTS: dict[str, Any] = {
    "ollama_base_url": "http://192.168.1.90:11434",
    "model": "phi4:latest",
    "pytest_command": [
        "poetry", "run", "pytest",
        "--cov=returns", "--cov-report=term-missing",
        "tests/", "-v",
    ],
    "max_context_chars": 8000,
}


# ---------------------------------------------------------------------------
# Pydantic schema – Ollama must return JSON matching this shape
# ---------------------------------------------------------------------------

class TestAnalysis(BaseModel):
    """Structured analysis of pytest failures returned by the LLM."""

    summary: str
    failing_tests: list[str]
    root_causes: list[str]
    suggested_fixes: list[str]


# ---------------------------------------------------------------------------
# Config
# ---------------------------------------------------------------------------

def load_config() -> dict[str, Any]:
    """Load test_agent section from config.yaml, falling back to defaults."""
    if CONFIG_PATH.exists():
        with open(CONFIG_PATH) as f:
            data = yaml.safe_load(f) or {}
        return {**_DEFAULTS, **data.get("test_agent", {})}
    return dict(_DEFAULTS)


# ---------------------------------------------------------------------------
# Test runner
# ---------------------------------------------------------------------------

def run_tests(command: list[str], extra_args: list[str]) -> tuple[int, str]:
    """
    Run pytest and return (exit_code, combined stdout+stderr).

    Args:
        command: Base pytest command from config.
        extra_args: Any additional pytest arguments from the CLI.

    Returns:
        Tuple of (exit_code, output_text).
    """
    full_cmd = command + extra_args
    logger.info("Running: %s", " ".join(full_cmd))
    result = subprocess.run(full_cmd, capture_output=True, text=True)
    return result.returncode, result.stdout + result.stderr


# ---------------------------------------------------------------------------
# Ollama integration
# ---------------------------------------------------------------------------

def _build_prompt(test_output: str) -> str:
    return f"""\
You are an expert Python developer and testing specialist.

The pytest run below produced failures. Analyse them and respond with JSON
that matches this exact schema — no markdown, no prose, only the JSON object:

{{
  "summary": "<one-sentence description of what failed and why>",
  "failing_tests": ["<test_name>", ...],
  "root_causes": ["<root cause for each group of failures>", ...],
  "suggested_fixes": ["<concrete, actionable fix>", ...]
}}

PYTEST OUTPUT:
{test_output}
"""


def query_ollama(base_url: str, model: str, prompt: str) -> TestAnalysis:
    """
    Send the prompt to Ollama and parse the response into a TestAnalysis.

    Uses Ollama's ``format`` field with the Pydantic JSON schema to force
    structured output, guaranteeing valid JSON from the model.

    Args:
        base_url: Ollama server base URL (e.g. ``http://192.168.1.90:11434``).
        model: Model name (e.g. ``phi4:latest``).
        prompt: The prompt text to send.

    Returns:
        Validated TestAnalysis instance.

    Raises:
        requests.HTTPError: If the Ollama request fails.
        ValidationError: If the model response doesn't match the schema.
    """
    payload = {
        "model": model,
        "prompt": prompt,
        "stream": False,
        "format": TestAnalysis.model_json_schema(),
    }
    logger.debug("POST %s/api/generate model=%s", base_url, model)
    resp = requests.post(f"{base_url}/api/generate", json=payload, timeout=120)
    resp.raise_for_status()

    raw_text: str = resp.json()["response"]
    logger.debug("Raw LLM response: %s", raw_text[:500])

    try:
        return TestAnalysis.model_validate_json(raw_text)
    except ValidationError:
        # Fallback: try to extract a JSON object if the model added surrounding text
        start = raw_text.find("{")
        end = raw_text.rfind("}") + 1
        if start != -1 and end > start:
            return TestAnalysis.model_validate(json.loads(raw_text[start:end]))
        raise


# ---------------------------------------------------------------------------
# Output formatting
# ---------------------------------------------------------------------------

def _print_analysis(analysis: TestAnalysis, model: str) -> None:
    width = 60
    print("\n" + "=" * width)
    print(f"  ANALYSIS  —  {model}")
    print("=" * width)
    print(f"\nSummary\n  {analysis.summary}")

    if analysis.failing_tests:
        print(f"\nFailing tests ({len(analysis.failing_tests)})")
        for t in analysis.failing_tests:
            print(f"  • {t}")

    if analysis.root_causes:
        print("\nRoot causes")
        for i, c in enumerate(analysis.root_causes, 1):
            print(f"  {i}. {c}")

    if analysis.suggested_fixes:
        print("\nSuggested fixes")
        for i, f in enumerate(analysis.suggested_fixes, 1):
            print(f"  {i}. {f}")

    print("=" * width + "\n")


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------

def main() -> int:
    """Run the test agent. Returns the pytest exit code."""
    parser = argparse.ArgumentParser(
        description="Ollama-powered pytest runner — runs tests and analyses failures with a local LLM.",
    )
    parser.add_argument(
        "--model",
        help="Override the Ollama model from config.yaml",
    )
    parser.add_argument(
        "--pytest-args",
        default="",
        help="Extra arguments forwarded verbatim to pytest (e.g. '-k test_analysis')",
    )
    parser.add_argument(
        "--no-analysis",
        action="store_true",
        help="Skip LLM analysis even when tests fail (just run pytest)",
    )
    parser.add_argument(
        "--verbose",
        action="store_true",
        help="Enable DEBUG logging",
    )
    args = parser.parse_args()

    logging.basicConfig(
        level=logging.DEBUG if args.verbose else logging.INFO,
        format="%(asctime)s %(levelname)-8s %(message)s",
        datefmt="%H:%M:%S",
    )

    cfg = load_config()
    model: str = args.model or cfg["model"]
    base_url: str = cfg["ollama_base_url"]
    pytest_command: list[str] = cfg["pytest_command"]
    max_chars: int = cfg["max_context_chars"]
    extra_args: list[str] = args.pytest_args.split() if args.pytest_args else []

    exit_code, output = run_tests(pytest_command, extra_args)
    print(output, end="")

    if exit_code == 0:
        logger.info("All tests passed.")
        return 0

    if args.no_analysis:
        return exit_code

    # Trim output to stay within a reasonable context window
    context = output[-max_chars:] if len(output) > max_chars else output
    if len(output) > max_chars:
        logger.debug("Output trimmed from %d to %d chars for LLM context.", len(output), max_chars)

    logger.info("Tests failed — querying %s at %s for analysis...", model, base_url)
    try:
        analysis = query_ollama(base_url, model, _build_prompt(context))
        _print_analysis(analysis, model)
    except requests.exceptions.ConnectionError:
        logger.error("Cannot reach Ollama at %s — is the server running?", base_url)
    except requests.HTTPError as exc:
        logger.error("Ollama request failed: %s", exc)
    except (ValidationError, ValueError, json.JSONDecodeError) as exc:
        logger.error("Could not parse LLM response: %s", exc)

    return exit_code


if __name__ == "__main__":
    sys.exit(main())
