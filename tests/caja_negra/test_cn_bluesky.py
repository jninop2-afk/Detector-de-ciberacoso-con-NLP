"""Caja negra del bot de Bluesky por menciones.

Se simula el servidor de Bluesky con un cliente falso: el bot "recibe"
notificaciones y se observa únicamente lo que publica como respuesta.

Técnicas: tabla de decisión (comandos de la mención) y valores límite
(cupo de vigilancia y umbral de reporte).
"""

import types
from unittest.mock import MagicMock

from atproto import models
import pytest

from src import config
from src.bot_bluesky import bot

BOT = 'nlpguardbot.bsky.social'


class ClienteFalso:
  """Sustituye al servidor de Bluesky y guarda lo que el bot publica."""

  def __init__(self, notificaciones, padres=None):
    self._notifs = notificaciones
    self._padres = padres or {}
    self.publicados = []
    self.reportes = []
    self.app = MagicMock()
    self.app.bsky.notification.list_notifications.return_value.notifications = notificaciones
    self.com = MagicMock()
    self.com.atproto.moderation.create_report.side_effect = self.reportes.append

  def get_posts(self, uris):
    return types.SimpleNamespace(posts=[self._padres[u] for u in uris if u in self._padres])

  def send_post(self, text, reply_to):
    self.publicados.append(text)

  def get_current_time_iso(self):
    return '2026-11-04T00:00:00Z'


def _mencion(texto, autor='usuario.bsky.social', leida=False, padre=None, n=[0]):
  n[0] += 1
  reply = None
  if padre:
    raiz = models.ComAtprotoRepoStrongRef.Main(uri=padre, cid='cid-raiz')
    reply = types.SimpleNamespace(parent=types.SimpleNamespace(uri=padre), root=raiz)
  return types.SimpleNamespace(
      uri=f'at://mencion/{n[0]}', cid=f'cid{n[0]}', is_read=leida, reason='mention',
      author=types.SimpleNamespace(handle=autor),
      record=types.SimpleNamespace(text=f'@{BOT} {texto}', reply=reply),
  )


def _post(texto, uri='at://post/1'):
  return types.SimpleNamespace(record=types.SimpleNamespace(text=texto), uri=uri, cid='cid-post')


@pytest.fixture
def entorno(db_temporal, detector_real, monkeypatch):
  """Base de datos aislada, modelo real y modo simulación de reportes."""
  monkeypatch.setattr(config, 'BLUESKY_HANDLE', BOT)
  monkeypatch.setattr(config, 'BLUESKY_REPORTES_REALES', False)
  monkeypatch.setattr(config, 'BLUESKY_UMBRAL_REPORTE', 0.60)
  return db_temporal


def _procesar(*notifs, padres=None):
  cliente = ClienteFalso(list(notifs), padres)
  bot.procesar_notificaciones(cliente)
  return cliente


# ---------------------------------------------------------------------------
# Análisis de mensajes
# ---------------------------------------------------------------------------
def test_mencion_con_acoso_responde_categoria(entorno):
  c = _procesar(_mencion('te voy a matar cuando te vea'))
  assert len(c.publicados) == 1
  assert c.publicados[0].startswith('Posible ciberacoso detectado: Hostigamiento y amenazas')


def test_mencion_neutra_responde_que_no_hay_acoso(entorno):
  c = _procesar(_mencion('hola, buenos días a todos'))
  assert c.publicados[0].startswith('No detecté ciberacoso')


def test_respuesta_a_un_post_analiza_el_post_original(entorno):
  padre = _post('eres un hijueputa inútil', uri='at://post/padre')
  c = _procesar(_mencion('qué opinas de esto', padre='at://post/padre'),
                padres={'at://post/padre': padre})
  assert 'Insultos y ofensas personales' in c.publicados[0]


def test_ninguna_respuesta_supera_300_caracteres(entorno):
  c = _procesar(_mencion('eres un idiota ' * 100 + ' reportar'))
  assert all(len(t) <= 300 for t in c.publicados)


# ---------------------------------------------------------------------------
# Notificaciones que se deben ignorar
# ---------------------------------------------------------------------------
@pytest.mark.parametrize('notif', [
    pytest.param(_mencion('eres un idiota', leida=True), id='CN-BSK-ya-leida'),
    pytest.param(_mencion('eres un idiota', autor=BOT), id='CN-BSK-del-propio-bot'),
])
def test_notificaciones_ignoradas(entorno, notif):
  assert _procesar(notif).publicados == []


