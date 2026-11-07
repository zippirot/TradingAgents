# Reopen a zero-coverage outcome

Publication settlement keeps priced, pending, ineligible and unresolvable outcomes separate. An unknown or malformed empty response, outage or missing benchmark row stays retryable. Three verified zero-instrument-session checks after the nominal horizon, on distinct runs at least 14 calendar days apart, stop automatic retries. This is a coverage limit, not a delisting or a loss.

If coverage has been restored, explicitly reopen one zero-coverage endpoint:

```bash
python -m tradingagents.memory.publication_outcomes reopen \
  --results-dir /path/to/results \
  --decision-id PUBLICATION_UUID \
  --endpoint 5_sessions
```

`--results-dir` is required and names the directory containing `publications/`. There is no default live-data destination. Run this from the intended checkout with its existing Python environment. The invocation acquires the existing companion lock, verifies the publication and companion, reopens only the selected zero-coverage terminal endpoint, and resets its three-check evidence. It preserves the terminal reason, knowledge time and manual reopen time. Siblings and the immutable publication are unchanged. The next ordinary settlement pass can use restored prices; no automatic reopen or new service is introduced. An invalid/corrupt companion, unknown endpoint or different terminal classification fails visibly.

Historical summaries show the terminal status only from its recorded knowledge time until the manual reopen time. Terminal outcomes are not resolved performance samples. A verified exact-session mismatch never licenses an asof return. Current deterministic calendar proof is limited to SPY's published 2026 NYSE Arca holiday closures; other missing rows and years remain retryable.

Calendar references (checked November 7, 2026): [NYSE holiday schedule](https://www.nyse.com/trade/hours-calendars), [SPY listing on NYSE Arca](https://www.ssga.com/us/en/institutional/etfs/state-street-spdr-sp-500-etf-trust-spy). These are dated local rules, not a new network provider. Calendar updates require source review.
