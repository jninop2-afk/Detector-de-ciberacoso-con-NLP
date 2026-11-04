"""Pruebas de src/features.py (señales léxicas)."""

import numpy as np
import pytest

from src.features import LexiconFeatures, lexicon_signals


@pytest.mark.parametrize('texto', [
    'te voy a matar', 'se donde vives', 'vas a pagar caro', 'cuidate mucho',
])
def test_lexicon_signals_detecta_amenazas(texto):
  assert lexicon_signals(texto)['amenazas'] >= 1


@pytest.mark.parametrize('texto', [
    'ojalá te mueras', 'matate', 'nadie te quiere', 'no mereces vivir',
])
def test_lexicon_signals_detecta_odio_y_muerte(texto):
  assert lexicon_signals(texto)['odio_muerte'] >= 1


def test_lexicon_signals_cuenta_insultos_tras_normalizar_jerga():
  # "hp" y "gnrr" se normalizan a hijueputa y gonorrea
  assert lexicon_signals('hp gnrr')['insultos'] == 2


def test_lexicon_signals_cuenta_terminos_de_difamacion():
  assert lexicon_signals('ese senador es un ladrón corrupto')['difamacion'] == 3


def test_lexicon_signals_mensaje_neutro_sin_senales():
  s = lexicon_signals('buenos dias a todos')
  assert s['insultos'] == s['amenazas'] == s['odio_muerte'] == s['difamacion'] == 0


def test_lexicon_features_devuelve_9_columnas_por_texto():
  X = LexiconFeatures().transform(['ERES UN IDIOTA!!', 'hola', None])
  assert X.shape == (3, 9)
  assert np.isfinite(X).all()


def test_lexicon_features_marca_insulto_dirigido():
  nombres = list(LexiconFeatures.feature_names)
  X = LexiconFeatures().transform(['eres un idiota', 'que idiota'])
  col = nombres.index('insulto_dirigido')
  assert X[0, col] == 1.0  # insulto + "eres"
  assert X[1, col] == 0.0  # insulto sin destinatario


def test_lexicon_features_ratio_mayusculas():
  col = list(LexiconFeatures.feature_names).index('ratio_mayusculas')
  X = LexiconFeatures().transform(['HOLA', 'hola'])
  assert X[0, col] == 1.0 and X[1, col] == 0.0
