"""Pruebas de src/preprocessing.py (normalización de texto)."""

import pytest

from src.preprocessing import (
    clean_text, decode_leetspeak, normalize_slang, preprocess_for_transformer,
    strip_accents,
)


@pytest.mark.parametrize('entrada', ['', None, 123, '   '])
def test_clean_text_entradas_vacias_o_no_texto_devuelve_cadena_vacia(entrada):
  assert clean_text(entrada) == ''


@pytest.mark.parametrize('entrada, esperado', [
    ('S4P4 HIJ0 D3 PUT4', 'sapo hijo de puta'),
    ('p3rr0', 'perro'),
])
def test_clean_text_decodifica_leetspeak(entrada, esperado):
  assert clean_text(entrada) == esperado


@pytest.mark.parametrize('jerga, canonica', [
    ('hp', 'hijueputa'), ('hpta', 'hijueputa'), ('hdp', 'hijueputa'),
    ('gonorria', 'gonorrea'), ('mlp', 'malparido'), ('mk', 'marica'),
    ('gvn', 'huevon'), ('q', 'que'), ('xq', 'porque'),
])
def test_clean_text_unifica_jerga_colombiana(jerga, canonica):
  assert clean_text(jerga) == canonica


def test_clean_text_reemplaza_menciones_y_quita_urls_y_hashtags():
  assert clean_text('Mira @juan https://x.co #Colombia') == 'mira usuario colombia'


def test_clean_text_reduce_letras_alargadas():
  assert clean_text('Holaaaaa') == 'hola'


def test_clean_text_normaliza_risas():
  assert clean_text('jajajajaja que risa') == 'jaja que risa'


def test_clean_text_quita_tildes_pero_conserva_la_enie():
  assert clean_text('Niño CANCIÓN') == 'niño cancion'


def test_clean_text_elimina_numeros_puros_y_puntuacion():
  assert clean_text('Año 2000 ¡hola!') == 'año hola'


def test_clean_text_quita_marca_de_retweet():
  assert clean_text('RT @x hola') == 'usuario hola'


def test_clean_text_convierte_emojis_en_tokens():
  assert 'emoji_cara_de_payaso' in clean_text('eres un payaso 🤡')


def test_decode_leetspeak_no_altera_numeros_puros():
  assert decode_leetspeak('tengo 2000 pesos') == 'tengo 2000 pesos'


def test_decode_leetspeak_conserva_puntuacion_final():
  assert decode_leetspeak('h0la!') == 'hola!'


def test_strip_accents_conserva_enie():
  assert strip_accents('canción ñandú') == 'cancion ñandu'


def test_normalize_slang_no_cambia_palabras_desconocidas():
  assert normalize_slang('hola mundo') == 'hola mundo'


def test_preprocess_for_transformer_es_ligero():
  # Conserva la estructura: usa marcadores en vez de borrar y deja 2 letras repetidas
  assert preprocess_for_transformer('Holaaaa @juan https://x.co') == 'holaa @usuario url'
