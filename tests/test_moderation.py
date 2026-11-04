"""Pruebas de las reglas de sanción del bot de Discord (src/bot_Discord/moderation.py).

Discord se sustituye por dobles (AsyncMock): no se conecta a ningún servidor.
"""

import asyncio
from datetime import timedelta
from unittest.mock import AsyncMock, MagicMock

import pytest

from src.bot_Discord import moderation


def _miembro(guild_id=1, user_id=42):
  m = MagicMock()
  m.id = user_id
  m.guild.id = guild_id
  m.guild.name = 'Servidor de prueba'
  m.mention = f'<@{user_id}>'
  m.send = AsyncMock()
  m.timeout = AsyncMock()
  return m


def _infraccion(miembro, canal, mod=None, avisos_publicos=False):
  return asyncio.run(
      moderation.apply_infraction(
          miembro, canal, 'texto ofensivo', 2, mod, public_notices=avisos_publicos,
      )
  )


@pytest.fixture
def canal():
  c = MagicMock()
  c.send = AsyncMock()
  return c


def test_primeras_tres_alertas_solo_advierten(db_temporal, canal):
  m = _miembro()
  for esperado in (1, 2, 3):
    total, _, sancion = _infraccion(m, canal)
    assert total == esperado and sancion is None
  m.timeout.assert_not_called()
  assert m.send.await_count == 3  # un MD por alerta


def test_cuarta_alerta_consecutiva_bloquea_indefinidamente(db_temporal, canal):
  m = _miembro()
  for _ in range(3):
    _infraccion(m, canal)
  _, consecutivas, sancion = _infraccion(m, canal)
  assert consecutivas == 4 and sancion == 'indefinido'
  m.timeout.assert_awaited_once()
  assert m.timeout.await_args.args[0] == moderation.MAX_TIMEOUT
  assert db_temporal.get_user_status(1, 42)['is_blocked'] is True


def test_cuarta_alerta_no_consecutiva_silencia_una_hora(db_temporal, canal):
  m = _miembro()
  for _ in range(3):
    _infraccion(m, canal)
  db_temporal.reset_consecutive(1, 42)  # hubo un mensaje limpio
  total, consecutivas, sancion = _infraccion(m, canal)
  assert (total, consecutivas, sancion) == (4, 1, 'temporal')
  assert m.timeout.await_args.args[0] == timedelta(hours=moderation.TEMP_BLOCK_HOURS)


def _canal_mod():
  mod = MagicMock()
  mod.send = AsyncMock()
  return mod


def test_cada_infraccion_se_reporta_en_canal_de_moderacion(db_temporal, canal):
  mod = _canal_mod()
  m = _miembro()
  for _ in range(4):
    _infraccion(m, canal, mod)
  assert mod.send.await_count == 4  # una por infracción, no sólo las sanciones
  embed = mod.send.await_args.kwargs['embed']
  assert embed.title == 'Infracción registrada'


def test_por_privacidad_no_publica_avisos_en_el_canal(db_temporal, canal):
  m = _miembro()
  for _ in range(4):
    _infraccion(m, canal)
  canal.send.assert_not_called()


def test_con_avisos_publicos_activados_publica_en_el_canal(db_temporal, canal):
  m = _miembro()
  _infraccion(m, canal, avisos_publicos=True)
  canal.send.assert_awaited_once()
  assert 'ALERTA (1/3)' in canal.send.await_args.args[0]


def test_md_cerrados_no_interrumpen_la_sancion(db_temporal, canal):
  import discord
  mod = _canal_mod()
  m = _miembro()
  m.send.side_effect = discord.Forbidden(MagicMock(status=403), 'MD cerrados')
  total, _, _ = _infraccion(m, canal, mod)
  assert total == 1
  mod.send.assert_awaited_once()  # el reporte a moderadores igual se envía


@pytest.mark.parametrize('texto, limite, esperado', [
    ('corto', 10, 'corto'),
    ('a' * 20, 10, 'aaaaaaa...'),
])
def test_truncate(texto, limite, esperado):
  assert moderation.truncate(texto, limite) == esperado
