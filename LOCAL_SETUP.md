# Running your TradingAgents fork

Your fork: https://github.com/zippirot/TradingAgents

Original project: https://github.com/TauricResearch/TradingAgents

## Launch

Double-click `Start TradingAgents.command` in Finder. It opens the interactive
terminal interface. You can also run:

```sh
cd /Users/zipp/Documents/ChatGPT/Tauric/TradingAgents
./Start\ TradingAgents.command
```

Choose your ticker, date, analysts and model provider in the prompts.
This is a terminal application, with saved reports available as HTML.

## API key

Edit `.env` in this folder and fill in the key for your chosen provider.
Keep the key in this local file, not in chat or committed source files.
The file is ignored by Git and readable only by your macOS account.
Model API calls use your provider's paid API account; local installation does
not make those calls free. Market-data access still requires internet access.

## Development

Python 3.12 is installed in `.venv`; the package is installed in editable mode,
so source edits are used on the next launch. Development test tools are included.

```sh
.venv/bin/python -m pip check
.venv/bin/python -m pytest tests/test_cli_commands.py tests/test_cli_headless.py tests/test_env_overrides.py
```

`origin` is your fork. `upstream` is TauricResearch. Local setup changes are on
`codex/local-setup`; `main` tracks your fork's original code. Future changes can
be committed on feature branches and pushed to your fork when you are ready.

To rebuild the environment on this Mac:

```sh
/opt/homebrew/bin/python3.12 -m venv .venv
.venv/bin/python -m pip install -e '.[dev]'
```

Results and cache use the upstream defaults under `~/.tradingagents` unless
you override their paths in `.env`.

## Setup verification (2026-10-19)

- Upstream version: 0.7.0, commit `e8f5503e9b86d5c2710b0c76b1f686703968c9df`.
- Python 3.12.13; editable installation with development dependencies succeeded.
- `pip check`: no broken requirements.
- Launcher shell syntax, CLI help and interactive ticker prompt verified.
- The three focused test files above: 75 passed.
- `.env` and `.venv` are ignored by Git.
- Live model calls and a complete market analysis have not been tested; an API
  provider and a valid key still need to be configured.
