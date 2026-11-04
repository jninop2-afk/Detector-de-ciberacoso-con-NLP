"""Pruebas de src/data.py (unificación de datasets) y src/translate_english.py."""

import pandas as pd
import pytest

from src import config, data
from src.translate_english import subclasificar


# ---------------------------------------------------------------------------
# data._finalize: limpieza, filtrado y deduplicación
# ---------------------------------------------------------------------------
def _df(filas):
  return pd.DataFrame(filas, columns=['texto', 'ciberacoso', 'categoria', 'fuente'])


def test_finalize_descarta_textos_de_una_palabra():
  df = data._finalize(_df([('hola', 0, 0, 'colombia'), ('hola amigos', 0, 0, 'colombia')]))
  assert df['texto'].tolist() == ['hola amigos']


def test_finalize_conserva_una_palabra_si_la_etiqueto_un_humano():
  df = data._finalize(_df([('idiota', 1, 2, 'feedback')]))
  assert len(df) == 1


def test_finalize_ante_duplicados_gana_la_fuente_mas_confiable():
  df = data._finalize(_df([
      ('Eres un idiota', 1, 3, 'colombia'),
      ('eres un IDIOTA!!', 1, 2, 'feedback'),  # mismo texto limpio
  ]))
  assert len(df) == 1
  assert df.iloc[0]['fuente'] == 'feedback'
  assert df.iloc[0]['categoria'] == 2


def test_finalize_ingles_traducido_tiene_la_menor_prioridad():
  assert data.SOURCE_PRIORITY['ingles'] < min(
      v for k, v in data.SOURCE_PRIORITY.items() if k != 'ingles')


def test_load_english_translated_sin_cache_devuelve_vacio(tmp_path, monkeypatch):
  monkeypatch.setattr(config, 'ENGLISH_TRANSLATED_CSV', tmp_path / 'no_existe.csv')
  assert data.load_english_translated().empty


def test_load_english_translated_lee_el_cache(tmp_path, monkeypatch):
  ruta = tmp_path / 'ingles.csv'
  pd.DataFrame({'origen': ['x'], 'texto_en': ['you idiot'], 'texto': ['tu idiota'],
                'ciberacoso': [1], 'categoria': [2]}).to_csv(ruta, index=False)
  monkeypatch.setattr(config, 'ENGLISH_TRANSLATED_CSV', ruta)
  df = data.load_english_translated()
  assert df.iloc[0].to_dict() == {'texto': 'tu idiota', 'ciberacoso': 1,
                                  'categoria': 2, 'fuente': 'ingles'}


# ---------------------------------------------------------------------------
# translate_english.subclasificar: categorías 1-4 por reglas
# ---------------------------------------------------------------------------
@pytest.mark.parametrize('texto, anotacion, esperado', [
    ('te voy a matar', '', 1),
    ('ojalá te mueras', '', 3),
    ('ese político es un ladrón', '', 4),
    ('eres un idiota', '', 2),               # por defecto: insulto
    ('texto neutro', 'threat', 1),          # la anotación también cuenta
    ('te voy a matar ladrón', '', 1),       # la amenaza tiene prioridad
])
def test_subclasificar(texto, anotacion, esperado):
  assert subclasificar(texto, anotacion) == esperado
