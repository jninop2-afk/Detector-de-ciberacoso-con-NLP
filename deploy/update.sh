#!/usr/bin/env bash
# Actualiza el código desde GitHub y reinicia los bots activos.
# Uso:  bash deploy/update.sh
set -euo pipefail

APP_DIR="$(cd "$(dirname "$0")/.." && pwd)"
cd "$APP_DIR"
export PATH="$HOME/.local/bin:$PATH"

git pull --ff-only
uv pip install --python env/bin/python -c deploy/constraints.txt -r requirements.txt
sudo systemctl restart 'cyberbot@*'
systemctl --no-pager list-units --type=service 'cyberbot@*'
