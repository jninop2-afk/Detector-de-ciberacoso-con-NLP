"""Integración: feedback de moderadores -> datasets -> entrenamiento -> detector.

Verifica que las piezas del ciclo de aprendizaje encajan: lo que un moderador
corrige en SQLite llega al dataset, el entrenamiento produce un modelo que el
detector puede cargar, y el modelo guardado es coherente con el código actual
de preprocesamiento.
"""

import json

import pytest

from src import config, data


def _feedback(db, guild, texto, categoria, confiable):
  db.set_guild_trusted(guild, confiable)
  rid = db.create_review(guild, 1, 1, 5, texto, categoria, 0.5, 'clasico')
  db.resolve_review(rid, categoria, reviewed_by=1)


def test_solo_el_feedback_de_servidores_de_confianza_llega_al_dataset(entorno):
  _feedback(entorno, 1, 'mensaje corregido en servidor confiable', 2, True)
  _feedback(entorno, 2, 'mensaje de servidor externo no confiable', 0, False)

  dataset = data.build_binary_dataset()
  textos = dataset.loc[dataset['fuente'] == 'feedback', 'texto'].tolist()
  assert 'mensaje corregido en servidor confiable' in textos
  assert 'mensaje de servidor externo no confiable' not in textos


def test_el_feedback_humano_prevalece_sobre_el_dataset_original(entorno):
  # Un texto que ya existe en el dataset colombiano, re-etiquetado por un moderador
  original = data.load_colombian().iloc[0]
  _feedback(entorno, 1, original['texto'], 4, True)
  fila = data.build_category_dataset().query('texto == @original.texto')
  assert fila['fuente'].tolist() == ['feedback']
  assert fila['categoria'].tolist() == [4]


@pytest.mark.lenta
def test_reentrenar_genera_un_modelo_que_el_detector_puede_usar(entorno, tmp_path, monkeypatch):
  from src.feedback import retrain_from_feedback
  from src.predict import CyberbullyingDetector

  monkeypatch.setattr(config, 'MODELS_DIR', tmp_path / 'models')
  monkeypatch.setattr(config, 'CLASSIC_MODEL_PATH', tmp_path / 'models' / 'classic_model.joblib')
  monkeypatch.setattr(config, 'CLASSIC_METRICS_PATH', tmp_path / 'models' / 'classic_metrics.json')
  _feedback(entorno, 1, 'sos un pelmazo insoportable', 2, True)

  metricas = retrain_from_feedback()

  assert config.CLASSIC_MODEL_PATH.exists()
  guardadas = json.loads(config.CLASSIC_METRICS_PATH.read_text(encoding='utf-8'))
  assert guardadas['binario']['f1_ciberacoso'] == pytest.approx(metricas['binario']['f1_ciberacoso'])
  assert metricas['binario']['f1_ciberacoso'] > 0.75
  assert metricas['gravedad']['f1_macro'] > 0.80

  detector = CyberbullyingDetector(model_path=config.CLASSIC_MODEL_PATH, use_roberta=False)
  assert detector.predict('te voy a matar')['categoria'] == 1
  assert detector.predict('buenos días a todos')['es_ciberacoso'] is False


def test_modelo_guardado_es_coherente_con_el_codigo_actual(detector_real):
  """Si alguien cambia el preprocesamiento sin reentrenar, esto lo detecta."""
  textos = ['eres un hijueputa inútil', 'buenos días', 'te voy a matar', 'ojalá te mueras']
  lote = detector_real.predict_classic_batch(textos)
  for i, t in enumerate(textos):
    individual = detector_real.predict(t)
    assert individual['prob_clasico'] == pytest.approx(float(lote['prob_ciberacoso'][i]), abs=1e-4)

  guardadas = json.loads(config.CLASSIC_METRICS_PATH.read_text(encoding='utf-8'))
  assert detector_real.binary_threshold == guardadas['binario']['umbral']
