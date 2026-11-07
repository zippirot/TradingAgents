"""The memory log: an append-only markdown record of each decision and, once settled, its outcome."""

import contextlib
import re
from datetime import UTC, datetime
from pathlib import Path
from uuid import UUID
from zoneinfo import ZoneInfo

from tradingagents.agents.evidence_presentation import compact_prior_decision
from tradingagents.agents.rating import RATINGS_5_TIER, parse_rating
from tradingagents.dataflows.files import locked, replace_file


def is_trading_entry(entry: dict) -> bool:
    """Only an actual five-tier decision can settle, score or become a lesson."""
    return entry.get("rating") in RATINGS_5_TIER


class TradingMemoryLog:
    """Append-only markdown log of trading decisions and reflections."""

    # HTML comment: cannot appear in LLM prose output, safe as a hard delimiter
    _SEPARATOR = "\n\n<!-- ENTRY_END -->\n\n"
    # Precompiled patterns — avoids re-compilation on every load_entries() call
    _DECISION_RE = re.compile(r"DECISION:\n(.*?)(?=\nREFLECTION:|\Z)", re.DOTALL)
    _REFLECTION_RE = re.compile(r"REFLECTION:\n(.*?)$", re.DOTALL)

    def __init__(self, config: dict = None):
        cfg = config or {}
        self._log_path = None
        path = cfg.get("memory_log_path")
        if path:
            self._log_path = Path(path).expanduser()
            self._log_path.parent.mkdir(parents=True, exist_ok=True)
        # Optional cap on resolved entries. None disables rotation.
        self._max_entries = cfg.get("memory_log_max_entries")

    # --- Write: a run records its decision ---

    def store_decision(
        self,
        ticker: str,
        trade_date: str,
        final_trade_decision: str,
        rating: str | None = None,
        decision_id: str | None = None,
    ) -> None:
        """Atomically add a pending entry at end of propagate(). No LLM call.

        ``rating`` is the decision's own rating when the caller has it; without
        one it is read from the decision text.
        """
        if decision_id is not None:
            decision_id = str(UUID(decision_id))
        rating = rating or parse_rating(final_trade_decision)
        if not self._log_path or rating not in RATINGS_5_TIER:
            return
        with locked(self._log_path):
            raw = self._log_path.read_text(encoding="utf-8") if self._log_path.exists() else ""
            complete = raw
            partial = ""
            if raw and not raw.endswith(self._SEPARATOR):
                # An interrupted append has no closing delimiter. Keep only
                # delimited entries so its tag cannot mask or consume this one.
                before, separator, tail = raw.rpartition(self._SEPARATOR)
                if tail.strip():
                    complete, partial = before + separator, tail
            # Idempotency guard: fast raw-text scan instead of full parse. Any entry
            # for this ticker and date blocks another, pending or settled: a re-run
            # after the outcome landed would otherwise count the same decision twice
            # in past context and in every aggregate over the log.
            for line in complete.splitlines():
                if line.startswith(f"[{trade_date} | {ticker} |") and line.endswith("]"):
                    fields = [field.strip() for field in line[1:-1].split("|")]
                    if len(fields) >= 4 and is_trading_entry({"rating": fields[2]}):
                        return
            # Historical REVIEW entries remain readable but never block a
            # corrected decision for the same ticker/date.
            tag = f"[{trade_date} | {ticker} | {rating} | pending]"
            link = f"<!-- PUBLICATION_ID: {decision_id} -->\n\n" if decision_id else ""
            entry = f"{tag}\n\n{link}DECISION:\n{final_trade_decision}{self._SEPARATOR}"
            if partial:
                stamp = datetime.now(UTC).strftime("%Y%m%dT%H%M%S%fZ")
                quarantine = self._log_path.with_name(f"{self._log_path.name}.partial-{stamp}.md")
                suffix = 1
                while quarantine.exists():
                    quarantine = self._log_path.with_name(
                        f"{self._log_path.name}.partial-{stamp}-{suffix}.md"
                    )
                    suffix += 1
                replace_file(
                    quarantine,
                    lambda temp: Path(temp).write_text(partial, encoding="utf-8"),
                    strict=True,
                )
            replace_file(
                self._log_path,
                lambda temp: Path(temp).write_text(complete + entry, encoding="utf-8"),
                strict=True,
            )

    def settling(self, wait: bool = True):
        """Hold the log for one settlement pass at a time, across threads and processes.

        A pass reads the pending entries, asks the model for a reflection on
        each and writes it; two passes at once would pay for the same
        reflections. A separate lock from the one each write takes. Yields
        whether it is held; with ``wait=False`` another pass is not waited for.
        """
        if not self._log_path:
            return contextlib.nullcontext(True)
        return locked(f"{self._log_path}.settle", wait=wait)

    # --- Read ---

    def load_entries(self) -> list[dict]:
        """Parse all entries from log. Returns list of dicts."""
        if not self._log_path or not self._log_path.exists():
            return []
        text = self._log_path.read_text(encoding="utf-8")
        raw_entries = [e.strip() for e in text.split(self._SEPARATOR) if e.strip()]
        entries = []
        for raw in raw_entries:
            parsed = self._parse_entry(raw)
            if parsed:
                entries.append(parsed)
        return entries

    def get_pending_entries(self) -> list[dict]:
        """Return entries with outcome:pending, for settlement."""
        return [e for e in self.load_entries() if e.get("pending") and is_trading_entry(e)]

    def get_past_context(
        self, ticker: str, n_same: int = 5, n_cross: int = 3, as_of: str | None = None,
        *, allow_unstamped_legacy: bool = False, analysis_date: str | None = None,
        analysis_timezone: str | None = None,
    ) -> str:
        """Return formatted past context string for agent prompt injection.

        Date-only callers retain the older resolution-date filter. An exact
        timestamp requires the actual persistence time (``known_at:...``), so
        legacy date-only tags cannot become retrospective lessons by an assumed
        timezone. A caller may retain unstamped legacy entries only when the
        actual read time is on the analysis date in its named timezone and has
        not passed the exact cutoff. ``as_of=None`` retains
        unfiltered direct-call behavior.
        """
        entries = [e for e in self.load_entries() if not e.get("pending") and is_trading_entry(e)]
        if analysis_date is not None:
            entries = [e for e in entries if not e.get('resolved') or e['resolved'] <= analysis_date]
        if as_of is not None:
            if len(as_of) == 10:
                # Preserve old direct date-query behavior. The graph uses an
                # exact instant, which requires a real persisted known-at time.
                entries = [e for e in entries if e.get("resolved") and e["resolved"] <= as_of]
            else:
                cutoff = datetime.fromisoformat(as_of.replace('Z', '+00:00'))
                if cutoff.utcoffset() is None:
                    raise ValueError('Lesson cutoff timestamp must include a timezone')
                read_at = datetime.now(UTC)
                legacy_available_now = bool(
                    allow_unstamped_legacy and analysis_date and analysis_timezone
                    and read_at <= cutoff
                    and read_at.astimezone(ZoneInfo(analysis_timezone)).date().isoformat()
                    == analysis_date)
                eligible = []
                for entry in entries:
                    if not entry.get('known_at'):
                        if legacy_available_now:
                            eligible.append(entry)
                        continue
                    known = datetime.fromisoformat(entry['known_at'].replace('Z', '+00:00'))
                    if known.utcoffset() is None:
                        raise ValueError('Recorded lesson known-at timestamp must include a timezone')
                    if known.astimezone(UTC) <= cutoff:
                        eligible.append(entry)
                entries = eligible
        if not entries:
            return ""

        same, cross = [], []
        for e in reversed(entries):
            if len(same) >= n_same and len(cross) >= n_cross:
                break
            if e["ticker"] == ticker and len(same) < n_same:
                same.append(e)
            elif e["ticker"] != ticker and len(cross) < n_cross:
                cross.append(e)

        if not same and not cross:
            return ""

        parts = []
        if same:
            parts.append(f"Past analyses of {ticker} (most recent first):")
            parts.extend(self._format_full(e) for e in same)
        if cross:
            parts.append("Recent cross-ticker lessons:")
            parts.extend(self._format_reflection_only(e) for e in cross)
        return "\n\n".join(parts)

    # --- Settle: record a decision's outcome and reflection ---

    def update_with_outcome(
        self,
        ticker: str,
        trade_date: str,
        raw_return: float,
        alpha_return: float,
        holding_days: int,
        reflection: str,
        resolution_date: str | None = None,
    ) -> bool:
        """Replace pending tag and append REFLECTION section using atomic write.

        Returns whether an entry was updated: False when the decision was no
        longer pending (another pass settled it first).

        Finds the first pending entry matching (trade_date, ticker), updates
        its tag with return figures (and the ``resolution_date`` the outcome
        became known), and appends a REFLECTION section.  Uses a temp-file +
        os.replace() so a crash mid-write never corrupts the log.
        """
        if not self._log_path or not self._log_path.exists():
            return False
        with locked(self._log_path):
            text = self._log_path.read_text(encoding="utf-8")
            blocks = text.split(self._SEPARATOR)

            pending_prefix = f"[{trade_date} | {ticker} |"
            raw_pct = f"{raw_return:+.1%}"
            alpha_pct = f"{alpha_return:+.1%}"

            updated = False
            new_blocks = []
            for block in blocks:
                stripped = block.strip()
                if not stripped:
                    new_blocks.append(block)
                    continue

                lines = stripped.splitlines()
                tag_line = lines[0].strip()

                if (
                    not updated
                    and tag_line.startswith(pending_prefix)
                    and tag_line.endswith("| pending]")
                ):
                    fields = [f.strip() for f in tag_line[1:-1].split("|")]
                    rating = fields[2]
                    if not is_trading_entry({"rating": rating}):
                        new_blocks.append(block)
                        continue
                    new_tag = self._resolved_tag(
                        trade_date,
                        ticker,
                        rating,
                        raw_pct,
                        alpha_pct,
                        holding_days,
                        resolution_date,
                        datetime.now(UTC).isoformat(),
                    )
                    rest = "\n".join(lines[1:])
                    new_blocks.append(f"{new_tag}\n\n{rest.lstrip()}\n\nREFLECTION:\n{reflection}")
                    updated = True
                else:
                    new_blocks.append(block)

            if not updated:
                return False

            new_blocks = self._apply_rotation(new_blocks)
            new_text = self._SEPARATOR.join(new_blocks)
            tmp_path = self._log_path.with_suffix(".tmp")
            tmp_path.write_text(new_text, encoding="utf-8")
            tmp_path.replace(self._log_path)
            return True

    def batch_update_with_outcomes(self, updates: list[dict]) -> None:
        """Apply multiple outcome updates in a single read + atomic write.

        Each element of updates must have keys: ticker, trade_date,
        raw_return, alpha_return, holding_days, reflection.
        """
        if not self._log_path or not self._log_path.exists() or not updates:
            return
        with locked(self._log_path):
            text = self._log_path.read_text(encoding="utf-8")
            blocks = text.split(self._SEPARATOR)

            update_map = {(u["trade_date"], u["ticker"]): u for u in updates}

            updated_any = False
            new_blocks = []
            for block in blocks:
                stripped = block.strip()
                if not stripped:
                    new_blocks.append(block)
                    continue

                lines = stripped.splitlines()
                tag_line = lines[0].strip()

                matched = False
                for (trade_date, ticker), upd in list(update_map.items()):
                    pending_prefix = f"[{trade_date} | {ticker} |"
                    if tag_line.startswith(pending_prefix) and tag_line.endswith("| pending]"):
                        fields = [f.strip() for f in tag_line[1:-1].split("|")]
                        rating = fields[2]
                        if not is_trading_entry({"rating": rating}):
                            continue
                        raw_pct = f"{upd['raw_return']:+.1%}"
                        alpha_pct = f"{upd['alpha_return']:+.1%}"
                        new_tag = self._resolved_tag(
                            trade_date,
                            ticker,
                            rating,
                            raw_pct,
                            alpha_pct,
                            upd["holding_days"],
                            upd.get("resolution_date"),
                            datetime.now(UTC).isoformat(),
                        )
                        rest = "\n".join(lines[1:])
                        new_blocks.append(
                            f"{new_tag}\n\n{rest.lstrip()}\n\nREFLECTION:\n{upd['reflection']}"
                        )
                        del update_map[(trade_date, ticker)]
                        matched = True
                        updated_any = True
                        break

                if not matched:
                    new_blocks.append(block)

            if not updated_any:
                return
            new_blocks = self._apply_rotation(new_blocks)
            new_text = self._SEPARATOR.join(new_blocks)
            tmp_path = self._log_path.with_suffix(".tmp")
            tmp_path.write_text(new_text, encoding="utf-8")
            tmp_path.replace(self._log_path)

    # --- Helpers ---

    @staticmethod
    def _resolved_tag(
        trade_date, ticker, rating, raw_pct, alpha_pct, holding_days, resolution_date,
        known_at=None,
    ) -> str:
        """Build a resolved entry tag, recording the outcome's known-by date.

        ``resolution_date`` (the date of the last price bar used for the return)
        is the point-in-time cutoff a later run filters on (#1251). Omitted when
        unavailable, keeping the legacy 6-field tag.
        """
        tag = f"[{trade_date} | {ticker} | {rating} | {raw_pct} | {alpha_pct} | {holding_days}d"
        if resolution_date:
            tag += f" | resolved:{resolution_date}"
        if known_at:
            tag += f" | known_at:{known_at}"
        return tag + "]"

    def _apply_rotation(self, blocks: list[str]) -> list[str]:
        """Drop oldest resolved blocks when their count exceeds max_entries.

        Pending blocks are always kept (they represent unprocessed work).
        Returns ``blocks`` unchanged when rotation is disabled or under cap.
        """
        if not self._max_entries or self._max_entries <= 0:
            return blocks

        # Tag each block with (kept, is_resolved) by parsing tag-line markers.
        decisions = []
        for block in blocks:
            stripped = block.strip()
            if not stripped:
                decisions.append((block, False))
                continue
            tag_line = stripped.splitlines()[0].strip()
            is_resolved = (
                tag_line.startswith("[")
                and tag_line.endswith("]")
                and not tag_line.endswith("| pending]")
                and is_trading_entry(self._parse_entry(stripped) or {})
            )
            decisions.append((block, is_resolved))

        resolved_count = sum(1 for _, r in decisions if r)
        if resolved_count <= self._max_entries:
            return blocks

        to_drop = resolved_count - self._max_entries
        kept: list[str] = []
        for block, is_resolved in decisions:
            if is_resolved and to_drop > 0:
                to_drop -= 1
                continue
            kept.append(block)
        return kept

    def _parse_entry(self, raw: str) -> dict | None:
        lines = raw.strip().splitlines()
        if not lines:
            return None
        tag_line = lines[0].strip()
        if not (tag_line.startswith("[") and tag_line.endswith("]")):
            return None
        fields = [f.strip() for f in tag_line[1:-1].split("|")]
        if len(fields) < 4:
            return None
        # Optional trailing "resolved:YYYY-MM-DD" field records when the outcome
        # became known, for point-in-time filtering (#1251).
        resolved = None
        known_at = None
        for f in fields[6:]:
            if f.startswith("resolved:"):
                resolved = f[len("resolved:") :].strip()
            elif f.startswith("known_at:"):
                known_at = f[len("known_at:") :].strip()
        entry = {
            "date": fields[0],
            "ticker": fields[1],
            "rating": fields[2],
            "pending": fields[3] == "pending",
            "raw": fields[3] if fields[3] != "pending" else None,
            "alpha": fields[4] if len(fields) > 4 else None,
            "holding": fields[5] if len(fields) > 5 else None,
            "resolved": resolved,
            "known_at": known_at,
        }
        body = "\n".join(lines[1:]).strip()
        publication_match = re.search(r"^<!-- PUBLICATION_ID: ([0-9a-f-]{36}) -->$", body, re.MULTILINE)
        if publication_match:
            entry["decision_id"] = str(UUID(publication_match.group(1)))
        decision_match = self._DECISION_RE.search(body)
        reflection_match = self._REFLECTION_RE.search(body)
        entry["decision"] = decision_match.group(1).strip() if decision_match else ""
        entry["reflection"] = reflection_match.group(1).strip() if reflection_match else ""
        return entry

    def _format_full(self, e: dict) -> str:
        raw = e["raw"] or "n/a"
        alpha = e["alpha"] or "n/a"
        holding = e["holding"] or "n/a"
        tag = f"[{e['date']} | {e['ticker']} | {e['rating']} | {raw} | {alpha} | {holding}]"
        parts = [tag, f"DECISION:\n{compact_prior_decision(e['decision'])}"]
        if e["reflection"]:
            parts.append(f"REFLECTION:\n{e['reflection']}")
        return "\n\n".join(parts)

    def _format_reflection_only(self, e: dict) -> str:
        tag = f"[{e['date']} | {e['ticker']} | {e['rating']} | {e['raw'] or 'n/a'}]"
        if e["reflection"]:
            return f"{tag}\n{e['reflection']}"
        decision = compact_prior_decision(e["decision"])
        text = decision[:300]
        suffix = "..." if len(decision) > 300 else ""
        return f"{tag}\n{text}{suffix}"
