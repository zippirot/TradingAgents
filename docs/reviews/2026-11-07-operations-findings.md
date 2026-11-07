# Initial Build D findings review

Initial audit completed/reviewer_completed, Claude Fable,54 actual turns,$5.963897,2300244ms. Soft40 reached, hard70/$30/150min respected. Summary narrative says~28turns and ten tasks; telemetry54 and actual nine D2–D10 tasks are authoritative. No auditor Critical/High/Medium; builder promotes the verified D7 subset as material to preserving approved local diagnostics. Final local completion remains pending.

## 1. D7 allowlist silently drops sanitized locally generated indicator no-data details (e.g. '{indicator} unavailable: TypeName', '{indicator} could not be read for {date}: TypeName'), so an invalid LLM-chosen indicator now reads downstream as a generic no-usable-market-data message that can be mistaken for missing symbol coverage; the distinction survives only in logs

partially_confirmed; material=True; action=fix. Known local unsupported-indicator and wrapped calculation context was lost. Reproduced through actual Alpha Vantage and Yahoo entry points; fixed bounded literal reasons preserve category with no vendor message/argument echo. Raw exception detail remains forbidden. Same-worktree regression and final independent closure required.

## 2. delivered_narrative(raw=None) depends on the ambient _last_structured_raw contextvar; any future LLM/structured invocation between invoke_structured and the render call in the same node (e.g. inside validate_final_case or replay helpers in portfolio_manager/research_manager) would mislabel or drop the truncation note. Correct today per supplied code, but the coupling is implicit and unguarded

confirmed; material=False; action=defer. Future coupling risk, no current wrong-delivery reproduction. Research replay occurs before structured invocation or after rendered narrative; PM validate_final_case is deterministic and does not invoke an LLM. Supply complete producer/validator context for closure; no speculative refactor.

## 3. _resolve_save_path rejects any input shorter than three characters, including valid short absolute paths (e.g. '/a') and '~', forcing the default after one re-prompt; spec text ties the length rule to yes/no confusion, not absolute operator paths which D5 acceptance says remain supported

incorrect; material=False; action=no_action. Frozen D5 explicitly rejects any answer shorter than three characters. /a and ~ follow that approved rule; do not silently change it. Distinct builder-found Enter/default-relative-path defect is reproduced and corrected separately.

## 4. Run-log sanitization relies on log call sites using lazy %-args: any app-owned logger call that eagerly formats provider exception text into the message string itself (msg is kept verbatim when it is a str) would bypass _SafeRunFormatter's argument suppression; known offenders were fixed but the formatter cannot enforce this globally

confirmed; material=False; action=defer. Formatter relies on owned literal templates and suppressed args. All reachable modified provider logs use literal templates/type-name args; no current eager provider message leak reproduced. Future call-site convention documented; no generic redaction framework.

## 5. bind_structured's include_raw TypeError fallback means providers whose with_structured_output rejects include_raw get no raw envelope, so successful structured narratives on those providers can never receive a truncation note (silent degradation, no warning is logged for this path)

confirmed; material=False; action=defer. Legacy compatibility fallback lacks raw metadata, so cannot infer truncation. Actual supported installed LangChain adapters accept include_raw; custom legacy doubles do not. Existing tests prove no stale annotation and parsed contract preservation. Record limitation; no promise to infer absent metadata.

## 6. configure_run_logging lowers the root logger level to WARNING when it was higher, which also makes all pre-existing root handlers (e.g. a console handler set to ERROR) emit WARNING records for the duration of the run; level is restored on cleanup but the side effect during the run is undocumented

partially_confirmed; material=False; action=defer. Root threshold may broaden NOTSET handlers during the run, intentionally enabling required WARNING capture; original level is restored. Handler-level ERROR remains respected, contrary to finding example. No extra handler mutation or logger infrastructure.

## 7. In openai_client the openrouter branch assigns llm_kwargs['extra_body'] by replacement rather than merge; nothing else sets extra_body at construction today, but a future registry/spec-supplied extra_body would be silently overwritten

confirmed; material=False; action=defer. No current extra_body producer is overwritten. Future registry collision is speculative; defer merging infrastructure until a second actual producer exists.

## Builder-found D5 correction

With relative results_dir, Typer returns the displayed default on Enter. _prompt_save_path treated that relative default as a new relative input and duplicated it under reports. Public regression observed RED after correcting a missing test import. Normalize only the prompt default to an absolute path; explicit relative answers still anchor under reports, short-input and escape rules unchanged. Native existing replay now uses relative results inside its disposable cwd and returns actual displayed defaults. No new product confirmation.

## Evidence/coverage

Initial source-context bodies are exact historical da6f1876, not final correction source. Final closure will receive current complete CLI/router/indicator producers and PM/research/decision-context/valuation helpers omitted in the first packet. Raw provider data and live calls remain unavailable. Browser code reuse is checked with exact per-commit module comparison. No broader scope expansion.

## Exact code-reuse and logging/adapter probes

Builder byte comparison `tradingagents/report_html.py`: early28ad8f39 == da6f1876 == current156570502e124d710c2daa0447f898086f09fd9d: True. No browser payload recomputation is claimed.
Builder byte comparison `tradingagents/reporting.py`: early28ad8f39 == da6f1876 == current156570502e124d710c2daa0447f898086f09fd9d: True. No browser payload recomputation is claimed.

Actual logging/installed-adapter probe (builder run; no provider invocation):

```json
{
  "error_handler_still_excludes_warning": true,
  "root_level_restored": true,
  "include_raw_signature": {
    "ChatOpenAI": "(self, schema: '_DictOrPydanticClass | None' = None, *, method: \"Literal['function_calling', 'json_mode', 'json_schema']\" = 'json_schema', include_raw: 'bool' = False, strict: 'bool | None' = None, tools: 'list | None' = None, **kwargs: 'Any') -> 'Runnable[LanguageModelInput, _DictOrPydantic]'",
    "ChatAnthropic": "(self, schema: 'dict | type', *, include_raw: 'bool' = False, method: \"Literal['function_calling', 'json_schema']\" = 'function_calling', **kwargs: 'Any') -> 'Runnable[LanguageModelInput, dict | BaseModel]'",
    "ChatGoogleGenerativeAI": "(self, schema: 'dict | type[BaseModel]', method: \"Literal['function_calling', 'json_mode', 'json_schema'] | None\" = 'json_schema', *, include_raw: 'bool' = False, **kwargs: 'Any') -> 'Runnable[LanguageModelInput, dict | BaseModel]'"
  }
}
```

Initial audit input omissions are resolved by explicit full current PM/research manager, decision-context, shared valuation and valuation modules in final closure governing inputs. These deterministic helpers contain no LLM invocation between the structured reply and truncation marking. Nonselected pipeline/broker/live provider paths remain out of scope.
