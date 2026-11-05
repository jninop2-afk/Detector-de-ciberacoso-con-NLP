"""Caja negra de la aplicación completa: se ejecuta "python main.py" como lo
haría un usuario y sólo se mira lo que imprime en la terminal.
"""

import os
from pathlib import Path
import subprocess
import sys

import pytest

RAIZ = Path(__file__).resolve().parents[2]


def _ejecutar(args, entrada=''):
  env = {**os.environ, 'ROBERTA_ENABLED': '0', 'PYTHONIOENCODING': 'utf-8'}
  return subprocess.run(
      [sys.executable, 'main.py', *args], input=entrada, cwd=RAIZ, env=env,
      capture_output=True, text=True, timeout=120,
  )


def test_ayuda_lista_todos_los_comandos():
  salida = _ejecutar(['--help']).stdout
  for comando in ['cli', 'train', 'bot', 'bluesky', 'vigilancia', 'bluesky-diag', 'traducir']:
    assert comando in salida


@pytest.fixture
def con_modelo(detector_real):
  """Sólo para comprobar que el modelo existe (se omite si no)."""


def test_consola_detecta_acoso_y_sale_con_salir(con_modelo):
  p = _ejecutar(['cli', '--sin-roberta'], 'eres un hijueputa inútil\nsalir\n')
  assert p.returncode == 0
  assert '[ POSIBLE CIBERACOSO ]' in p.stdout
  assert 'Insultos y ofensas personales' in p.stdout


def test_consola_mensaje_neutro_es_seguro(con_modelo):
  p = _ejecutar(['cli', '--sin-roberta'], 'buenos días a todos\nsalir\n')
  assert '[ MENSAJE SEGURO ]' in p.stdout
  assert 'PERMITIR_MENSAJE' in p.stdout


def test_consola_analiza_varios_mensajes_seguidos(con_modelo):
  p = _ejecutar(['cli', '--sin-roberta'], 'hola\nte voy a matar\nqué buen día\nsalir\n')
  assert p.stdout.count('ACCIÓN SUGERIDA') == 3


def test_consola_ignora_lineas_vacias(con_modelo):
  p = _ejecutar(['cli', '--sin-roberta'], '\n\n   \nsalir\n')
  assert p.returncode == 0
  assert 'ACCIÓN SUGERIDA' not in p.stdout


@pytest.mark.parametrize('palabra', ['salir', 'SALIR', 'exit', 'quit'])
def test_consola_palabras_de_salida(con_modelo, palabra):
  assert _ejecutar(['cli', '--sin-roberta'], f'{palabra}\n').returncode == 0


def test_consola_termina_bien_si_se_cierra_la_entrada(con_modelo):
  # Equivale a presionar Ctrl+D
  p = _ejecutar(['cli', '--sin-roberta'], 'hola\n')
  assert p.returncode == 0
  assert 'Saliendo...' in p.stdout
