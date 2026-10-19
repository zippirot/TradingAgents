#!/bin/bash
set -euo pipefail
cd -- "$(dirname -- "$0")"
if [[ ! -x .venv/bin/python ]]; then
  echo "The local Python environment is missing. Follow LOCAL_SETUP.md to install it."
  exit 1
fi
exec .venv/bin/python -m cli.main "$@"
