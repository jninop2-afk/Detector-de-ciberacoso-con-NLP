"""Integración: base de datos real + registro de vigilancia + copias de seguridad.

Se llenan las tablas con datos reales de los bots, se hace la copia y se
comprueba que la copia se puede abrir y contiene lo mismo (es restaurable).

IMPORTANTE: backup_now() fija su carpeta por defecto (config.BACKUP_DIR) al
importarse el módulo, así que cambiar config.BACKUP_DIR después no la cambia.
Por eso estas pruebas SIEMPRE pasan dest_dir explícito: si no, escribirían en
la carpeta backups/ real y la rotación podría borrar copias reales.
"""

import json
import sqlite3

from src import backup, config


def _llenar(db):
  db.set_guild_config(1, configured_by=9, mod_channel_id=99)
  db.register_user_alert(1, 42)
  db.register_user_alert(1, 42)
  rid = db.create_review(1, 2, 3, 42, 'texto dudoso', 2, 0.5, 'clasico')
  db.resolve_review(rid, 2, reviewed_by=9)
  db.add_bluesky_watch('ana.bsky.social')
  config.BLUESKY_VIGILANCIA_JSON.write_text(
      json.dumps({'vistos': ['at://x'], 'detectados': []}), encoding='utf-8')


def test_la_copia_contiene_los_mismos_datos_y_se_puede_abrir(entorno):
  _llenar(entorno)
  destino = backup.backup_now(dest_dir=config.BACKUP_DIR)

  copia = sqlite3.connect(destino / config.DB_PATH.name)
  assert copia.execute('PRAGMA integrity_check').fetchone()[0] == 'ok'
  assert copia.execute('SELECT alerts_count FROM user_status').fetchone()[0] == 2
  assert copia.execute('SELECT COUNT(*) FROM admin_feedback').fetchone()[0] == 1
  assert copia.execute('SELECT handle FROM bluesky_watch').fetchone()[0] == 'ana.bsky.social'
  copia.close()

  registro = json.loads((destino / config.BLUESKY_VIGILANCIA_JSON.name).read_text(encoding='utf-8'))
  assert registro['vistos'] == ['at://x']


def test_restaurar_la_copia_recupera_el_estado_de_los_bots(entorno, monkeypatch):
  _llenar(entorno)
  destino = backup.backup_now(dest_dir=config.BACKUP_DIR)
  # Se "pierde" la base original y se apunta a la copia
  config.DB_PATH.unlink()
  monkeypatch.setattr(config, 'DB_PATH', destino / 'bot_database.db')
  assert entorno.get_user_status(1, 42)['alerts_count'] == 2
  assert entorno.list_bluesky_watch() == ['ana.bsky.social']


def test_solo_se_conservan_las_ultimas_copias(entorno, monkeypatch):
  for i in range(5):
    (config.BACKUP_DIR / f'2026010{i}_000000').mkdir(parents=True)
  backup.backup_now(dest_dir=config.BACKUP_DIR, keep=3)
  assert len(list(config.BACKUP_DIR.iterdir())) == 3


def test_sin_base_de_datos_no_falla(tmp_path, monkeypatch):
  monkeypatch.setattr(config, 'DB_PATH', tmp_path / 'no_existe.db')
  assert backup.backup_now(dest_dir=tmp_path / 'b') is None


def test_las_pruebas_no_escriben_en_la_carpeta_real_de_copias(entorno):
  """Protección: la carpeta temporal debe ser distinta de la real."""
  assert config.BACKUP_DIR != config.BASE_DIR / 'backups'
  assert backup.backup_now(dest_dir=config.BACKUP_DIR).parent == config.BACKUP_DIR
