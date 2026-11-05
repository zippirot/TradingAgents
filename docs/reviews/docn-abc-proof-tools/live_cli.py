"""Bounded, isolated real CLI proof. No paid traffic without --execute."""

from __future__ import annotations

import argparse
import fcntl
import hashlib
import json
import os
import re
import runpy
import subprocess
import sys
import threading
from datetime import UTC, datetime
from decimal import Decimal, InvalidOperation
from pathlib import Path
from urllib.request import urlopen

ROOT = Path(__file__).resolve().parents[3]
PROOF_ROOT = ROOT / "results/docn-abc"
WORK = PROOF_ROOT / "live-01"
LEDGER = PROOF_ROOT / "cost_ledger.jsonl"
LOCK = PROOF_ROOT / "runner.lock"
ORIGINAL_PREFS = Path.home() / ".tradingagents/cli_prefs.json"
CATALOG_URL = "https://openrouter.ai/api/v1/models"
SOURCE_ENV = Path("/Users/zipp/Documents/ChatGPT/Tauric/TradingAgents/.env")
MODEL = "openai/gpt-6.1-terra-pro"
MAX_OUTPUT = 65_536
# November 5 extension is incremental, not a reset of the existing ledger.
BASE_ATTEMPTS = 7
BASE_COMMITTED_USD = 18.410925
CAP_USD = float(min(Decimal("70"), Decimal(str(BASE_COMMITTED_USD)) + Decimal("50")))
MAX_ATTEMPTS = 11
MAX_DEEP_ATTEMPTS = 2
ANALYSIS_DATE = "2026-11-05"
TICKER = "DOCN"
DEPTH = 1
ANALYSIS_TIMEZONE = "America/Denver"
# Use the highest supplied published rate for either short/long input and output.
INPUT_USD_PER_TOKEN = 0.0000025
OUTPUT_USD_PER_TOKEN = 0.0000075

def work_for_run(name: str) -> Path:
    if not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9_-]{0,63}", name):
        raise ValueError("--run-name must be a simple basename (letters, digits, underscore, hyphen)")
    return PROOF_ROOT / name


def now() -> str:
    return datetime.now(UTC).isoformat()


def append(event: dict) -> None:
    PROOF_ROOT.mkdir(parents=True, exist_ok=True)
    with LEDGER.open("a", encoding="utf-8") as file:
        file.write(json.dumps({"time": now(), **event}, sort_keys=True) + "\n")
        file.flush()
        os.fsync(file.fileno())


def history() -> list[dict]:
    if not LEDGER.exists():
        return []
    return [json.loads(line) for line in LEDGER.read_text().splitlines() if line.strip()]


def committed_usd(events: list[dict]) -> float:
    # Reservations remain committed until a response supplies trustworthy usage.
    return sum(float(e.get("usd", 0)) for e in events if e["type"] in {"reserve", "settle"}) - sum(
        float(e.get("usd", 0)) for e in events if e["type"] == "release"
    )


def validate_attempt(events: list[dict], run_name: str, depth: int) -> int:
    """Enforce the approved extension against the retained lifetime ledger."""
    if depth not in (1, 5):
        raise ValueError("Proof depth must be Shallow (1) or Deep (5)")
    baseline_ends = [i for i, event in enumerate(events)
                     if event['type'] == 'attempt_end' and event.get('number') == BASE_ATTEMPTS]
    if len(baseline_ends) != 1:
        raise RuntimeError("Approved seven-attempt baseline is missing or ambiguous")
    baseline = events[:baseline_ends[0] + 1]
    if [e.get('number') for e in baseline if e['type'] == 'attempt'] != list(range(1, BASE_ATTEMPTS + 1)):
        raise RuntimeError("Approved attempt baseline is incomplete")
    if abs(committed_usd(baseline) - BASE_COMMITTED_USD) > 1e-8:
        raise RuntimeError("Approved spending baseline does not match retained ledger")
    attempts = [e for e in events if e['type'] == 'attempt']
    if [e.get('number') for e in attempts] != list(range(1, len(attempts) + 1)):
        raise RuntimeError("Attempt ledger sequence is invalid")
    if any(e.get('depth', 1) not in (1, 5) for e in attempts):
        raise RuntimeError("Unknown prior proof depth in ledger")
    if any(e.get('run_name') == run_name for e in attempts):
        raise RuntimeError("Run name already used; retain its proof and choose a new name")
    if len(attempts) >= MAX_ATTEMPTS:
        raise RuntimeError("Eleven-attempt lifetime proof limit reached")
    if depth == 5 and sum(e.get('depth', 1) == 5 for e in attempts) >= MAX_DEEP_ATTEMPTS:
        raise RuntimeError("Two-Deep-attempt proof limit reached")
    if committed_usd(events) + 1e-9 >= CAP_USD:
        raise RuntimeError("Proof cost ceiling reached")
    return len(attempts) + 1


