"""Copias de seguridad de la base de datos y del registro de vigilancia.

Usa la API de backup de SQLite, que genera una copia consistente aunque los
bots estén escribiendo en la base de datos en ese momento. Se conservan las
últimas BACKUP_KEEP copias.

    python main.py backup

El bot de Discord también ejecuta una copia automática cada 24 horas.
BACKUP_DIR puede apuntar a otra unidad o a una carpeta sincronizada (Google
Drive, Object Storage montado...) para tener la copia fuera de la máquina.
"""

from datetime import datetime
import logging
from pathlib import Path
import shutil
import sqlite3

from src import config

log = logging.getLogger(__name__)


def backup_now(dest_dir: Path = config.BACKUP_DIR, keep: int = config.BACKUP_KEEP) -> Path | None:
  if not config.DB_PATH.exists():
    log.warning('No existe %s; nada que respaldar.', config.DB_PATH)
    return None

  stamp = datetime.now().strftime('%Y%m%d_%H%M%S')
  target = Path(dest_dir) / stamp
  target.mkdir(parents=True, exist_ok=True)

  src_conn = sqlite3.connect(config.DB_PATH, timeout=30)
  dst_conn = sqlite3.connect(target / config.DB_PATH.name)
  try:
    src_conn.backup(dst_conn)
  finally:
    dst_conn.close()
    src_conn.close()

  if config.BLUESKY_VIGILANCIA_JSON.exists():
    shutil.copy2(config.BLUESKY_VIGILANCIA_JSON, target)

  _rotate(Path(dest_dir), keep)
  log.info('Copia de seguridad creada en %s', target)
  return target


def _rotate(dest_dir: Path, keep: int):
  """Borra las copias más antiguas, conservando las `keep` más recientes."""
  copies = sorted(p for p in dest_dir.iterdir() if p.is_dir() and p.name[:8].isdigit())
  for old in copies[:-keep] if keep > 0 else []:
    shutil.rmtree(old, ignore_errors=True)


def main():
  logging.basicConfig(level=logging.INFO, format='%(asctime)s [%(levelname)s] %(message)s')
  target = backup_now()
  if target:
    print(f'Copia creada en: {target}')


if __name__ == '__main__':
  main()
