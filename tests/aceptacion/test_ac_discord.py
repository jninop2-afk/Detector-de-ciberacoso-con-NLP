"""Pasos de features/moderacion_discord.feature."""

import asyncio
from unittest.mock import AsyncMock, MagicMock

import pytest
from pytest_bdd import given, parsers, scenarios, then, when

from src import config

scenarios('features/moderacion_discord.feature')

GUILD, USUARIO, CANAL, CANAL_MOD = 100, 42, 7, 999
OFENSA = 'eres un hijueputa inútil'


class Servidor:
  """Servidor de Discord simulado alrededor del bot real."""

  def __init__(self, modulo, db):
    self.modulo, self.db = modulo, db
    self.canal_mod = MagicMock(id=CANAL_MOD)
    self.canal_mod.send = AsyncMock()
    self.mensajes = []

  def escribir(self, texto):
    guild = MagicMock(id=GUILD)
    guild.name = 'Servidor de aceptación'
    autor = MagicMock(id=USUARIO, bot=False, guild=guild, mention=f'<@{USUARIO}>')
    autor.send, autor.timeout = AsyncMock(), AsyncMock()
    canal = MagicMock(id=CANAL, mention=f'<#{CANAL}>')
    canal.send = AsyncMock()
    msg = MagicMock(id=len(self.mensajes) + 1, content=texto, guild=guild, author=autor,
                    channel=canal, jump_url='https://discord.com/channels/x/y/z')
    msg.delete = AsyncMock()
    asyncio.run(self.modulo.on_message(msg))
    self.mensajes.append(msg)
    return msg

  @property
  def ultimo(self):
    return self.mensajes[-1]


# ---------------------------------------------------------------------------
# Dado
# ---------------------------------------------------------------------------
@given('un servidor de Discord con el bot configurado y un canal privado de moderación',
       target_fixture='servidor')
def servidor_configurado(entorno, detector_real, monkeypatch):
  from src.bot_Discord import bot as modulo
  srv = Servidor(modulo, entorno)
  monkeypatch.setattr(modulo.bot, 'detector', detector_real)
  monkeypatch.setattr(modulo.bot, 'get_channel',
                      lambda cid: srv.canal_mod if cid == CANAL_MOD else None)
  entorno.set_guild_config(GUILD, configured_by=1, mod_channel_id=CANAL_MOD)
  entorno.set_guild_trusted(GUILD, True)
  return srv


# ---------------------------------------------------------------------------
# Cuando
# ---------------------------------------------------------------------------
@when(parsers.parse('un usuario escribe "{texto}"'))
def usuario_escribe(servidor, texto):
  servidor.escribir(texto)


@when(parsers.parse('un usuario escribe {n:d} mensajes ofensivos seguidos'))
def usuario_reincide(servidor, n):
  for _ in range(n):
    servidor.escribir(OFENSA)


@when('un usuario escribe un mensaje que el detector considera dudoso')
def mensaje_dudoso(servidor, monkeypatch):
  detector = servidor.modulo.bot.detector
  dudoso = dict(detector.predict('eres un idiota'), accion_sugerida='REVISAR_POR_ADMIN')
  monkeypatch.setattr(detector, 'predict', lambda t: dudoso)
  servidor.escribir('mensaje ambiguo para revisión humana')


@when(parsers.parse('un moderador lo clasifica como "{categoria}"'))
def moderador_clasifica(servidor, categoria):
  numero = next(k for k, v in config.CATEGORIES.items() if v == categoria)
  with servidor.db._connect() as conn:
    review_id = conn.execute('SELECT id FROM pending_reviews ORDER BY id DESC').fetchone()[0]
  assert servidor.db.resolve_review(review_id, numero, reviewed_by=1)
  servidor.categoria_elegida = numero


# ---------------------------------------------------------------------------
# Entonces
# ---------------------------------------------------------------------------
@then('el mensaje se elimina')
def mensaje_eliminado(servidor):
  servidor.ultimo.delete.assert_awaited_once()


@then('el mensaje no se elimina')
def mensaje_no_eliminado(servidor):
  servidor.ultimo.delete.assert_not_called()


@then('el usuario recibe una advertencia por mensaje privado')
def advertencia_privada(servidor):
  servidor.ultimo.author.send.assert_awaited_once()


@then('los moderadores reciben el reporte en el canal privado')
def reporte_privado(servidor):
  servidor.canal_mod.send.assert_awaited_once()


@then('los moderadores no reciben ningún reporte')
def sin_reporte(servidor):
  servidor.canal_mod.send.assert_not_called()


@then('no se publica ningún aviso en el canal público')
def sin_aviso_publico(servidor):
  servidor.ultimo.channel.send.assert_not_called()


@then('el usuario queda silenciado en Discord')
def usuario_silenciado(servidor):
  servidor.ultimo.author.timeout.assert_awaited_once()
  assert servidor.db.get_user_status(GUILD, USUARIO)['is_blocked'] is True


@then('sus siguientes mensajes se eliminan aunque sean normales')
def bloqueado_se_borra_todo(servidor):
  servidor.escribir('hola, buenos días')
  servidor.ultimo.delete.assert_awaited_once()


@then('los moderadores reciben una solicitud de revisión con un botón por categoría')
def solicitud_revision(servidor):
  envio = servidor.canal_mod.send.await_args.kwargs
  assert 'Revisión requerida' in envio['embed'].title
  assert len(envio['view'].children) == len(config.CATEGORIES)


@then('su decisión queda guardada para reentrenar el modelo')
def decision_guardada(servidor):
  from src import data
  feedback = data.load_feedback()
  fila = feedback[feedback['texto'] == 'mensaje ambiguo para revisión humana']
  assert fila['categoria'].tolist() == [servidor.categoria_elegida]
