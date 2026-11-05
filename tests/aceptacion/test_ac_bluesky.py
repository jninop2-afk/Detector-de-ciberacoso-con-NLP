"""Pasos de features/proteccion_bluesky.feature."""

import json
import types
from unittest.mock import MagicMock

from atproto import models
import pytest
from pytest_bdd import given, parsers, scenarios, then, when

from src import config
from src.bot_bluesky import bot, vigilancia

scenarios('features/proteccion_bluesky.feature')

BOT = 'nlpguardbot.bsky.social'
YO = 'juan.bsky.social'


class Bluesky:
  """Bluesky simulado: mi cuenta, una publicación mía y sus respuestas."""

  def __init__(self):
    self.publicados, self.reportes, self.respuestas = [], [], []
    self.app, self.com = MagicMock(), MagicMock()
    self.com.atproto.moderation.create_report.side_effect = self.reportes.append

  # bot de menciones
  def send_post(self, text, reply_to):
    self.publicados.append(text)

  def get_current_time_iso(self):
    return '2026-11-05T00:00:00Z'

  # vigilancia
  def get_author_feed(self, cuenta, limit):
    post = types.SimpleNamespace(
        uri='at://juan/post/001', cid='c1', reply_count=len(self.respuestas),
        author=types.SimpleNamespace(handle=YO), record=types.SimpleNamespace(text='mi foto'))
    return types.SimpleNamespace(feed=[types.SimpleNamespace(post=post)] if cuenta == YO else [])

  def get_post_thread(self, uri, depth):
    hilo = MagicMock(spec=models.AppBskyFeedDefs.ThreadViewPost)
    hilo.replies = []
    for i, texto in enumerate(self.respuestas):
      r = MagicMock(spec=models.AppBskyFeedDefs.ThreadViewPost)
      r.post = types.SimpleNamespace(
          uri=f'at://otro/r/{i:03d}', cid=f'r{i}', reply_count=0,
          author=types.SimpleNamespace(handle='troll.bsky.social'),
          record=types.SimpleNamespace(text=texto))
      hilo.replies.append(r)
    return types.SimpleNamespace(thread=hilo)

  def ciclo_vigilancia(self):
    registro = vigilancia.cargar_registro()
    for cuenta, propios in vigilancia.cuentas_a_vigilar().items():
      vigilancia.revisar_cuenta(self, cuenta, registro, propios)
    vigilancia.guardar_registro(registro)
    return registro


@pytest.fixture
def bsky(entorno, detector_real, monkeypatch):
  monkeypatch.setattr(config, 'BLUESKY_HANDLE', BOT)
  monkeypatch.setattr(config, 'BLUESKY_CUENTAS_VIGILADAS', [])
  monkeypatch.setattr(config, 'BLUESKY_REPORTES_REALES', False)
  return Bluesky()


def _mencionar(bsky, texto):
  notif = types.SimpleNamespace(
      uri='at://juan/mencion/1', cid='cm', is_read=False, reason='mention',
      author=types.SimpleNamespace(handle=YO),
      record=types.SimpleNamespace(text=f'@{BOT} {texto}', reply=None))
  bsky.app.bsky.notification.list_notifications.return_value.notifications = [notif]
  bot.procesar_notificaciones(bsky)


# ---------------------------------------------------------------------------
@given('que pedí la vigilancia de mi cuenta')
def ya_vigilado(bsky):
  _mencionar(bsky, 'vigilar')
  bsky.publicados.clear()


@when(parsers.parse('menciono al bot con "{texto}"'))
def menciono(bsky, texto):
  _mencionar(bsky, texto)


@when(parsers.parse('alguien responde "{texto}" a una de mis publicaciones'))
def alguien_responde(bsky, texto):
  bsky.respuestas.append(texto)
  bsky.publicados_antes_de_vigilar = len(bsky.publicados)
  bsky.registro = bsky.ciclo_vigilancia()


# ---------------------------------------------------------------------------
@then('el bot me responde que detectó posible ciberacoso')
def responde_acoso(bsky):
  assert bsky.publicados[-1].startswith('Posible ciberacoso detectado')


@then('la respuesta indica la categoría y la confianza')
def indica_categoria(bsky):
  texto = bsky.publicados[-1]
  assert any(nombre in texto for nombre in list(config.CATEGORIES.values())[1:])
  assert '% de confianza' in texto


@then('la respuesta cabe en un post de Bluesky')
def cabe_en_post(bsky):
  assert len(bsky.publicados[-1]) <= 300


@then('el bot registra esa respuesta como ciberacoso')
def registra(bsky):
  detectados = bsky.registro['detectados']
  assert len(detectados) == 1 and detectados[0]['texto'] == 'ojalá te mueras basura'


@then('el bot no publica nada en esa conversación')
def no_publica(bsky):
  assert len(bsky.publicados) == bsky.publicados_antes_de_vigilar


@then('el bot no registra nada')
def no_registra(bsky):
  assert bsky.registro['detectados'] == []


@then('el bot confirma que lo habría reportado')
def confirma_reporte(bsky):
  assert '[Simulación] Este post se habría reportado' in bsky.publicados[-1]


@then('no se envía ningún reporte real a Bluesky')
def sin_reporte_real(bsky):
  assert bsky.reportes == []
