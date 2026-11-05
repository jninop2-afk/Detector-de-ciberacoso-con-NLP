"""Configuración de las pruebas de aceptación.

Las historias de usuario están en features/*.feature (Gherkin en español) y
los pasos ("Dado", "Cuando", "Entonces") se implementan en test_*.py con
pytest-bdd. El sistema se ejecuta con sus módulos reales; sólo se simulan los
servidores de Discord y Bluesky.
"""

import pytest

from src import config as cfg


def pytest_configure(config):
  config.addinivalue_line('markers', 'aceptacion: pruebas de aceptación (historias de usuario)')


def pytest_collection_modifyitems(items):
  for item in items:
    if '/aceptacion/' in str(item.fspath).replace('\\', '/'):
      item.add_marker(pytest.mark.aceptacion)


@pytest.fixture
def entorno(tmp_path, monkeypatch):
  """Base de datos y registro de vigilancia en una carpeta temporal."""
  from src import database
  monkeypatch.setattr(cfg, 'DB_PATH', tmp_path / 'bot_database.db')
  monkeypatch.setattr(cfg, 'BLUESKY_VIGILANCIA_JSON', tmp_path / 'vigilancia_bluesky.json')
  monkeypatch.setattr(cfg, 'LEGACY_FEEDBACK_CSV', tmp_path / 'no_existe.csv')
  database.init_db()
  return database
