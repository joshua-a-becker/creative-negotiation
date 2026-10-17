#!/usr/bin/env python3
"""Run one offer through the same scorer used by the Creative Negotiations app."""

from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parent
APP = ROOT / "app"
SCORER = APP / "backend" / "stream.py"
CONFIG = APP / "config"
SHARED_KEYS = ROOT.parent / "01b Local Keys and Source Archive" / "keys"


def clean_unicode(value: object) -> str:
    """Keep malformed pasted characters from breaking the UTF-8 scorer pipe."""
    return str(value or "").encode("utf-8", errors="replace").decode("utf-8")


def main() -> int:
    parser = argparse.ArgumentParser(description="Score one Candidate-Recruiter offer.")
    parser.add_argument("--role", choices=("Candidate", "Recruiter"), default="Candidate")
    parser.add_argument("--issue-space", choices=("tutorial", "15", "200", "215", "fixed-15"), default=os.environ.get("SCORER_DEFAULT_SPACE", "15"), help="15/200/215 use flexible materials; fixed-15 requires all 15 terms.")
    inputs = parser.add_mutually_exclusive_group()
    inputs.add_argument("--text", help="Offer text. If omitted, the program asks for it.")
    inputs.add_argument("--choices-json", help="JSON object of explicit issue choices; scores without an LLM call.")
    parser.add_argument("--json", action="store_true", help="Print the complete structured result.")
    parser.add_argument("--scenario-file", help="Path to an external scenario JSON (both roles' issues/ranges/payoffs); overrides --issue-space.")
    args = parser.parse_args()

    if args.choices_json is not None:
        try:
            choices = json.loads(args.choices_json)
            if not isinstance(choices, dict) or not choices:
                raise ValueError('Expected a non-empty object of issue choices.')
        except (ValueError, TypeError) as exc:
            print(f'Invalid --choices-json: {exc}', file=sys.stderr)
            return 2
        payload = {'choices': choices}
    else:
        offer_text = clean_unicode(args.text if args.text is not None else input("Offer text: ")).strip()
        if not offer_text:
            print("Please provide an offer.", file=sys.stderr)
            return 2
        payload = {"text": offer_text, "previous_offer": ""}

    scenario_files = {"tutorial": "tutorial.json", "15": "small-15.json", "200": "large-200.json", "215": "large-215.json", "fixed-15": "fixed-15.json"}
    scenario = Path(args.scenario_file).resolve() if args.scenario_file else CONFIG / scenario_files[args.issue_space]
    if not SCORER.is_file() or not scenario.is_file():
        print("Scorer or scenario file not found. Keep empirica/ beside app/ and check --scenario-file.", file=sys.stderr)
        return 2
    environment = {
        **os.environ,
        "PYTHONIOENCODING": "utf-8",
        "PYTHONUTF8": "1",
        "ROLE": args.role,
        "MODE": "JSON",
        "NEGOTIATOR_PROVIDER": "openai",
        "NEGOTIATOR_MODEL": "gpt-5-nano",
        "NEGOTIATOR_SCORER_ROUTING": os.environ.get("NEGOTIATOR_SCORER_ROUTING", "nano-luna"),
        "NEGOTIATOR_SCENARIO_FILE": str(scenario),
    }
    if SHARED_KEYS.is_dir():
        environment.setdefault("CREATIVE_NEGOTIATIONS_KEYS_DIR", str(SHARED_KEYS))
    completed = subprocess.run(
        [sys.executable, str(SCORER)],
        input=json.dumps(payload, ensure_ascii=True),
        text=True,
        encoding="utf-8",
        capture_output=True,
        cwd=APP,
        env=environment,
        check=False,
    )
    if completed.returncode:
        print(completed.stderr or completed.stdout, file=sys.stderr)
        return completed.returncode

    result = json.loads(completed.stdout)
    if args.json:
        print(json.dumps(result, ensure_ascii=False, indent=2))
    else:
        print(result.get("display_text", completed.stdout))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
