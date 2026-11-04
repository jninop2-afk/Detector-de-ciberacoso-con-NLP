"""Configuración compartida de las pruebas unitarias.

Las pruebas nunca usan RoBERTa, red, Discord ni Bluesky reales: todo lo
externo se sustituye por dobles de prueba.
"""

import os

# Debe fijarse ANTES de importar src.config (lee el entorno al importarse)
os.environ['ROBERTA_ENABLED'] = '0'
os.environ['BLUESKY_REPORTES_REALES'] = '0'

import pytest  # noqa: E402

from src import config  # noqa: E402


class FakeBinary:
  """Stub del pipeline binario: devuelve una P(acoso) fija."""

  def __init__(self, p_acoso: float):
    self.p = p_acoso

  def predict_proba(self, textos):
    return [[1 - self.p, self.p] for _ in textos]


class FakeSeverity:
  """Stub del pipeline de gravedad: distribución fija sobre las clases 1-4."""

  classes_ = [1, 2, 3, 4]

  def __init__(self, dist):
    self.dist = dist

  def predict_proba(self, textos):
    return [list(self.dist) for _ in textos]


@pytest.fixture
def detector_falso():
  """Fábrica de detectores con modelos stub (sin cargar ningún archivo)."""
  from src.predict import CyberbullyingDetector

  def _crear(p_acoso=0.9, dist=(0.05, 0.85, 0.05, 0.05), umbral=0.4,
             f1_binario=0.82, f1_clases=None):
    d = object.__new__(CyberbullyingDetector)
    d.binary = FakeBinary(p_acoso)
    d.severity = FakeSeverity(dist)
    d.binary_threshold = umbral
    d.threshold = config.CONFIDENCE_THRESHOLD
    d.severity_classes = [1, 2, 3, 4]
    d.binary_f1 = f1_binario
    d.class_f1 = f1_clases or {1: 0.9, 2: 0.9, 3: 0.9, 4: 0.9}
    d.metrics = {}
    d.roberta = None
    return d

  return _crear


@pytest.fixture(scope='session')
def detector_real():
  """Detector con el modelo entrenado (se omite si aún no existe)."""
  if not config.CLASSIC_MODEL_PATH.exists():
    pytest.skip('Falta models/classic_model.joblib: ejecuta "python main.py train"')
  from src.predict import CyberbullyingDetector
  return CyberbullyingDetector(use_roberta=False)


@pytest.fixture
def db_temporal(tmp_path, monkeypatch):
  """Base de datos SQLite aislada en una carpeta temporal."""
  from src import database
  monkeypatch.setattr(config, 'DB_PATH', tmp_path / 'test.db')
  database.init_db()
  return database
