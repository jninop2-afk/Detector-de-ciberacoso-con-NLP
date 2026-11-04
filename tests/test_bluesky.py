"""Pruebas de la lógica de los bots de Bluesky (src/bot_bluesky/common.py).

El cliente de Bluesky se sustituye por un MagicMock: no se usa la red.
"""

from unittest.mock import MagicMock

import pytest

from src import config
from src.bot_bluesky import common


def _resultado(es=True, confianza=0.9, accion='SANCIONAR', categoria=2):
  return {
      'es_ciberacoso': es, 'confianza': confianza, 'accion_sugerida': accion,
      'categoria': categoria, 'categoria_nombre': config.CATEGORIES[categoria],
  }


@pytest.mark.parametrize('texto, esperado', [
    ('@nlpguardbot.bsky.social eres un idiota', 'eres un idiota'),
    ('hola @a.bsky.social y @b.bsky.social', 'hola  y'),
    ('', ''),
    (None, ''),
])
def test_limpiar_menciones(texto, esperado):
  assert common.limpiar_menciones(texto) == esperado


def test_respuesta_sin_acoso():
  r = _resultado(es=False, confianza=0.97, accion='PERMITIR_MENSAJE', categoria=0)
  assert common.construir_respuesta(r) == 'No detecté ciberacoso en ese mensaje (97% de confianza).'


def test_respuesta_con_acoso_incluye_categoria_y_aviso():
  texto = common.construir_respuesta(_resultado(confianza=0.91))
  assert 'Insultos y ofensas personales (91% de confianza)' in texto
  assert 'puede equivocarse' in texto


def test_respuesta_caso_dudoso_pide_revision_humana():
  texto = common.construir_respuesta(_resultado(accion='REVISAR_POR_ADMIN'))
  assert 'requiere revisión humana' in texto


def test_respuesta_respeta_limite_de_300_caracteres(monkeypatch):
  r = _resultado()
  r['categoria_nombre'] = 'x' * 500
  assert len(common.construir_respuesta(r)) <= common.MAX_CARACTERES


def test_no_reporta_si_no_hay_acoso():
  cliente = MagicMock()
  msg = common.gestionar_reporte(cliente, _resultado(es=False), 'at://x', 'cid')
  assert msg == 'No hay nada que reportar.'
  cliente.com.atproto.moderation.create_report.assert_not_called()


def test_no_reporta_casos_dudosos():
  cliente = MagicMock()
  msg = common.gestionar_reporte(cliente, _resultado(accion='REVISAR_POR_ADMIN'), 'at://x', 'cid')
  assert 'revisión humana' in msg
  cliente.com.atproto.moderation.create_report.assert_not_called()


def test_no_reporta_bajo_el_umbral(monkeypatch):
  monkeypatch.setattr(config, 'BLUESKY_UMBRAL_REPORTE', 0.80)
  cliente = MagicMock()
  msg = common.gestionar_reporte(cliente, _resultado(confianza=0.79), 'at://x', 'cid')
  assert msg == 'No lo reporté: la confianza es menor a 80%.'


def test_modo_simulacion_no_envia_reporte(monkeypatch):
  monkeypatch.setattr(config, 'BLUESKY_REPORTES_REALES', False)
  cliente = MagicMock()
  msg = common.gestionar_reporte(cliente, _resultado(), 'at://x', 'cid')
  assert msg.startswith('[Simulación]')
  cliente.com.atproto.moderation.create_report.assert_not_called()


def test_modo_real_envia_reporte_una_vez(monkeypatch):
  monkeypatch.setattr(config, 'BLUESKY_REPORTES_REALES', True)
  cliente = MagicMock()
  msg = common.gestionar_reporte(cliente, _resultado(), 'at://post', 'cid123')
  assert msg == 'Reporte enviado a la moderación de Bluesky.'
  cliente.com.atproto.moderation.create_report.assert_called_once()


def test_login_sin_credenciales_no_conecta(monkeypatch, capsys):
  monkeypatch.setattr(config, 'BLUESKY_HANDLE', None)
  assert common.login() is None
  assert 'faltan BLUESKY_HANDLE' in capsys.readouterr().out