def claim_workdir(work: Path, settings: dict) -> None:
    """Claim a new run without overwriting prior proofs or intentional seeds."""
    if work.is_symlink():
        raise RuntimeError("Proof directory cannot be a symlink")
    for path in work.rglob('*') if work.exists() else ():
        relative = path.relative_to(work).as_posix()
        if path.is_symlink():
            raise RuntimeError("Proof seed cannot contain symlinks")
        if path.is_file() and not (relative in {'cli.stdout.log', 'seed-continuity.json', 'engineering-seed.json'}
                or relative == 'memory/trading_memory.md'
                or relative.startswith('results/publications/')):
            raise RuntimeError(f"Refusing existing proof artifacts: {relative}")
    work.mkdir(parents=True, exist_ok=True)
    try:
        with (work / 'run_claim.json').open('x', encoding='utf-8') as handle:
            json.dump({'claimed_at': now(), **settings}, handle, indent=2)
            handle.write('\n')
    except FileExistsError as exc:
        raise RuntimeError("Refusing existing proof claim") from exc


class Guard:
    def __init__(self):
        self.lock = threading.RLock()
        self.request_count = 0

    def before(self, request) -> tuple[int, float] | None:
        if request.url.host != "openrouter.ai":
            if request.headers.get("authorization"):
                raise RuntimeError("Authenticated non-OpenRouter HTTP request blocked")
            return None
        if request.url.path != "/api/v1/chat/completions" or request.method != "POST":
            raise RuntimeError("Unexpected OpenRouter endpoint or method")
        body = request.content
        payload = json.loads(body)
        if payload.get("model") != MODEL:
            raise RuntimeError("Unexpected model in serialized request")
        if payload.get("plugins") or payload.get("web_search_options"):
            raise RuntimeError("Unbudgeted OpenRouter paid add-on in request")
        limit = payload.get("max_completion_tokens", payload.get("max_tokens"))
        if limit != MAX_OUTPUT:
            raise RuntimeError("Serialized request lacks expected output cap")
        # Serialized bytes cover request contents; add a chat framing allowance
        # for model-side formatting not present in JSON.
        framing = 1024 + 64 * len(payload.get("messages", [])) + 256 * len(payload.get("tools", []))
        input_bound = len(body) + framing
        upper = ((input_bound * INPUT_USD_PER_TOKEN + MAX_OUTPUT * OUTPUT_USD_PER_TOKEN) * 100 + 0.999999) // 1 / 100
        with self.lock:
            events = history()
            used = committed_usd(events)
            if used + upper > CAP_USD + 1e-9:
                raise RuntimeError(f"Proof budget exhausted: reserved ${used:.2f}, next upper bound ${upper:.2f}")
            self.request_count += 1
            sequence = 1 + sum(e["type"] == "reserve" for e in events)
            append({"type": "reserve", "request": sequence, "bytes": len(body), "framing_tokens": framing,
                    "input_bound_tokens": input_bound, "usd": upper, "model": MODEL})
        return sequence, upper

    def after(self, ticket: tuple[int, float] | None, response) -> None:
        if ticket is None:
            return
        sequence, upper = ticket
        if response.status_code >= 400 or not response.is_closed:
            # An HTTP failure or streaming body may still incur provider charges.
            append({"type": "unknown", "request": sequence, "status": response.status_code})
            return
        try:
            result = response.json()
            usage = result["usage"]
            prompt = int(usage["prompt_tokens"])
            completion = int(usage["completion_tokens"])
            if prompt < 0 or completion < 0 or completion > MAX_OUTPUT:
                raise ValueError("Invalid usage")
            usage_bound = prompt * INPUT_USD_PER_TOKEN + completion * OUTPUT_USD_PER_TOKEN
            if usage_bound > upper:
                raise ValueError("Usage exceeds reserved upper bound")
        except (KeyError, TypeError, ValueError, json.JSONDecodeError):
            append({"type": "unknown", "request": sequence, "status": response.status_code})
            return
        with self.lock:
            # Keep release and settlement atomic relative to new reservations.
            append({"type": "settle", "request": sequence, "usd": usage_bound,
                    "prompt_tokens": prompt, "completion_tokens": completion})
            append({"type": "release", "request": sequence, "usd": upper})


