#!/usr/bin/env bash
set -euo pipefail
cd "$(dirname "$0")/.."
command -v python3 >/dev/null
command -v npm >/dev/null
python3 -c 'import sys; assert sys.version_info >= (3, 11), "Python 3.11+ required"'
python3 -m venv .venv
.venv/bin/python -m pip install -e '.[dev]'
(
  cd frontend
  npm ci
  npm run build
)
.venv/bin/projection-show validate
printf '\nReady. Run .venv/bin/projection-show run --windowed\n'
printf 'No system services or display settings were changed.\n'
