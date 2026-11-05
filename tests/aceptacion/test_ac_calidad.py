"""Pasos de features/calidad_deteccion.feature."""

import csv
from pathlib import Path
import time

from pytest_bdd import parsers, scenarios, then, when
import pytest

from src import config

scenarios('features/calidad_deteccion.feature')

CASOS = Path(__file__).parents[1] / 'caja_negra' / 'casos_detector.csv'


@pytest.fixture
def resultado():
  return {}


@when(parsers.parse('el detector analiza "{mensaje}"'))
def analiza(detector_real, resultado, mensaje):
  resultado['r'] = detector_real.predict(mensaje)


@then(parsers.parse('lo clasifica como "{categoria}"'))
def clasifica(resultado, categoria):
  assert resultado['r']['categoria_nombre'] == categoria


@then('lo detecta como ciberacoso')
def detecta(resultado):
  assert resultado['r']['es_ciberacoso'] is True


@when('el detector analiza el conjunto de aceptación')
def analiza_conjunto(detector_real, resultado):
  if not CASOS.exists():
    pytest.skip('Falta tests/caja_negra/casos_detector.csv')
  casos = list(csv.DictReader(CASOS.open(encoding='utf-8')))
  ok_bin = ok_cat = 0
  for c in casos:
    r = detector_real.predict(c['texto'])
    ok_bin += int(r['es_ciberacoso']) == int(c['es_ciberacoso'])
    ok_cat += r['categoria'] == int(c['categoria'])
  resultado.update(binario=ok_bin / len(casos), categoria=ok_cat / len(casos))
  print(f'\nAcierto binario {resultado["binario"]:.1%} | categoría {resultado["categoria"]:.1%}')


@then(parsers.parse('acierta si es acoso o no en al menos el {pct:d} % de los mensajes'))
def acierto_binario(resultado, pct):
  assert resultado['binario'] >= pct / 100


@then(parsers.parse('acierta la categoría en al menos el {pct:d} % de los mensajes'))
def acierto_categoria(resultado, pct):
  assert resultado['categoria'] >= pct / 100


@when(parsers.parse('el detector analiza {n:d} mensajes seguidos'))
def analiza_muchos(detector_real, resultado, n):
  base = ['eres un idiota', 'buenos días', 'te voy a matar', 'qué buen partido', 'ojalá te mueras']
  inicio = time.perf_counter()
  for i in range(n):
    detector_real.predict(base[i % len(base)])
  resultado['ms'] = (time.perf_counter() - inicio) * 1000 / n


@then(parsers.parse('el tiempo promedio por mensaje es menor a {ms:d} ms'))
def tiempo(resultado, ms):
  assert resultado['ms'] < ms