def install_guard(guard: Guard) -> None:
    import httpx
    import httpx2

    for module in (httpx, httpx2):
        original_send = module.Client.send
        original_async_send = module.AsyncClient.send

        def guarded_send(client, request, *args, _original=original_send, **kwargs):
            ticket = guard.before(request)
            response = _original(client, request, *args, **kwargs)
            guard.after(ticket, response)
            return response

        async def guarded_async_send(client, request, *args, _original=original_async_send, **kwargs):
            ticket = guard.before(request)
            response = await _original(client, request, *args, **kwargs)
            guard.after(ticket, response)
            return response

        module.Client.send = guarded_send
        module.AsyncClient.send = guarded_async_send


def read_required_env() -> None:
    from dotenv import dotenv_values

    values = dotenv_values(SOURCE_ENV)
    for name in ("OPENROUTER_API_KEY", "SEC_EDGAR_USER_AGENT"):
        value = values.get(name)
        if not value:
            raise RuntimeError(f"Required credential/identifier absent: {name}")
        os.environ[name] = value
    # Do not permit the package import to load any other credentials from a .env.
    import dotenv
    dotenv.find_dotenv = lambda *args, **kwargs: ""
    dotenv.load_dotenv = lambda *args, **kwargs: False


def configure() -> None:
    for name in list(os.environ):
        if name.startswith("TRADINGAGENTS_") or name.endswith("_API_KEY"):
            del os.environ[name]
    read_required_env()
    settings = {
        "TRADINGAGENTS_RESULTS_DIR": WORK / "results",
        "TRADINGAGENTS_CACHE_DIR": WORK / "cache",
        "TRADINGAGENTS_MEMORY_LOG_PATH": WORK / "memory/trading_memory.md",
        "TRADINGAGENTS_PREFS_PATH": WORK / "cli_prefs.json",
        "TRADINGAGENTS_LLM_PROVIDER": "openrouter",
        "TRADINGAGENTS_QUICK_THINK_LLM": MODEL,
        "TRADINGAGENTS_DEEP_THINK_LLM": MODEL,
        "TRADINGAGENTS_LLM_BACKEND_URL": "https://openrouter.ai/api/v1",
        "TRADINGAGENTS_OUTPUT_LANGUAGE": "English",
        "TRADINGAGENTS_MAX_DEBATE_ROUNDS": str(DEPTH),
        "TRADINGAGENTS_MAX_RISK_ROUNDS": str(DEPTH),
        "TRADINGAGENTS_ANALYSIS_TIMEZONE": ANALYSIS_TIMEZONE,
        "TRADINGAGENTS_MAX_TOOL_ROUNDS": "4",
        "TRADINGAGENTS_MAX_TOKENS": str(MAX_OUTPUT),
        "TRADINGAGENTS_LLM_MAX_RETRIES": "0",
        "TRADINGAGENTS_NO_UPDATE_CHECK": "1",
    }
    for name, value in settings.items():
        os.environ[name] = str(value)
    for path in (WORK / "results", WORK / "cache", WORK / "memory"):
        path.mkdir(parents=True, exist_ok=True)


