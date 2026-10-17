#!/usr/bin/env sh
set -eu
cd "$(dirname "$0")"
command -v python3 >/dev/null 2>&1 || { echo 'Installez Python 3.11+ et python3-venv.'; exit 1; }
python3 -c 'import sys; assert sys.version_info >= (3,11), "Python 3.11 minimum requis"'
[ -x .venv/bin/python ] || python3 -m venv .venv
.venv/bin/python -m pip install -r requirements.txt
.venv/bin/python -m evolution_lab doctor
echo 'Installation terminée. Lancez sh start_app.sh.'
