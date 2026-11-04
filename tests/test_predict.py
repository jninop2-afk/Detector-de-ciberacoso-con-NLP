"""Pruebas de src/predict.py (detector híbrido).

La primera parte usa modelos stub para probar la LÓGICA de decisión de forma
aislada y determinista. La segunda usa el modelo entrenado como prueba de
humo (se omite si no se ha ejecutado "python main.py train").
"""

import pytest

from src import config

CLAVES_RESULTADO = {
    'texto_original', 'texto_limpio', 'es_ciberacoso', 'categoria',
    'categoria_gravedad', 'categoria_nombre', 'prob_ciberacoso', 'confianza',
    'confianza_categoria', 'probabilidades', 'motor', 'motivos_sospecha',
    'desacuerdo_modelos', 'prob_clasico', 'prob_roberta', 'notificar_admin',
    'accion_sugerida',
}


# ---------------------------------------------------------------------------
# Lógica de decisión con modelos stub
# ---------------------------------------------------------------------------
def test_predict_devuelve_todas_las_claves_del_contrato(detector_falso):
  r = detector_falso().predict('eres un idiota')
  assert set(r) == CLAVES_RESULTADO


def test_predict_texto_vacio_permite_sin_consultar_modelos(detector_falso):
  r = detector_falso(p_acoso=0.99).predict('!!!')
  assert r['es_ciberacoso'] is False
  assert r['accion_sugerida'] == 'PERMITIR_MENSAJE'
  assert r['prob_clasico'] is None  # no se llamó al modelo


def test_predict_acoso_seguro_sanciona_con_categoria_mas_probable(detector_falso):
  # P(acoso)=0.95 lejos del umbral y categoría 2 con 0.85 -> sin sospechas
  r = detector_falso(p_acoso=0.95, dist=(0.05, 0.85, 0.05, 0.05)).predict('x y')
  assert r['es_ciberacoso'] is True
  assert r['categoria'] == 2
  assert r['categoria_nombre'] == config.CATEGORIES[2]
  assert r['accion_sugerida'] == 'SANCIONAR'


def test_predict_mensaje_limpio_se_permite(detector_falso):
  r = detector_falso(p_acoso=0.02).predict('buenos dias a todos')
  assert r['es_ciberacoso'] is False
  assert r['categoria'] == 0
  assert r['accion_sugerida'] == 'PERMITIR_MENSAJE'


def test_predict_probabilidad_cerca_del_umbral_va_a_revision(detector_falso):
  # 0.45 está a menos de UNCERTAINTY_MARGIN (0.20) del umbral 0.40
  r = detector_falso(p_acoso=0.45).predict('x y')
  assert r['es_ciberacoso'] is True
  assert any('cercana al umbral' in m for m in r['motivos_sospecha'])
  assert r['accion_sugerida'] == 'REVISAR_POR_ADMIN'


def test_predict_categoria_con_confianza_baja_va_a_revision(detector_falso):
  r = detector_falso(p_acoso=0.95, dist=(0.3, 0.3, 0.2, 0.2)).predict('x y')
  assert any('confianza baja' in m for m in r['motivos_sospecha'])
  assert r['accion_sugerida'] == 'REVISAR_POR_ADMIN'


def test_predict_categoria_con_f1_bajo_va_a_revision(detector_falso):
  det = detector_falso(p_acoso=0.95, dist=(0.9, 0.04, 0.03, 0.03),
                       f1_clases={1: 0.40, 2: 0.9, 3: 0.9, 4: 0.9})
  r = det.predict('x y')
  assert r['categoria'] == 1
  assert any('F1 de validación bajo' in m for m in r['motivos_sospecha'])
  assert r['accion_sugerida'] == 'REVISAR_POR_ADMIN'


def test_predict_amenaza_explicita_con_prediccion_segura_genera_sospecha(detector_falso):
  r = detector_falso(p_acoso=0.01).predict('te voy a matar')
  assert 'patrones de amenaza/odio pese a predicción segura' in r['motivos_sospecha']


@pytest.mark.parametrize('p_acoso', [0.0, 0.3, 0.5, 0.9, 1.0])
def test_predict_distribucion_suma_uno(detector_falso, p_acoso):
  r = detector_falso(p_acoso=p_acoso).predict('x y')
  assert sum(r['probabilidades'].values()) == pytest.approx(1.0, abs=1e-3)


def test_predict_fusiona_con_roberta_cuando_hay_sospecha(detector_falso):
  class RobertaStub:
    mode = 'finetuned'

    def predict(self, texto):
      return {'prob_ciberacoso': 0.9, 'modo': 'finetuned',
              'probabilidades': {0: 0.1, 1: 0.0, 2: 0.9, 3: 0.0, 4: 0.0}}

  det = detector_falso(p_acoso=0.45)  # cerca del umbral -> consulta RoBERTa
  det.roberta = RobertaStub()
  r = det.predict('x y')
  assert r['motor'] == 'roberta_finetuned'
  assert r['prob_roberta'] == 0.9
  assert r['categoria'] == 2


def test_predict_si_roberta_falla_usa_el_clasico(detector_falso):
  class RobertaRoto:
    mode = 'finetuned'

    def predict(self, texto):
      raise RuntimeError('sin memoria')

  det = detector_falso(p_acoso=0.45)
  det.roberta = RobertaRoto()
  r = det.predict('x y')
  assert r['motor'] == 'clasico'
  assert 'RoBERTa no disponible' in r['motivos_sospecha']


# ---------------------------------------------------------------------------
# Pruebas de humo con el modelo entrenado
# ---------------------------------------------------------------------------
@pytest.mark.modelo
@pytest.mark.parametrize('texto', ['Hola a todos, ¿cómo van hoy?', 'Buenos días, feliz semana'])
def test_modelo_real_permite_mensajes_neutros(detector_real, texto):
  assert detector_real.predict(texto)['es_ciberacoso'] is False


@pytest.mark.modelo
@pytest.mark.parametrize('texto, categoria', [
    ('eres un hijueputa inutil', 2),
    ('te voy a matar', 1),
])
def test_modelo_real_detecta_acoso_explicito(detector_real, texto, categoria):
  r = detector_real.predict(texto)
  assert r['es_ciberacoso'] is True
  assert r['categoria'] == categoria