def verify_config(config: dict | None = None) -> None:
    from tradingagents.default_config import DEFAULT_CONFIG

    config = DEFAULT_CONFIG if config is None else config
    if any(config.get(f"{tier}_think_provider") not in (None, "openrouter") for tier in ("quick", "deep")):
        raise RuntimeError("A model tier is configured outside OpenRouter")
    if config["llm_provider"] != "openrouter" or any(
        config[f"{tier}_think_llm"] != MODEL for tier in ("quick", "deep")
    ):
        raise RuntimeError("Unexpected provider or model tier")
    if config["backend_url"] != "https://openrouter.ai/api/v1":
        raise RuntimeError("Unexpected LLM backend")
    if any(config.get(f"{tier}_think_backend_url") for tier in ("quick", "deep")):
        raise RuntimeError("Unexpected tier-specific LLM backend")
    if int(config["max_tokens"]) != MAX_OUTPUT or int(config["llm_max_retries"]) != 0:
        raise RuntimeError("Unexpected completion cap or SDK retry setting")
    if any(int(config[key]) != DEPTH for key in ('max_debate_rounds', 'max_risk_discuss_rounds')):
        raise RuntimeError("Actual CLI debate/risk depth does not match requested proof depth")
    if int(config['max_tool_rounds']) != 4:
        raise RuntimeError("Unexpected tool round limit")
    if config.get('analysis_timezone') != ANALYSIS_TIMEZONE:
        raise RuntimeError("Unexpected analysis timezone")
    if {name for name in os.environ if name.endswith("_API_KEY")} != {"OPENROUTER_API_KEY"}:
        raise RuntimeError("Unexpected API credential in proof process")


def pricing_snapshot() -> dict:
    """Fetch current public rates and reject prices outside the reservation."""
    with urlopen(CATALOG_URL, timeout=15) as response:
        catalog = json.load(response)
    matches = [entry for entry in catalog.get("data", []) if entry.get("id") == MODEL]
    if len(matches) != 1 or not isinstance(matches[0].get("pricing"), dict):
        raise RuntimeError("Exact proof model pricing unavailable")
    pricing = matches[0]["pricing"]
    overrides = pricing.get("overrides", [])
    if not isinstance(overrides, list) or any(not isinstance(item, dict) for item in overrides):
        raise RuntimeError("Unrecognized model pricing overrides")
    allowed = {"prompt", "completion", "input_cache_read", "input_cache_write",
               "web_search", "overrides", "min_prompt_tokens"}
    checks = []
    for tier in [pricing, *overrides]:
        if any(key not in allowed and str(value) not in {"0", "0.0", "None"}
               for key, value in tier.items()):
            raise RuntimeError("Unbudgeted model pricing field")
        try:
            rates = {key: Decimal(str(tier[key])) for key in
                     ("prompt", "completion", "input_cache_read", "input_cache_write") if key in tier}
        except (InvalidOperation, TypeError) as exc:
            raise RuntimeError("Unreadable model pricing") from exc
        if "prompt" not in rates or "completion" not in rates:
            raise RuntimeError("Missing model prompt/completion price")
        if any(value < 0 for value in rates.values()):
            raise RuntimeError("Invalid negative model price")
        if any(rates.get(key, Decimal(0)) > Decimal(str(INPUT_USD_PER_TOKEN)) for key in
               ("prompt", "input_cache_read", "input_cache_write")):
            raise RuntimeError("Model input or cache price exceeds budget cap")
        if rates["completion"] > Decimal(str(OUTPUT_USD_PER_TOKEN)):
            raise RuntimeError("Model completion price exceeds budget cap")
        checks.append({key: str(value) for key, value in tier.items() if key in allowed and key != "overrides"})
    snapshot = {"fetched_at": now(), "catalog_url": CATALOG_URL, "model": MODEL,
                "base_and_overrides": checks,
                "optional_web_search_blocked": bool(pricing.get("web_search"))}
    (WORK / "pricing_snapshot.json").write_text(json.dumps(snapshot, indent=2) + "\n")
    return snapshot


