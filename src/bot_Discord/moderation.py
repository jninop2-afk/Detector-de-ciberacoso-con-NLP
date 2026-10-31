"""Reglas de sanción del bot.

  - Alertas 1 a 3: advertencia por mensaje directo.
  - Alerta 4 o más: silencio temporal de 1 hora.
  - 4 alertas consecutivas (sin mensajes limpios entre ellas): bloqueo
    indefinido hasta que un admin use /desbloquear.

Privacidad: por defecto nada se publica en los canales del servidor. El
infractor recibe un MD y los administradores un reporte en el canal privado
de moderación. Los avisos públicos se activan con /configurar.
"""

from datetime import timedelta
import logging

import discord

from src import config
from src import database as db

log = logging.getLogger(__name__)

MAX_WARNINGS = 3
CONSECUTIVE_LIMIT = 4
TEMP_BLOCK_HOURS = 1
# Discord no permite timeouts de más de 28 días
MAX_TIMEOUT = timedelta(days=28)


def truncate(text: str, limit: int = 1000) -> str:
  return text if len(text) <= limit else text[: limit - 3] + '...'


async def _send_dm(member, guild, text, category, total, sanction):
  embed = discord.Embed(
      title='Advertencia de moderación: ciberacoso detectado',
      description=(
          f'Tu mensaje en **{guild.name}** fue eliminado porque vulnera las'
          ' normas de convivencia.'
      ),
      color=discord.Color.red(),
  )
  embed.add_field(name='Contenido eliminado', value=f'"{truncate(text)}"', inline=False)
  embed.add_field(name='Categoría', value=config.CATEGORIES[category], inline=True)
  embed.add_field(name='Alertas', value=f'{total}/{MAX_WARNINGS}', inline=True)
  if sanction == 'indefinido':
    note = '**Tu cuenta fue bloqueada de forma indefinida.** Un administrador revisará tu caso.'
  elif sanction == 'temporal':
    note = f'**Has sido silenciado por {TEMP_BLOCK_HOURS} hora(s).**'
  else:
    note = f'Superar {MAX_WARNINGS} alertas conlleva un bloqueo temporal o definitivo.'
  embed.add_field(name='Sanción', value=note, inline=False)
  embed.set_footer(text='Sistema automatizado de detección de ciberacoso (NLP + RoBERTa)')
  try:
    await member.send(embed=embed)
  except discord.Forbidden:
    log.info('No se pudo enviar MD a %s (MD cerrados).', member)
  except discord.HTTPException as err:
    log.warning('Error enviando MD a %s: %s', member, err)


async def _public_notice(channel, member, total, sanction):
  if sanction is None:
    text = (
        f'**ALERTA ({total}/{MAX_WARNINGS})** {member.mention}: tu mensaje fue'
        ' detectado como posible ciberacoso y fue eliminado.'
    )
    await channel.send(text, delete_after=10)
  elif sanction == 'temporal':
    await channel.send(
        f'{member.mention} superó el límite de {MAX_WARNINGS} alertas y fue'
        f' **silenciado por {TEMP_BLOCK_HOURS} hora(s)**.'
    )
  else:
    await channel.send(
        f'{member.mention} acumuló **{CONSECUTIVE_LIMIT} alertas consecutivas**'
        ' y fue **bloqueado de forma indefinida**.'
    )


async def _report(mod_channel, member, channel, text, category, total, consecutive, sanction, source):
  colors = {None: discord.Color.orange(), 'temporal': discord.Color.red(),
            'indefinido': discord.Color.dark_red()}
  embed = discord.Embed(title='Infracción registrada', color=colors[sanction])
  embed.add_field(name='Usuario', value=f'{member.mention} (`{member.id}`)', inline=False)
  where = getattr(channel, 'mention', 'desconocido')
  embed.add_field(name='Canal', value=where, inline=True)
  embed.add_field(name='Categoría', value=config.CATEGORIES[category], inline=True)
  embed.add_field(name='Origen', value=source, inline=True)
  embed.add_field(name='Mensaje eliminado', value=f'"{truncate(text)}"', inline=False)
  embed.add_field(
      name='Alertas',
      value=f'{total} totales, {consecutive} consecutivas',
      inline=True,
  )
  embed.add_field(
      name='Sanción',
      value={None: 'Advertencia', 'temporal': f'Silencio {TEMP_BLOCK_HOURS} h',
             'indefinido': 'Bloqueo indefinido'}[sanction],
      inline=True,
  )
  if sanction:
    embed.set_footer(text=f'Para revertir: /desbloquear usuario:{member}')
  try:
    await mod_channel.send(embed=embed)
  except discord.HTTPException as err:
    log.warning('No se pudo enviar el reporte de moderación: %s', err)


async def apply_infraction(
    member: discord.Member,
    channel: discord.abc.Messageable,
    text: str,
    category: int,
    mod_channel: discord.TextChannel | None,
    public_notices: bool = False,
    source: str = 'automático',
):
  """Registra la alerta y aplica la sanción correspondiente."""
  guild = member.guild
  total, consecutive = db.register_user_alert(guild.id, member.id)

  sanction = None
  if consecutive >= CONSECUTIVE_LIMIT:
    sanction = 'indefinido'
    db.set_user_blocked(guild.id, member.id, duration_hours=None)
    timeout, reason = MAX_TIMEOUT, f'{CONSECUTIVE_LIMIT} infracciones consecutivas de ciberacoso'
  elif total > MAX_WARNINGS:
    sanction = 'temporal'
    db.set_user_blocked(guild.id, member.id, duration_hours=TEMP_BLOCK_HOURS)
    timeout, reason = timedelta(hours=TEMP_BLOCK_HOURS), f'{total} alertas de ciberacoso'

  if sanction:
    try:
      await member.timeout(timeout, reason=reason)
    except discord.Forbidden:
      log.warning('Sin permiso "Moderar miembros" para silenciar a %s.', member)
    except discord.HTTPException as err:
      log.warning('No se pudo silenciar a %s: %s', member, err)

  await _send_dm(member, guild, text, category, total, sanction)

  if public_notices and channel is not None:
    try:
      await _public_notice(channel, member, total, sanction)
    except discord.HTTPException as err:
      log.warning('No se pudo publicar el aviso: %s', err)

  if mod_channel is not None:
    await _report(mod_channel, member, channel, text, category, total, consecutive, sanction, source)
  return total, consecutive, sanction
