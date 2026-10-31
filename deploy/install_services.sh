#!/usr/bin/env bash
# Instala y arranca los servicios systemd de los bots.
# Uso:  bash deploy/install_services.sh bot bluesky vigilancia
#       (sin argumentos instala sólo el bot de Discord)
set -euo pipefail

APP_DIR="$(cd "$(dirname "$0")/.." && pwd)"
BOTS=("${@:-bot}")

sed -e "s|__USER__|$USER|g" -e "s|__APP_DIR__|$APP_DIR|g" \
  "$APP_DIR/deploy/cyberbot@.service" | sudo tee /etc/systemd/system/cyberbot@.service >/dev/null
sudo systemctl daemon-reload

for b in "${BOTS[@]}"; do
  case "$b" in
    bot|bluesky|vigilancia) ;;
    *) echo "Bot desconocido: $b (usa bot, bluesky o vigilancia)"; exit 1 ;;
  esac
  sudo systemctl enable --now "cyberbot@$b"
  echo "==> cyberbot@$b activo"
done

echo
systemctl --no-pager list-units --type=service 'cyberbot@*'
echo
echo "Registros en vivo:  journalctl -u cyberbot@bot -f"
