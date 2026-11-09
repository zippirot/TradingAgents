# Installed vendor producer context

Observed installed yfinance1.7.0; no installation or dependency change. This is bounded local-source evidence, not a claim that all distributions expose this signal. Missing attributes fail conservatively to retry. Test HTTP responses and timezone are substituted; actual Ticker and PriceHistory parsing execute. No live Yahoo request.

`scrapers/history.py` SHA-256 `063a569905cddc7b7dd93420d05163d1afdae5936bef4beb468bee365c1f9d3a`.

`exceptions.py` SHA-256 `133f737ed130e64a72341fc262f25b4f092bc7c718f8f5f403c77f28c83dd67f`.

`base.py` SHA-256 `26aaff9fc59864f4c1e446bce0979de8f062a9bd35b9fa13acfd15aa33cb5eb1`.


Producer trace: TickerBase.history delegates to cached/lazy PriceHistory. Lazy construction uses the existing timezone lookup; the new helper performs no metadata request. PriceHistory stores its known timezone in `tz`. A chart.error sets the exception's yahoo_reason from its description; malformed/status/missing-result branches use the same exception type without that explicit reason. The helper accepts only the exact no-data grammar, matching canonical ticker and start/end epochs in the known timezone. Exception display text is neither evidence nor persisted narrative.

Bounded verbatim assignments from installed producer (scrapers/history.py):
```python
yahoo_reason = data["chart"]["error"]["description"]
_exception = YFPricesMissingError(self.ticker, _price_data_debug, yahoo_reason=yahoo_reason)
```
Exception assignments (exceptions.py):
```python
self.debug_info = debug_info
self.yahoo_reason = yahoo_reason
```
The full third-party bodies are omitted from the frozen packet. The real-parser regression supplies the exercised producer branch, including exact HTTP parameters, and preserves the actual wrapper; it does not independently prove live Yahoo delivery. Installed distributions without yahoo_reason remain retryable, which is a compatibility limitation rather than a license to infer zero.
