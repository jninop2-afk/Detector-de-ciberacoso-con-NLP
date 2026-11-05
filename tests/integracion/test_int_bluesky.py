"""Integración: bot de menciones + base de datos + vigilancia + detector + registro.

Recorre el flujo real entre los dos procesos de Bluesky: una persona pide
"vigilar" al bot de menciones, eso queda en SQLite, el proceso de vigilancia
lee la base de datos, analiza las respuestas que recibe esa cuenta con el
detector y guarda lo detectado en el registro JSON.
"""

import json
import types
from unittest.mock import MagicMock

from atproto import models
import pytest

from src import config
from src.bot_bluesky import bot, vigilancia

BOT = 'nlpguardbot.bsky.social'
ANA = 'ana.bsky.social'


def _post(uri, autor, texto, respuestas=0):
  return types.SimpleNamespace(
      uri=uri, cid='cid-' + uri[-3:], reply_count=respuestas,
      author=types.SimpleNamespace(handle=autor),
      record=types.SimpleNamespace(text=texto),
  )


class BlueskyFalso:
  """Servidor de Bluesky simulado con un post de Ana y sus respuestas."""

  def __init__(self, respuestas):
    self.publicados = []
    self.post_ana = _post('at://ana/post/001', ANA, 'eres un idiota (post propio de Ana)',
                          respuestas=len(respuestas))
    self.respuestas = respuestas
    self.app = MagicMock()
    self.com = MagicMock()

  # --- usado por el bot de menciones ---
  def send_post(self, text, reply_to):
    self.publicados.append(text)

  def get_current_time_iso(self):
    return '2026-11-04T00:00:00Z'

  # --- usado por la vigilancia ---
  def get_author_feed(self, cuenta, limit):
    feed = [types.SimpleNamespace(post=self.post_ana)] if cuenta == ANA else []
    return types.SimpleNamespace(feed=feed)

  def get_post_thread(self, uri, depth):
    hilo = MagicMock(spec=models.AppBskyFeedDefs.ThreadViewPost)
    hilo.replies = []
    for p in self.respuestas:
      r = MagicMock(spec=models.AppBskyFeedDefs.ThreadViewPost)
      r.post = p
      hilo.replies.append(r)
    return types.SimpleNamespace(thread=hilo)


def _mencion(texto, autor=ANA):
  return types.SimpleNamespace(
      uri='at://ana/mencion/1', cid='cid-m', is_read=False, reason='mention',
      author=types.SimpleNamespace(handle=autor),
      record=types.SimpleNamespace(text=f'@{BOT} {texto}', reply=None),
  )


@pytest.fixture
def cliente(entorno, detector_real, monkeypatch):
  monkeypatch.setattr(config, 'BLUESKY_HANDLE', BOT)
  monkeypatch.setattr(config, 'BLUESKY_CUENTAS_VIGILADAS', [])
  monkeypatch.setattr(config, 'BLUESKY_REPORTES_REALES', False)
  return BlueskyFalso([
      _post('at://x/r/001', 'troll.bsky.social', 'ojalá te mueras basura'),
      _post('at://x/r/002', 'amigo.bsky.social', 'qué buena foto, felicitaciones'),
  ])


def _pedir(cliente, texto):
  cliente.app.bsky.notification.list_notifications.return_value.notifications = [_mencion(texto)]
  bot.procesar_notificaciones(cliente)


def _ciclo_vigilancia(cliente):
  """Un ciclo del bucle principal de vigilancia (sin el sleep)."""
  registro = vigilancia.cargar_registro()
  for cuenta, propios in vigilancia.cuentas_a_vigilar().items():
    vigilancia.revisar_cuenta(cliente, cuenta, registro, propios)
  vigilancia.guardar_registro(registro)
  return json.loads(config.BLUESKY_VIGILANCIA_JSON.read_text(encoding='utf-8'))


def test_pedir_vigilancia_hace_que_el_otro_proceso_vigile_la_cuenta(cliente, entorno):
  _pedir(cliente, 'vigilar')
  assert vigilancia.cuentas_a_vigilar() == {ANA: False}  # sin analizar sus propios posts

  registro = _ciclo_vigilancia(cliente)
  detectados = registro['detectados']
  assert [d['autor'] for d in detectados] == ['troll.bsky.social']
  assert detectados[0]['categoria'] in (2, 3)
  assert detectados[0]['tipo'] == 'respuesta recibida'
  assert detectados[0]['accion'].startswith('[Simulación]')


def test_los_posts_propios_de_quien_pidio_vigilancia_no_se_analizan(cliente, entorno):
  _pedir(cliente, 'vigilar')
  registro = _ciclo_vigilancia(cliente)
  assert 'at://ana/post/001' not in registro['vistos']


def test_un_segundo_ciclo_no_duplica_detecciones(cliente, entorno):
  _pedir(cliente, 'vigilar')
  _ciclo_vigilancia(cliente)
  registro = _ciclo_vigilancia(cliente)
  assert len(registro['detectados']) == 1


def test_dejar_de_vigilar_saca_la_cuenta_del_proceso(cliente, entorno):
  _pedir(cliente, 'vigilar')
  _pedir(cliente, 'dejar de vigilar')
  assert vigilancia.cuentas_a_vigilar() == {}
  assert _ciclo_vigilancia(cliente)['detectados'] == []


def test_cuentas_del_env_tambien_analizan_sus_posts(cliente, entorno, monkeypatch):
  monkeypatch.setattr(config, 'BLUESKY_CUENTAS_VIGILADAS', [ANA])
  assert vigilancia.cuentas_a_vigilar() == {ANA: True}
  registro = _ciclo_vigilancia(cliente)
  tipos = {d['tipo'] for d in registro['detectados']}
  assert tipos == {'publicación propia', 'respuesta recibida'}
