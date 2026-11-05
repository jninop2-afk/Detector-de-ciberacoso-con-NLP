"""Caja negra de las reglas de sanción de Discord.

Técnica: transición de estados + valores límite. Especificación (README):
  - alertas 1 a 3: advertencia,
  - alerta 4 o más: silencio de 1 hora,
  - 4 alertas consecutivas (sin mensajes limpios entre ellas): bloqueo indefinido.

Cada caso es una secuencia de eventos:  A = mensaje ofensivo,  L = mensaje limpio.
Sólo se observa la sanción resultante; no se mira cómo se calcula.
"""

import asyncio
from unittest.mock import AsyncMock, MagicMock

import pytest

from src.bot_Discord import moderation


def _ejecutar(secuencia: str, db):
  m = MagicMock()
  m.id, m.guild.id, m.guild.name, m.mention = 42, 1, 'Servidor', '<@42>'
  m.send, m.timeout = AsyncMock(), AsyncMock()
  canal = MagicMock()
  canal.send = AsyncMock()
  sanciones = []
  for evento in secuencia:
    if evento == 'L':
      db.reset_consecutive(1, 42)  # el bot hace esto con cada mensaje limpio
    else:
      _, _, s = asyncio.run(moderation.apply_infraction(m, canal, 'ofensa', 2, None))
      sanciones.append(s)
  return sanciones


@pytest.mark.parametrize('secuencia, ultima_sancion', [
    pytest.param('A', None, id='CN-SAN-001 1 alerta: advertencia'),
    pytest.param('AAA', None, id='CN-SAN-002 3 alertas (límite): advertencia'),
    pytest.param('AAAA', 'indefinido', id='CN-SAN-003 4 seguidas: bloqueo indefinido'),
    pytest.param('AAALA', 'temporal', id='CN-SAN-004 4.ª alerta tras limpio: silencio 1 h'),
    pytest.param('ALALALA', 'temporal', id='CN-SAN-005 4 alertas alternadas: silencio 1 h'),
    pytest.param('AALAAA', 'temporal', id='CN-SAN-006 5 alertas, 3 seguidas: silencio 1 h'),
    pytest.param('AALAAAA', 'indefinido', id='CN-SAN-007 racha de 4 tras limpio: indefinido'),
    pytest.param('LLLLA', None, id='CN-SAN-008 limpios no suman alertas'),
])
def test_transiciones_de_sancion(db_temporal, secuencia, ultima_sancion):
  sanciones = _ejecutar(secuencia, db_temporal)
  assert sanciones[-1] == ultima_sancion


def test_bloqueo_indefinido_queda_registrado(db_temporal):
  _ejecutar('AAAA', db_temporal)
  estado = db_temporal.get_user_status(1, 42)
  assert estado['is_blocked'] is True and estado['blocked_until'] is None


def test_silencio_temporal_tiene_fecha_de_fin(db_temporal):
  _ejecutar('AAALA', db_temporal)
  estado = db_temporal.get_user_status(1, 42)
  assert estado['is_blocked'] is True and estado['blocked_until'] is not None