def source_record() -> None:
    import tradingagents
    from tradingagents.default_config import DEFAULT_CONFIG

    tracked = subprocess.check_output(["git", "ls-files", "-z"], cwd=ROOT).decode().split("\0")
    untracked = subprocess.check_output(
        ["git", "ls-files", "--others", "--exclude-standard", "-z"], cwd=ROOT
    ).decode().split("\0")
    relevant = {p for p in tracked + untracked
                if (p.startswith(("cli/", "tradingagents/", "tests/")) and p.endswith(".py"))
                or p in {"pyproject.toml", "pytest.ini", "conftest.py"}}
    runner = {str(path.relative_to(ROOT)) for path in Path(__file__).parent.glob("*") if path.is_file()}
    paths = sorted(relevant | runner)
    config = DEFAULT_CONFIG
    record = {
        "head": subprocess.check_output(["git", "rev-parse", "HEAD"], cwd=ROOT, text=True).strip(),
        "runtime": {"python_executable": sys.executable, "python_version": sys.version,
                    "tradingagents_package": str(Path(tradingagents.__file__).resolve())},
        "configuration": {
            "ticker": TICKER, "analysis_date": ANALYSIS_DATE,
            "depth": DEPTH, "analysis_timezone": config["analysis_timezone"],
            "analysts": ["market", "social", "news", "fundamentals"],
            "llm_provider": config["llm_provider"],
            "quick_think_provider": config.get("quick_think_provider") or config["llm_provider"],
            "deep_think_provider": config.get("deep_think_provider") or config["llm_provider"],
            "quick_think_llm": config["quick_think_llm"],
            "deep_think_llm": config["deep_think_llm"],
            "max_debate_rounds": config["max_debate_rounds"],
            "max_risk_discuss_rounds": config["max_risk_discuss_rounds"],
            "max_tool_rounds": config["max_tool_rounds"],
            "max_tokens": int(config["max_tokens"]),
            "llm_max_retries": int(config["llm_max_retries"]),
        },
        "files": {path: hashlib.sha256((ROOT / path).read_bytes()).hexdigest() for path in paths if (ROOT / path).is_file()},
    }
    (WORK / "source_sha256.json").write_text(json.dumps(record, indent=2) + "\n")


def install_run_config_guard() -> None:
    """Check the real CLI's final configuration before it constructs the graph."""
    import cli.run
    original = cli.run._build_run_config

    def checked(*args, **kwargs):
        config = original(*args, **kwargs)
        verify_config(config)
        keys = ('llm_provider', 'quick_think_llm', 'deep_think_llm', 'max_debate_rounds',
                'max_risk_discuss_rounds', 'max_tool_rounds', 'max_tokens', 'llm_max_retries',
                'analysis_timezone')
        (WORK / 'actual_run_config.json').write_text(json.dumps(
            {key: config.get(key) for key in keys}, indent=2) + '\n')
        return config

    cli.run._build_run_config = checked


def install_round_observer() -> None:
    """Retain actual stream counts without modifying messages or graph state."""
    from tradingagents.graph.trading_graph import TradingAgentsGraph
    original = TradingAgentsGraph.stream_run

    def observed(graph, *args, **kwargs):
        evidence = {'depth': DEPTH, 'expected_research_turns': 2 * DEPTH,
                    'expected_risk_turns': 3 * DEPTH, 'research_counts': [], 'risk_counts': [],
                    'research_count_max': 0, 'risk_count_max': 0,
                    'stream_completed': False, 'error_type': None}
        try:
            for item in original(graph, *args, **kwargs):
                state = item[1]
                if isinstance(state, dict):
                    for key, prefix in (('investment_debate_state', 'research'), ('risk_debate_state', 'risk')):
                        count = state.get(key, {}).get('count') if isinstance(state.get(key), dict) else None
                        if type(count) is int and count >= 0:
                            sequence = evidence[f'{prefix}_counts']
                            if not sequence or sequence[-1] != count:
                                sequence.append(count)
                            evidence[f'{prefix}_count_max'] = max(evidence[f'{prefix}_count_max'], count)
                yield item
            evidence['stream_completed'] = True
        except BaseException as exc:
            evidence['error_type'] = type(exc).__name__
            raise
        finally:
            (WORK / 'executed_rounds.json').write_text(json.dumps(evidence, indent=2) + '\n')

    TradingAgentsGraph.stream_run = observed