# ---------------------------------------------------------------------------
# Comando "reportar": tabla de decisión
# ---------------------------------------------------------------------------
def test_reportar_acoso_en_simulacion(entorno):
  c = _procesar(_mencion('reportar te voy a matar cuando te vea'))
  assert '[Simulación] Este post se habría reportado' in c.publicados[0]
  assert c.reportes == []


def test_reportar_mensaje_neutro_no_reporta(entorno):
  c = _procesar(_mencion('reportar hola buenos días'))
  assert 'No hay nada que reportar' in c.publicados[0]


def test_reportar_en_modo_real_envia_un_reporte(entorno, monkeypatch):
  monkeypatch.setattr(config, 'BLUESKY_REPORTES_REALES', True)
  c = _procesar(_mencion('reportar te voy a matar cuando te vea'))
  assert 'Reporte enviado a la moderación de Bluesky' in c.publicados[0]
  assert len(c.reportes) == 1


@pytest.mark.parametrize('umbral, se_reporta', [
    pytest.param(0.50, True, id='CN-BSK-umbral-por-debajo-de-la-confianza'),
    pytest.param(0.99, False, id='CN-BSK-umbral-por-encima-de-la-confianza'),
])
def test_umbral_de_reporte(entorno, monkeypatch, umbral, se_reporta):
  monkeypatch.setattr(config, 'BLUESKY_UMBRAL_REPORTE', umbral)
  c = _procesar(_mencion('reportar te voy a matar cuando te vea'))
  assert ('[Simulación]' in c.publicados[0]) is se_reporta


# ---------------------------------------------------------------------------
# Comando "vigilar" / "dejar de vigilar": tabla de decisión
# ---------------------------------------------------------------------------
@pytest.mark.parametrize('texto', ['vigilar', 'vigílame', 'Vigilarme por favor'])
def test_pedir_vigilancia(entorno, texto):
  c = _procesar(_mencion(texto, autor='ana.bsky.social'))
  assert c.publicados[0].startswith('Desde ahora reviso las respuestas')
  assert entorno.list_bluesky_watch() == ['ana.bsky.social']


def test_pedir_vigilancia_dos_veces(entorno):
  c = _procesar(_mencion('vigilar', autor='ana.bsky.social'),
                _mencion('vigilar', autor='ana.bsky.social'))
  # se procesan de la más antigua a la más nueva
  assert any('ya está en vigilancia' in t for t in c.publicados)


@pytest.mark.parametrize('texto', ['dejar de vigilar', 'deja de vigilar', 'no vigilar'])
def test_dejar_de_vigilar(entorno, texto):
  entorno.add_bluesky_watch('ana.bsky.social')
  c = _procesar(_mencion(texto, autor='ana.bsky.social'))
  assert c.publicados[0] == 'Listo, dejé de vigilar las respuestas a tus posts.'
  assert entorno.list_bluesky_watch() == []


def test_dejar_de_vigilar_sin_estar_vigilado(entorno):
  c = _procesar(_mencion('dejar de vigilar', autor='ana.bsky.social'))
  assert c.publicados[0] == 'Tu cuenta no estaba en vigilancia.'


def test_vigilar_en_medio_de_la_frase_no_es_comando(entorno):
  c = _procesar(_mencion('quiero que me puedas vigilar', autor='ana.bsky.social'))
  assert entorno.list_bluesky_watch() == []
  assert 'ciberacoso' in c.publicados[0]  # se analiza como un mensaje normal


def test_cada_persona_solo_puede_vigilar_su_propia_cuenta(entorno):
  _procesar(_mencion('vigilar @otra.bsky.social', autor='ana.bsky.social'))
  assert entorno.list_bluesky_watch() == ['ana.bsky.social']


@pytest.mark.parametrize('cupo, pedidos, ultima_respuesta', [
    pytest.param(2, 1, 'Desde ahora reviso', id='CN-BSK-cupo-debajo-del-limite'),
    pytest.param(2, 2, 'Desde ahora reviso', id='CN-BSK-cupo-en-el-limite'),
    pytest.param(2, 3, 'no hay cupo', id='CN-BSK-cupo-superado'),
])
def test_limite_de_cuentas_vigiladas(entorno, monkeypatch, cupo, pedidos, ultima_respuesta):
  monkeypatch.setattr(config, 'BLUESKY_MAX_VIGILADAS', cupo)
  notifs = [_mencion('vigilar', autor=f'u{i}.bsky.social') for i in range(pedidos)]
  # procesar_notificaciones recorre de la más antigua (última de la lista) a la más nueva
  c = _procesar(*reversed(notifs))
  assert ultima_respuesta in c.publicados[-1]
