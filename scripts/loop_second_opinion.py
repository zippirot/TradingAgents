"""A second evaluator from another model family, for the loop's periodic cross-check.

    loop_second_opinion.py REPORT_FOLDER [--cycle N] [--dry-run]

Sends the evaluator skill and the report (nothing else) to GPT-6 Astra through OpenRouter and writes
`evaluation.second.md` and `evaluation.second.json` beside the report. Used because the Codex command
line is not installed on this machine; the cost is measured and counted in the cycle's budget.
"""
from __future__ import annotations

import argparse
import datetime
import json
import re
import sys
import urllib.request
from pathlib import Path

from scripts.loop_run import STATE, environment, load_state, provider_usage, refusal

MODEL = "openai/gpt-6-astra"
SKILL = Path(__file__).resolve().parent.parent / "docs" / "loop" / "evaluator-skill-TAE-1.1-loop1.md"
ASK = ("Evaluate the report below by the skill above. You have only the report text; treat counts you cannot "
       "verify as unverified. Reply with the human-readable evaluation (section 17), then the section 18 record "
       "as ONE JSON object inside a ```json fenced block, shaped exactly as Host rule 4 says.")


def messages(report: str) -> list[dict]:
    return [{"role": "system", "content": SKILL.read_text()},
            {"role": "user", "content": f"{ASK}\n\n<report>\n{report}\n</report>"}]


def split_reply(text: str) -> tuple[str, dict]:
    """The prose and the last fenced JSON object in the reply; a reply without one is an error."""
    blocks = re.findall(r"```json\s*(\{.*?\})\s*```", text, flags=re.S)
    if not blocks:
        raise ValueError("the reply holds no fenced JSON record")
    return text, json.loads(blocks[-1])


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("folder", type=Path)
    parser.add_argument("--cycle", type=int, default=0)
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--state", type=Path, default=STATE)
    args = parser.parse_args(argv)
    report = (args.folder / "complete_report.md").read_text()
    state = load_state(args.state)
    blocked = refusal(state, args.cycle)
    print(f"second opinion from {MODEL}: report of {len(report):,} characters, skill {SKILL.name}")
    if blocked:
        print("REFUSED:", blocked)
        return 2
    if args.dry_run:
        print("dry run: nothing was sent")
        return 0
    env = environment()
    before = provider_usage(env)
    body = json.dumps({"model": MODEL, "messages": messages(report), "temperature": 0}).encode()
    request = urllib.request.Request("https://openrouter.ai/api/v1/chat/completions", data=body, headers={
        "Authorization": f"Bearer {env['OPENROUTER_API_KEY']}", "Content-Type": "application/json"})
    with urllib.request.urlopen(request, timeout=900) as reply:  # noqa: S310 - fixed https address
        text = json.load(reply)["choices"][0]["message"]["content"]
    (args.folder / "evaluation.second.md").write_text(text)
    after = provider_usage(env)
    cost = round(after - before, 4) if before is not None and after is not None else None
    state = load_state(args.state)
    state["runs"].append({"cycle": args.cycle, "kind": "second_opinion", "folder": str(args.folder), "cost": cost,
                          "started": datetime.datetime.now().isoformat(timespec="seconds")})
    args.state.write_text(json.dumps(state, indent=1))
    _prose, record = split_reply(text)
    (args.folder / "evaluation.second.json").write_text(json.dumps(record, indent=1))
    print(f"written beside the report; cost: {cost if cost is not None else 'not measured'} dollars")
    return 0


if __name__ == "__main__":
    sys.exit(main())