def prefs_sha256() -> str | None:
    return hashlib.sha256(ORIGINAL_PREFS.read_bytes()).hexdigest() if ORIGINAL_PREFS.is_file() else None


def main() -> None:
    global WORK, ANALYSIS_DATE, TICKER, DEPTH
    parser = argparse.ArgumentParser()
    parser.add_argument("--execute", action="store_true", help="Start one paid CLI attempt")
    parser.add_argument("--run-name", default="live-01", help="Isolated result folder basename")
    parser.add_argument("--analysis-date", default=ANALYSIS_DATE, help="Actual requested as-of date, YYYY-MM-DD")
    parser.add_argument("--ticker", default=TICKER, help="Issuer symbol, e.g. DOCN or AAPL")
    parser.add_argument("--depth", choices=('shallow', 'deep'), default='shallow', help="One or five debate/risk rounds")
    args = parser.parse_args()
    # Do not import application modules until configure() sets the isolated env.
    requested_date = datetime.strptime(args.analysis_date, "%Y-%m-%d").date()
    if requested_date.isoformat() != args.analysis_date or requested_date > datetime.now().date():
        raise ValueError("--analysis-date must be a canonical date no later than today")
    ANALYSIS_DATE = args.analysis_date
    TICKER = args.ticker.upper()
    if not re.fullmatch(r"[A-Z0-9^][A-Z0-9.^=-]{0,31}", TICKER):
        raise ValueError("--ticker must be a bounded market symbol without paths or whitespace")
    DEPTH = 5 if args.depth == 'deep' else 1
    WORK = work_for_run(args.run_name)
    if not args.execute:
        print("Dry setup only. Paid calls require --execute.")
        return
    PROOF_ROOT.mkdir(parents=True, exist_ok=True)
    lock_file = LOCK.open("w")
    try:
        fcntl.flock(lock_file, fcntl.LOCK_EX | fcntl.LOCK_NB)
    except BlockingIOError as exc:
        raise RuntimeError("Another proof attempt is already running") from exc
    events = history()
    attempt_number = validate_attempt(events, args.run_name, DEPTH)
    original_prefs_before = prefs_sha256()
    claim_workdir(WORK, {'ticker': TICKER, 'depth': DEPTH, 'analysis_date': ANALYSIS_DATE,
                        'analysis_timezone': ANALYSIS_TIMEZONE, 'attempt_number': attempt_number,
                        'cumulative_cap_usd': CAP_USD})
    os.chdir(WORK)
    sys.path.insert(0, str(ROOT))
    configure()
    verify_config()
    pricing_snapshot()
    source_record()
    guard = Guard()
    install_guard(guard)
    install_run_config_guard()
    install_round_observer()
    append({"type": "attempt", "number": attempt_number, "run_name": args.run_name,
            "depth": DEPTH, "ticker": TICKER, "analysis_date": ANALYSIS_DATE,
            "original_prefs_sha256_before": original_prefs_before,
            "argv": ["--ticker", TICKER, "--date", ANALYSIS_DATE,
            "--analysts", "market,social,news,fundamentals", "--save", "--html", "--show", "--checkpoint"]})
    sys.argv = ["cli.main", "--ticker", TICKER, "--date", ANALYSIS_DATE, "--analysts",
                "market,social,news,fundamentals", "--save", "--html", "--show", "--checkpoint"]
    try:
        runpy.run_module("cli.main", run_name="__main__")
    finally:
        append({"type": "attempt_end", "number": attempt_number, "request_count": guard.request_count,
                "committed_usd": committed_usd(history()),
                "original_prefs_unchanged": prefs_sha256() == original_prefs_before})


if __name__ == "__main__":
    main()
