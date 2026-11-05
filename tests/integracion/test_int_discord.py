"""Integración: bot de Discord + detector real + base de datos + moderación.

Se entrega un mensaje al manejador on_message del bot (como haría Discord) y
se verifica el efecto en TODOS los módulos: si se borró el mensaje, si se
guardó la alerta en SQLite, si se aplicó la sanción y si llegó el reporte al
canal de moderación.
"""

import asyncio
from unittest.mock import AsyncMock, MagicMock

import pytest

GUILD, USUARIO, CANAL, CANAL_MOD = 100, 42, 7, 999


@pytest.fixture
def discord_bot(entorno, detector_real, monkeypatch):
  from src.bot_Discord import bot as modulo
  canal_mod = MagicMock(id=CANAL_MOD)
  canal_mod.send = AsyncMock()
  monkeypatch.setattr(modulo.bot, 'detector', detector_real)
  monkeypatch.setattr(modulo.bot, 'get_channel', lambda cid: canal_mod if cid == CANAL_MOD else None)
  modulo.canal_mod = canal_mod
  return modulo


def _mensaje(texto, canal_id=CANAL, usuario=USUARIO):
  guild = MagicMock(id=GUILD)
  guild.name = 'Servidor de prueba'
  autor = MagicMock(id=usuario, bot=False, guild=guild, mention=f'<@{usuario}>')
  autor.send, autor.timeout = AsyncMock(), AsyncMock()
  canal = MagicMock(id=canal_id, mention=f'<#{canal_id}>')
  canal.send = AsyncMock()
  msg = MagicMock(id=1, content=texto, guild=guild, author=autor, channel=canal,
                  jump_url='https://discord.com/channels/x/y/z')
  msg.delete = AsyncMock()
  return msg


def _enviar(modulo, msg):
  asyncio.run(modulo.on_message(msg))
  return msg


def _activar_servidor(db, avisos_publicos=False):
  db.set_guild_config(GUILD, configured_by=1, mod_channel_id=CANAL_MOD,
                      public_notices=avisos_publicos)


# ---------------------------------------------------------------------------
def test_servidor_sin_configurar_no_modera(discord_bot, entorno):
  msg = _enviar(discord_bot, _mensaje('eres un hijueputa inútil'))
  msg.delete.assert_not_called()
  assert entorno.get_user_status(GUILD, USUARIO)['alerts_count'] == 0


def test_mensaje_ofensivo_se_borra_se_registra_y_se_reporta(discord_bot, entorno):
  _activar_servidor(entorno)
  msg = _enviar(discord_bot, _mensaje('eres un hijueputa inútil'))

  msg.delete.assert_awaited_once()                       # Discord: mensaje borrado
  msg.author.send.assert_awaited_once()                  # MD al infractor
  assert entorno.get_user_status(GUILD, USUARIO)['alerts_count'] == 1   # SQLite
  discord_bot.canal_mod.send.assert_awaited_once()       # reporte a moderadores
  msg.channel.send.assert_not_called()                   # privacidad por defecto


def test_avisos_publicos_activados_publican_en_el_canal(discord_bot, entorno):
  _activar_servidor(entorno, avisos_publicos=True)
  msg = _enviar(discord_bot, _mensaje('eres un hijueputa inútil'))
  msg.channel.send.assert_awaited_once()


def test_mensaje_limpio_no_se_borra_y_rompe_la_racha(discord_bot, entorno):
  _activar_servidor(entorno)
  _enviar(discord_bot, _mensaje('eres un hijueputa inútil'))
  msg = _enviar(discord_bot, _mensaje('buenos días a todos, feliz semana'))
  msg.delete.assert_not_called()
  estado = entorno.get_user_status(GUILD, USUARIO)
  assert (estado['alerts_count'], estado['consecutive_alerts']) == (1, 0)


def test_cuatro_ofensas_seguidas_bloquean_y_luego_se_borra_todo(discord_bot, entorno):
  _activar_servidor(entorno)
  for _ in range(3):
    _enviar(discord_bot, _mensaje('eres un hijueputa inútil'))
  cuarto = _enviar(discord_bot, _mensaje('eres un hijueputa inútil'))
  cuarto.author.timeout.assert_awaited_once()            # silencio en Discord
  assert entorno.get_user_status(GUILD, USUARIO)['is_blocked'] is True

  # Un usuario bloqueado: cualquier mensaje, aunque sea neutro, se borra
  neutro = _enviar(discord_bot, _mensaje('hola, buenos días'))
  neutro.delete.assert_awaited_once()


def test_mensajes_del_canal_de_moderacion_se_ignoran(discord_bot, entorno):
  _activar_servidor(entorno)
  msg = _enviar(discord_bot, _mensaje('eres un hijueputa inútil', canal_id=CANAL_MOD))
  msg.delete.assert_not_called()


def test_caso_dudoso_crea_revision_y_su_resolucion_alimenta_el_reentrenamiento(
    discord_bot, entorno, monkeypatch):
  """Flujo completo: dudoso -> revisión -> moderador decide -> feedback -> dataset."""
  from src import data
  _activar_servidor(entorno)
  entorno.set_guild_trusted(GUILD, True)

  # Se fuerza un resultado dudoso para no depender de qué mensaje duda el modelo
  dudoso = dict(discord_bot.bot.detector.predict('eres un idiota'),
                accion_sugerida='REVISAR_POR_ADMIN')
  monkeypatch.setattr(discord_bot.bot.detector, 'predict', lambda t: dudoso)

  msg = _enviar(discord_bot, _mensaje('texto ambiguo de prueba integración'))
  msg.delete.assert_not_called()                          # no se sanciona solo
  envio = discord_bot.canal_mod.send.await_args.kwargs
  assert envio['embed'].title == 'Revisión requerida: mensaje dudoso'
  assert len(envio['view'].children) == 5                 # un botón por categoría

  with entorno._connect() as conn:
    review_id = conn.execute('SELECT id FROM pending_reviews').fetchone()[0]
  assert entorno.resolve_review(review_id, category=2, reviewed_by=1)

  feedback = data.load_feedback()
  assert 'texto ambiguo de prueba integración' in feedback['texto'].tolist()
  assert feedback.iloc[-1]['categoria'] == 2
