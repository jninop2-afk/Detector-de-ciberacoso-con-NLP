#!/usr/bin/env bash
# Preparación inicial de un servidor nuevo (Hetzner Cloud, Ubuntu 24.04).
# Se ejecuta UNA sola vez, como root, recién creado el servidor:
#   bash prepare_server.sh            (crea el usuario "cyberbot")
#   bash prepare_server.sh otro_user  (otro nombre de usuario)
#
# Qué hace:
#   - actualiza el sistema y activa las actualizaciones de seguridad automáticas
#   - crea un usuario sin contraseña, con tu misma llave SSH y permiso sudo
#   - 4 GB de swap (colchón de memoria para RoBERTa)
#   - zona horaria de Colombia (registros y copias de seguridad)
#   - cortafuegos: sólo entra SSH (los bots sólo hacen conexiones salientes)
#   - SSH: sin acceso de root y sin contraseñas (sólo llave)
set -euo pipefail

NEW_USER="${1:-cyberbot}"

if [ "$(id -u)" -ne 0 ]; then
  echo "Ejecuta este script como root."; exit 1
fi
if [ ! -s /root/.ssh/authorized_keys ]; then
  echo "root no tiene una llave SSH configurada."
  echo "Crea el servidor en Hetzner seleccionando tu llave SSH y vuelve a intentarlo."
  exit 1
fi

echo "==> Actualizando el sistema"
export DEBIAN_FRONTEND=noninteractive
apt-get update -y
apt-get upgrade -y
apt-get install -y git curl sqlite3 ufw unattended-upgrades
dpkg-reconfigure -f noninteractive unattended-upgrades

echo "==> Zona horaria America/Bogota"
timedatectl set-timezone America/Bogota

echo "==> Usuario $NEW_USER"
if ! id "$NEW_USER" >/dev/null 2>&1; then
  adduser --disabled-password --gecos "" "$NEW_USER"
fi
usermod -aG sudo "$NEW_USER"
# Sin contraseña: el acceso es sólo con llave SSH, así que sudo no la pide
echo "$NEW_USER ALL=(ALL) NOPASSWD:ALL" > "/etc/sudoers.d/90-$NEW_USER"
chmod 440 "/etc/sudoers.d/90-$NEW_USER"
install -d -m 700 -o "$NEW_USER" -g "$NEW_USER" "/home/$NEW_USER/.ssh"
install -m 600 -o "$NEW_USER" -g "$NEW_USER" /root/.ssh/authorized_keys "/home/$NEW_USER/.ssh/authorized_keys"

echo "==> Swap de 4 GB"
if ! swapon --show | grep -q .; then
  fallocate -l 4G /swapfile
  chmod 600 /swapfile
  mkswap /swapfile
  swapon /swapfile
  grep -q '^/swapfile' /etc/fstab || echo '/swapfile none swap sw 0 0' >> /etc/fstab
fi
# Usar el swap sólo cuando de verdad falte memoria
echo 'vm.swappiness=10' > /etc/sysctl.d/90-swappiness.conf
sysctl -q -p /etc/sysctl.d/90-swappiness.conf

echo "==> Cortafuegos (sólo SSH)"
ufw allow OpenSSH
ufw --force enable

echo "==> SSH: sin root y sin contraseñas"
cat > /etc/ssh/sshd_config.d/10-cyberbot.conf <<'EOF'
PermitRootLogin no
PasswordAuthentication no
KbdInteractiveAuthentication no
EOF
sshd -t
systemctl reload ssh || systemctl restart ssh

echo
echo "Servidor listo. ANTES de cerrar esta sesión, comprueba en otra terminal:"
echo "    ssh $NEW_USER@$(hostname -I | awk '{print $1}')"
echo "Desde ahora root ya no puede entrar por SSH."
