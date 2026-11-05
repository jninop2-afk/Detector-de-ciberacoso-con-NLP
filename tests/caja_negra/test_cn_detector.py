"""Caja negra del detector: entrada = mensaje, salida = decisión.

Técnica: particiones de equivalencia. Cada fila de casos_detector.csv
pertenece a una partición de la especificación (P0 neutro, P1 amenaza,
P2 insulto, P3 odio/muerte, P4 difamación, y ofuscaciones). El resultado
esperado lo definió una persona leyendo el mensaje, NO el modelo.

Los casos con la columna "hallazgo" son errores conocidos del modelo: se
marcan como xfail (fallo esperado) para que queden documentados sin romper
la suite. Si un reentrenamiento los corrige, pytest avisa con XPASS y hay
que quitar el hallazgo del CSV.

Además se genera reportes/caja_negra_detector.csv con el resultado real y
el estado de cada caso (plantilla de documentación de casos de prueba).
"""

import csv
from pathlib import Path
import time

import pytest

from src import config

CASOS_CSV = Path(__file__).with_name('casos_detector.csv')
REPORTE = config.BASE_DIR / 'reportes' / 'caja_negra_detector.csv'
CASOS = list(csv.DictReader(CASOS_CSV.open(encoding='utf-8')))

# Umbrales mínimos de calidad sobre el conjunto de casos
MIN_ACIERTO_BINARIO = 0.90
MIN_ACIERTO_CATEGORIA = 0.85
MIN_ACIERTO_POR_PARTICION = 0.70


def _param(caso):
  marcas = []
  if caso['hallazgo']:
    marcas.append(pytest.mark.xfail(reason=caso['hallazgo'], strict=True))
  return pytest.param(caso, id=caso['id'], marks=marcas)


# ---------------------------------------------------------------------------
# 1. Un caso por fila: ¿la decisión coincide con la especificación?
# ---------------------------------------------------------------------------
@pytest.mark.parametrize('caso', [_param(c) for c in CASOS])
def test_caso_detector(detector_real, caso):
  r = detector_real.predict(caso['texto'])
  assert int(r['es_ciberacoso']) == int(caso['es_ciberacoso']), (
      f'{caso["id"]}: se esperaba es_ciberacoso={caso["es_ciberacoso"]}')
  assert r['categoria'] == int(caso['categoria']), (
      f'{caso["id"]}: se esperaba categoría {caso["categoria"]}, '
      f'se obtuvo {r["categoria"]} ({r["categoria_nombre"]})')


# ---------------------------------------------------------------------------
# 2. Calidad global y por partición + reporte documentado
# ---------------------------------------------------------------------------
def test_calidad_global_y_reporte(detector_real):
  filas, ok_bin, ok_cat = [], 0, 0
  por_particion: dict[str, list[bool]] = {}
  for c in CASOS:
    r = detector_real.predict(c['texto'])
    b = int(r['es_ciberacoso']) == int(c['es_ciberacoso'])
    k = r['categoria'] == int(c['categoria'])
    ok_bin += b
    ok_cat += k
    por_particion.setdefault(c['particion'].split()[0], []).append(b and k)
    filas.append({
        'ID del caso': c['id'],
        'Partición': c['particion'],
        'Datos de entrada': c['texto'],
        'Resultado esperado': f'{c["es_ciberacoso"]} / categoría {c["categoria"]}',
        'Resultado real': f'{int(r["es_ciberacoso"])} / categoría {r["categoria"]} '
                          f'({r["accion_sugerida"]}, {r["confianza"]:.2f})',
        'Estado': 'Aprobado' if (b and k) else 'Fallido',
        'Observaciones': c['hallazgo'],
    })

  REPORTE.parent.mkdir(exist_ok=True)
  with REPORTE.open('w', encoding='utf-8', newline='') as f:
    w = csv.DictWriter(f, fieldnames=list(filas[0]))
    w.writeheader()
    w.writerows(filas)

  n = len(CASOS)
  print(f'\nAcierto binario: {ok_bin}/{n} | categoría: {ok_cat}/{n} | reporte: {REPORTE}')
  assert ok_bin / n >= MIN_ACIERTO_BINARIO
  assert ok_cat / n >= MIN_ACIERTO_CATEGORIA
  for particion, res in por_particion.items():
    assert sum(res) / len(res) >= MIN_ACIERTO_POR_PARTICION, f'partición {particion}'


# ---------------------------------------------------------------------------
# 3. Entradas límite e inválidas (robustez)
# ---------------------------------------------------------------------------
ACCIONES = {'PERMITIR_MENSAJE', 'REVISAR_POR_ADMIN', 'SANCIONAR'}


@pytest.mark.parametrize('texto', [
    pytest.param('', id='CN-ROB-001 vacío'),
    pytest.param('     ', id='CN-ROB-002 sólo espacios'),
    pytest.param('!!!???...', id='CN-ROB-003 sólo puntuación'),
    pytest.param('1234567890', id='CN-ROB-004 sólo números'),
    pytest.param('https://ejemplo.com/pagina', id='CN-ROB-005 sólo URL'),
])
def test_entradas_sin_contenido_se_permiten(detector_real, texto):
  r = detector_real.predict(texto)
  assert r['es_ciberacoso'] is False
  assert r['accion_sugerida'] == 'PERMITIR_MENSAJE'


@pytest.mark.xfail(strict=True, reason='Hallazgo CN-ROB-006: una mención sola va a revisión')
def test_mencion_sola_se_permite(detector_real):
  assert detector_real.predict('@juan')['accion_sugerida'] == 'PERMITIR_MENSAJE'


@pytest.mark.parametrize('texto', [
    pytest.param('hola ' * 2000, id='CN-ROB-007 10.000 caracteres'),
    pytest.param('a' * 5000, id='CN-ROB-008 palabra de 5.000 letras'),
    pytest.param('🤡😡💀' * 50, id='CN-ROB-009 sólo emojis'),
    pytest.param('مرحبا 你好 привет', id='CN-ROB-010 otros alfabetos'),
    pytest.param('<script>alert(1)</script>', id='CN-ROB-011 HTML'),
])
def test_entradas_extremas_no_rompen_el_sistema(detector_real, texto):
  inicio = time.perf_counter()
  r = detector_real.predict(texto)
  assert r['accion_sugerida'] in ACCIONES
  assert 0.0 <= r['confianza'] <= 1.0
  assert time.perf_counter() - inicio < 2.0, 'tarda más de 2 s'


# ---------------------------------------------------------------------------
# 4. Propiedades observables
# ---------------------------------------------------------------------------
def test_misma_entrada_misma_salida(detector_real):
  a = detector_real.predict('eres un idiota')
  b = detector_real.predict('eres un idiota')
  assert a == b


@pytest.mark.parametrize('variante', [
    'ERES UN ESTÚPIDO', 'eres un estupido', 'Eres un estúpido!!!', 'eres un estupidoooo',
])
def test_mayusculas_tildes_y_alargamientos_no_cambian_la_decision(detector_real, variante):
  base = detector_real.predict('eres un estúpido')
  r = detector_real.predict(variante)
  assert (r['es_ciberacoso'], r['categoria']) == (base['es_ciberacoso'], base['categoria'])
