#!/usr/bin/env bash
# Instala Python, el entorno virtual y las dependencias en un servidor Ubuntu
# (Hetzner Cloud, x86 o ARM). Se ejecuta con el usuario normal, no con root,
# después de deploy/prepare_server.sh.
# Uso, desde la carpeta del proyecto:  bash deploy/setup.sh
set -euo pipefail

if [ "$(id -u)" -eq 0 ]; then
  echo "No lo ejecutes como root: entra con tu usuario (ssh cyberbot@<IP>)."; exit 1
fi

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
echo "Instalación lista. Siguiente paso, desde tu PC:"
echo "    powershell -ExecutionPolicy Bypass -File deploy\\subir_al_servidor.ps1 -Servidor <IP>"
