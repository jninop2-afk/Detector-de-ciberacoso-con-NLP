#!/usr/bin/env bash
# Instala el proyecto en un servidor Ubuntu (Oracle Cloud, Ampere ARM o x86).
# Uso, desde la carpeta del proyecto:  bash deploy/setup.sh
set -euo pipefail

APP_DIR="$(cd "$(dirname "$0")/.." && pwd)"
PY_VERSION="${PY_VERSION:-3.14}"
cd "$APP_DIR"

echo "==> Paquetes del sistema"
sudo apt-get update -y
sudo apt-get install -y git curl sqlite3

echo "==> uv (gestor de Python)"
if ! command -v uv >/dev/null 2>&1; then
  curl -LsSf https://astral.sh/uv/install.sh | sh
fi
export PATH="$HOME/.local/bin:$PATH"

echo "==> Python $PY_VERSION y entorno virtual en $APP_DIR/env"
uv python install "$PY_VERSION"
[ -d env ] || uv venv env --python "$PY_VERSION"

echo "==> Dependencias (torch versión CPU)"
uv pip install --python env/bin/python -c deploy/constraints.txt \
  torch --index-url https://download.pytorch.org/whl/cpu
uv pip install --python env/bin/python -c deploy/constraints.txt -r requirements.txt

echo "==> Comprobación"
env/bin/python - <<'PY'
import torch, transformers, sklearn, discord
print(f'torch {torch.__version__} | transformers {transformers.__version__} | '
      f'scikit-learn {sklearn.__version__} | discord.py {discord.__version__}')
PY

mkdir -p backups
echo
echo "Instalación lista. Siguiente paso: subir models/, data/ y .env (ver README)."
