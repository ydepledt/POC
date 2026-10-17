#!/usr/bin/env sh
set -eu
cd "$(dirname "$0")"
[ -x .venv/bin/python ] || sh install.sh
exec .venv/bin/python -m evolution_lab serve --open-browser
