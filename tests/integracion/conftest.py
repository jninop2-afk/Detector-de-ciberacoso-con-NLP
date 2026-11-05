"""Configuración de las pruebas de integración.

A diferencia de las unitarias, aquí los módulos del proyecto se usan REALES y
conectados entre sí: detector + base de datos SQLite + reglas de moderación +
bots + entrenamiento + copias de seguridad. Sólo se simula lo que está fuera
del proyecto (los servidores de Discord y Bluesky).

Todo se ejecuta en una carpeta temporal: nunca toca data/bot_database.db,
models/ ni el registro de vigilancia reales.
"""

import pytest

from src import config as cfg


def pytest_configure(config):
  config.addinivalue_line('markers', 'integracion: pruebas de integración entre módulos')
  config.addinivalue_line('markers', 'lenta: reentrena el modelo (~30-60 s)')


def pytest_collection_modifyitems(items):
  for item in items:
    if '/integracion/' in str(item.fspath).replace('\\', '/'):
      item.add_marker(pytest.mark.integracion)


@pytest.fixture
def entorno(tmp_path, monkeypatch):
  """Base de datos, registro de vigilancia y copias en una carpeta temporal."""
  from src import database
  monkeypatch.setattr(cfg, 'DB_PATH', tmp_path / 'bot_database.db')
  monkeypatch.setattr(cfg, 'BLUESKY_VIGILANCIA_JSON', tmp_path / 'vigilancia_bluesky.json')
  monkeypatch.setattr(cfg, 'BACKUP_DIR', tmp_path / 'backups')
  monkeypatch.setattr(cfg, 'LEGACY_FEEDBACK_CSV', tmp_path / 'no_existe.csv')
  database.init_db()
  return database
