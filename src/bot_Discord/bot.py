"""Bot de Discord para moderación de ciberacoso (multi-servidor).

Ejecutar desde la raíz del proyecto:
    python main.py bot

Privacidad:
  - Todos los comandos son slash commands sólo para administradores: Discord
    no se los muestra al resto de miembros y las respuestas son efímeras
    (sólo las ve quien ejecutó el comando).
  - El canal de moderación es privado (sólo administradores y el bot).
  - El bot no analiza nada en un servidor hasta que un admin use /configurar.

Comandos del dueño del bot (/reentrenar, /confiar, /servidores) sólo se
registran en el servidor del dueño (OWNER_GUILD_ID).
"""

import asyncio
import logging
import os

import discord
from discord import app_commands
from discord.ext import commands, tasks

from src import config
from src import database as db
from src.backup import backup_now
from src.bot_Discord.discord_ui import (
    ReviewButton, build_review_embed, build_review_view, is_admin,
)
from src.bot_Discord.moderation import apply_infraction, truncate
from src.feedback import retrain_from_feedback
from src.predict import CyberbullyingDetector

logging.basicConfig(level=logging.INFO, format='%(asctime)s [%(levelname)s] %(name)s: %(message)s')
log = logging.getLogger('bot')

# DISCORD_TOKEN se acepta por compatibilidad con el .env del proyecto anterior
BOT_TOKEN = os.getenv('DISCORD_BOT_TOKEN') or os.getenv('DISCORD_TOKEN')
# Canal de moderación del servidor original (se migra a la config por servidor)
ADMIN_MOD_CHANNEL_ID = int(os.getenv('ADMIN_MOD_CHANNEL_ID', '0'))

PRIVATE_CHANNEL_NAME = 'moderacion-ciberacoso'
INVITE_PERMISSIONS = discord.Permissions(
    view_channel=True, send_messages=True, embed_links=True,
    read_message_history=True, manage_messages=True, manage_channels=True,
    manage_roles=True, moderate_members=True,
)
REQUIRED_PERMISSIONS = {
    'manage_messages': 'Gestionar mensajes',
    'moderate_members': 'Moderar miembros',
    'manage_channels': 'Gestionar canales',
    'manage_roles': 'Gestionar roles',
}


class ModerationBot(commands.Bot):

  def __init__(self):
    intents = discord.Intents.default()
    intents.message_content = True
    intents.members = True
    # Sin comandos de prefijo: todo se gestiona con slash commands
    super().__init__(command_prefix=commands.when_mentioned, intents=intents, help_command=None)
    self.detector: CyberbullyingDetector | None = None
    self.retrain_lock = asyncio.Lock()
    self.owner_guild_id = config.OWNER_GUILD_ID

  async def setup_hook(self):
    db.init_db()
    # Los botones de revisiones pendientes siguen activos tras reiniciar
    self.add_dynamic_items(ReviewButton)
    await self._setup_owner_guild()

    owner_guild = discord.Object(self.owner_guild_id) if self.owner_guild_id else None
    for cmd in OWNER_COMMANDS:
      self.tree.add_command(cmd, guild=owner_guild)
    await self.tree.sync()
    if owner_guild:
      await self.tree.sync(guild=owner_guild)
    else:
      log.warning('Sin OWNER_GUILD_ID: los comandos del dueño son visibles para '
                  'los admins de todos los servidores (aunque sólo tú puedes usarlos).')

    self.detector = await asyncio.to_thread(self._load_detector)
    log.info('Detector listo. RoBERTa: %s', self.detector.roberta_mode)
    self.daily_backup.start()

  async def _setup_owner_guild(self):
    """Deduce el servidor del dueño y migra el canal del .env antiguo."""
    if ADMIN_MOD_CHANNEL_ID:
      try:
        channel = await self.fetch_channel(ADMIN_MOD_CHANNEL_ID)
        if not self.owner_guild_id:
          self.owner_guild_id = channel.guild.id
        cfg = db.get_guild_config(channel.guild.id)
        if not cfg or not cfg['mod_channel_id']:
          db.set_guild_config(channel.guild.id, 0, mod_channel_id=channel.id)
          log.info('Canal de moderación del .env migrado a la config del servidor.')
      except discord.HTTPException as err:
        log.warning('No se pudo leer ADMIN_MOD_CHANNEL_ID=%s: %s', ADMIN_MOD_CHANNEL_ID, err)
    if self.owner_guild_id:
      db.set_guild_trusted(self.owner_guild_id, True)

  @staticmethod
  def _load_detector(previous: CyberbullyingDetector | None = None):
    detector = CyberbullyingDetector()
    if previous is not None and previous.roberta is not None:
      detector.roberta = previous.roberta  # evita recargar el transformer
    detector.warmup()
    return detector

  def mod_channel_for(self, guild_id: int) -> discord.TextChannel | None:
    cfg = db.get_guild_config(guild_id)
    if not cfg or not cfg['mod_channel_id']:
      return None
    return self.get_channel(cfg['mod_channel_id'])

  @tasks.loop(hours=24)
  async def daily_backup(self):
    try:
      await asyncio.to_thread(backup_now)
    except Exception:
      log.exception('Falló la copia de seguridad automática')


bot = ModerationBot()


# ----------------------------------------------------------------------
# Eventos
# ----------------------------------------------------------------------
@bot.event
async def on_ready():
  log.info('Conectado como %s en %d servidor(es)', bot.user, len(bot.guilds))
  url = discord.utils.oauth_url(
      bot.user.id, permissions=INVITE_PERMISSIONS, scopes=('bot', 'applications.commands')
  )
  log.info('Enlace de invitación: %s', url)


@bot.event
async def on_guild_join(guild: discord.Guild):
  """Explica al dueño del servidor cómo activar el bot (por MD, no en público)."""
  log.info('Añadido al servidor %s (%s)', guild.name, guild.id)
  try:
    owner = guild.owner or await guild.fetch_member(guild.owner_id)
    await owner.send(
        f'¡Gracias por añadir el bot de moderación a **{guild.name}**!\n'
        'Por ahora **no analiza ningún mensaje**. Para activarlo, un administrador '
        'debe usar `/configurar` en el servidor: se creará un canal privado, visible '
        'sólo para administradores, donde llegarán las alertas.'
    )
  except discord.HTTPException:
    pass


async def send_to_review(message: discord.Message, result: dict, mod_channel: discord.TextChannel):
  review_id = db.create_review(
      message.guild.id, message.channel.id, message.id, message.author.id,
      message.content, result['categoria'], result['confianza'], result['motor'],
  )
  await mod_channel.send(
      embed=build_review_embed(message, result), view=build_review_view(review_id)
  )


@bot.event
async def on_message(message: discord.Message):
  if message.author.bot or message.guild is None:
    return
  cfg = db.get_guild_config(message.guild.id)
  # Servidor sin activar o mensaje del propio canal de moderación
  if not cfg or not cfg['mod_channel_id'] or message.channel.id == cfg['mod_channel_id']:
    return
  if not message.content.strip() or bot.detector is None:
    return

  guild_id, user_id = message.guild.id, message.author.id
  mod_channel = bot.get_channel(cfg['mod_channel_id'])

  if db.get_user_status(guild_id, user_id)['is_blocked']:
    try:
      await message.delete()
      if cfg['public_notices']:
        await message.channel.send(
            f'{message.author.mention}, tu cuenta está bloqueada por infracciones de ciberacoso.',
            delete_after=5,
        )
    except discord.HTTPException:
      pass
    return

  # La inferencia (sobre todo RoBERTa) corre fuera del event loop
  result = await asyncio.to_thread(bot.detector.predict, message.content)
  action = result['accion_sugerida']
  log.info(
      '[%s] msg=%r -> %s cat=%s conf=%.2f motor=%s', message.guild.name,
      truncate(message.content, 80), action, result['categoria'],
      result['confianza'], result['motor'],
  )

  if action == 'PERMITIR_MENSAJE':
    db.reset_consecutive(guild_id, user_id)
  elif action == 'REVISAR_POR_ADMIN':
    # No se sanciona automáticamente: decide un administrador
    if mod_channel is not None:
      await send_to_review(message, result, mod_channel)
    else:
      log.warning('[%s] El canal de moderación ya no existe; usa /configurar.', message.guild.name)
  elif action == 'SANCIONAR':
    try:
      await message.delete()
    except discord.HTTPException:
      log.warning('No se pudo borrar el mensaje (¿falta permiso "Gestionar mensajes"?)')
    await apply_infraction(
        message.author, message.channel, message.content, result['categoria'],
        mod_channel, public_notices=cfg['public_notices'],
    )


# ----------------------------------------------------------------------
# Verificaciones de permisos
# ----------------------------------------------------------------------
def admin_only():
  # default_permissions oculta el comando a no-admins; esta verificación
  # cubre el caso de que el servidor cambie esa configuración
  async def predicate(interaction: discord.Interaction) -> bool:
    if is_admin(interaction):
      return True
    raise app_commands.CheckFailure('Sólo los administradores pueden usar este comando.')
  return app_commands.check(predicate)


def owner_only():
  async def predicate(interaction: discord.Interaction) -> bool:
    if await interaction.client.is_owner(interaction.user):
      return True
    raise app_commands.CheckFailure('Sólo el dueño del bot puede usar este comando.')
  return app_commands.check(predicate)


@bot.tree.error
async def on_app_command_error(interaction: discord.Interaction, error: app_commands.AppCommandError):
  if isinstance(error, app_commands.CheckFailure):
    msg = str(error)
  else:
    log.error('Error en /%s: %s', interaction.command.name if interaction.command else '?', error)
    msg = f'Ocurrió un error: {error}'
  if interaction.response.is_done():
    await interaction.followup.send(msg, ephemeral=True)
  else:
    await interaction.response.send_message(msg, ephemeral=True)


# ----------------------------------------------------------------------
# Comandos de administradores (cada servidor)
# ----------------------------------------------------------------------
def _others_with_access(channel: discord.TextChannel) -> list[str]:
  """Roles/miembros no administradores con permiso explícito para ver el canal."""
  guild = channel.guild
  others = []
  for target, overwrite in channel.overwrites.items():
    if target in (guild.default_role, guild.me) or not overwrite.view_channel:
      continue
    perms = target.permissions if isinstance(target, discord.Role) else target.guild_permissions
    if not perms.administrator:
      others.append(target.mention)
  return others


class ConfigError(Exception):
  """Error de /configurar con un mensaje listo para mostrar al admin."""


def _forbidden_detail(err: discord.Forbidden) -> str:
  return f'Discord respondió: {err.text or "Forbidden"} (código {err.code}).'


def _check_channel_usable(channel: discord.TextChannel):
  """Comprueba, antes de tocar nada, que el bot puede convertir el canal en privado."""
  guild = channel.guild
  special = {guild.system_channel, guild.rules_channel, guild.public_updates_channel} - {None}
  if channel in special:
    raise ConfigError(
        f'{channel.mention} es un canal principal del servidor (bienvenidas, reglas o '
        'avisos) y no lo voy a ocultar a los miembros. Ejecuta `/configurar` sin `canal` '
        'para que cree uno privado, o elige otro canal.'
    )
  perms = channel.permissions_for(guild.me)
  if not perms.view_channel:
    raise ConfigError(
        f'No puedo ver {channel.mention}. Agrégame a ese canal (Editar canal → Permisos) '
        'o ejecuta `/configurar` sin `canal` para que cree uno privado.'
    )
  if not perms.manage_roles:
    raise ConfigError(
        f'No puedo editar los permisos de {channel.mention}: el canal o su categoría me '
        'quitan **Gestionar permisos**. Dámelo en ese canal o ejecuta `/configurar` sin `canal`.'
    )


async def _make_private(channel: discord.TextChannel):
  """Oculta el canal a @everyone sin que el bot pierda el acceso.

  El orden importa: si primero se oculta a @everyone, el bot (que suele ver el
  canal gracias a @everyone) deja de verlo y ya no puede darse acceso.
  """
  guild = channel.guild
  _check_channel_usable(channel)
  previous_everyone = channel.overwrites_for(guild.default_role)
  previous_me = channel.overwrites.get(guild.me)
  try:
    await channel.set_permissions(
        guild.me, view_channel=True, send_messages=True, embed_links=True,
        read_message_history=True, reason='Canal privado de moderación del bot',
    )
    await channel.set_permissions(
        guild.default_role, view_channel=False, reason='Canal privado de moderación del bot',
    )
  except discord.Forbidden as err:
    # Deshace lo que alcanzó a cambiar para no dejar el canal a medias
    try:
      await channel.set_permissions(guild.default_role, overwrite=previous_everyone)
      await channel.set_permissions(guild.me, overwrite=previous_me)
    except discord.HTTPException:
      log.warning('No se pudieron restaurar los permisos de #%s', channel)
    raise ConfigError(
        f'No pude cambiar los permisos de {channel.mention}. {_forbidden_detail(err)}'
    ) from err


async def _create_private_channel(guild: discord.Guild) -> discord.TextChannel:
  missing = [name for perm, name in (('manage_channels', 'Gestionar canales'),
                                     ('manage_roles', 'Gestionar roles'))
             if not getattr(guild.me.guild_permissions, perm)]
  if missing:
    raise ConfigError(
        f'Para crear el canal privado me falta: **{", ".join(missing)}**. '
        'Actívalo en Ajustes del servidor → Roles → mi rol, o vuelve a invitarme con el enlace.'
    )
  overwrites = {
      guild.default_role: discord.PermissionOverwrite(view_channel=False),
      guild.me: discord.PermissionOverwrite(
          view_channel=True, send_messages=True, embed_links=True, read_message_history=True,
      ),
  }
  return await guild.create_text_channel(
      PRIVATE_CHANNEL_NAME, overwrites=overwrites,
      topic='Alertas del bot de ciberacoso. Visible sólo para administradores.',
      reason='Canal privado de moderación del bot',
  )


@bot.tree.command(name='configurar', description='Activa el bot y define el canal privado de moderación')
@app_commands.describe(
    canal='Canal existente para las alertas (se volverá privado). Si no se indica, se crea uno.',
    avisos_publicos='Publicar avisos de sanción en el canal donde ocurrió (por defecto: no).',
)
@app_commands.guild_only()
@app_commands.default_permissions(administrator=True)
@admin_only()
async def configurar(
    interaction: discord.Interaction,
    canal: discord.TextChannel | None = None,
    avisos_publicos: bool | None = None,
):
  await interaction.response.defer(ephemeral=True, thinking=True)
  guild = interaction.guild
  cfg = db.get_guild_config(guild.id)
  current = guild.get_channel(cfg['mod_channel_id']) if cfg and cfg['mod_channel_id'] else None

  was_public = canal is not None and canal.permissions_for(guild.default_role).view_channel
  try:
    if canal is not None:
      await _make_private(canal)
      channel = canal
    elif current is None:
      channel = await _create_private_channel(guild)
    else:
      channel = current
  except ConfigError as err:
    await interaction.followup.send(str(err), ephemeral=True)
    return
  except discord.Forbidden as err:
    log.warning('/configurar en %s (%s): %s', guild.name, guild.id, err)
    await interaction.followup.send(
        f'No pude crear el canal privado. {_forbidden_detail(err)}', ephemeral=True,
    )
    return

  db.set_guild_config(guild.id, interaction.user.id, mod_channel_id=channel.id,
                      public_notices=avisos_publicos)
  cfg = db.get_guild_config(guild.id)

  lines = [
      '**Bot de moderación activo en este servidor.**',
      f'• Canal privado de moderación: {channel.mention}',
      *(['• Ese canal era público: ahora solo lo ven los administradores.'] if was_public else []),
      f'• Avisos públicos de sanción: **{"sí" if cfg["public_notices"] else "no"}**'
      ' (el infractor siempre recibe un MD)',
  ]
  others = _others_with_access(channel)
  if others:
    lines.append(f'• Atención: también pueden ver el canal {", ".join(others)}')
  missing = [name for perm, name in REQUIRED_PERMISSIONS.items()
             if not getattr(guild.me.guild_permissions, perm)]
  if missing:
    lines.append(f'• Me faltan permisos: **{", ".join(missing)}**')
  lines.append('• Recuerda: mi rol debe estar por encima de los usuarios que deba silenciar.')
  await interaction.followup.send('\n'.join(lines), ephemeral=True)


@bot.tree.command(name='analizar', description='Prueba el detector con un texto (no sanciona)')
@app_commands.describe(texto='Texto a analizar')
@app_commands.guild_only()
@app_commands.default_permissions(administrator=True)
@admin_only()
async def analizar(interaction: discord.Interaction, texto: str):
  await interaction.response.defer(ephemeral=True, thinking=True)
  r = await asyncio.to_thread(bot.detector.predict, texto)
  probs = ' '.join(f'{c}:{p:.2f}' for c, p in r['probabilidades'].items())
  motivos = '; '.join(r['motivos_sospecha']) or 'ninguno'
  await interaction.followup.send(
      f'```\nTexto     : {truncate(texto, 300)}\n'
      f'Limpio    : {truncate(r["texto_limpio"], 300)}\n'
      f'Resultado : {r["categoria_nombre"]} (confianza {r["confianza"]:.2f})\n'
      f'Acción    : {r["accion_sugerida"]}\n'
      f'Motor     : {r["motor"]}\n'
      f'P(acoso)  : clásico={r["prob_clasico"]} roberta={r["prob_roberta"]}\n'
      f'Dist. 0-4 : {probs}\n'
      f'Sospechas : {motivos}\n```',
      ephemeral=True,
  )


@bot.tree.command(name='estado', description='Alertas y bloqueo de un usuario')
@app_commands.describe(usuario='Miembro a consultar')
@app_commands.guild_only()
@app_commands.default_permissions(administrator=True)
@admin_only()
async def estado(interaction: discord.Interaction, usuario: discord.Member):
  s = db.get_user_status(interaction.guild.id, usuario.id)
  bloqueo = 'no'
  if s['is_blocked']:
    bloqueo = f'hasta {s["blocked_until"]}' if s['blocked_until'] else 'indefinido'
  await interaction.response.send_message(
      f'{usuario.mention}: alertas **{s["alerts_count"]}**, consecutivas'
      f' **{s["consecutive_alerts"]}**, bloqueo: **{bloqueo}**.',
      ephemeral=True,
  )


@bot.tree.command(name='desbloquear', description='Quita el bloqueo y reinicia las alertas de un usuario')
@app_commands.describe(usuario='Miembro a desbloquear')
@app_commands.guild_only()
@app_commands.default_permissions(administrator=True)
@admin_only()
async def desbloquear(interaction: discord.Interaction, usuario: discord.Member):
  db.unblock_user(interaction.guild.id, usuario.id)
  try:
    await usuario.timeout(None, reason=f'Desbloqueo manual por {interaction.user}')
  except discord.HTTPException:
    pass
  await interaction.response.send_message(
      f'{usuario.mention} fue **desbloqueado** y sus alertas se reiniciaron a 0.',
      ephemeral=True,
  )


@bot.tree.command(name='modelo', description='Métricas del modelo de detección')
@app_commands.guild_only()
@app_commands.default_permissions(administrator=True)
@admin_only()
async def modelo(interaction: discord.Interaction):
  m = bot.detector.metrics
  b, g = m['binario'], m['gravedad']
  per_class = ', '.join(f'{c}: {f:.2f}' for c, f in g['f1_por_clase'].items())
  await interaction.response.send_message(
      f'**Modelo clásico** (entrenado {m["entrenado_en"]})\n'
      f'• Binario `{b["modelo"]}`: F1 acoso {b["f1_ciberacoso"]:.3f}, umbral {b["umbral"]}\n'
      f'• Gravedad `{g["modelo"]}`: F1 macro {g["f1_macro"]:.3f} ({per_class})\n'
      f'• RoBERTa: `{bot.detector.roberta_mode}`\n'
      f'• Correcciones de este servidor: {db.count_feedback(interaction.guild.id)}',
      ephemeral=True,
  )


# ----------------------------------------------------------------------
# Comandos del dueño del bot (sólo en OWNER_GUILD_ID)
# ----------------------------------------------------------------------
@app_commands.command(name='reentrenar', description='[Dueño] Reentrena el modelo con el feedback de confianza')
@app_commands.default_permissions(administrator=True)
@owner_only()
async def reentrenar(interaction: discord.Interaction):
  if bot.retrain_lock.locked():
    await interaction.response.send_message('Ya hay un reentrenamiento en curso.', ephemeral=True)
    return
  await interaction.response.defer(ephemeral=True, thinking=True)
  async with bot.retrain_lock:
    try:
      await asyncio.to_thread(backup_now)  # copia antes de cambiar el modelo
      metrics = await asyncio.to_thread(retrain_from_feedback)
      bot.detector = await asyncio.to_thread(bot._load_detector, bot.detector)
      await interaction.followup.send(
          'Reentrenamiento completado. F1 binario:'
          f' {metrics["binario"]["f1_ciberacoso"]:.3f} | F1 macro gravedad:'
          f' {metrics["gravedad"]["f1_macro"]:.3f}',
          ephemeral=True,
      )
    except Exception as err:
      log.exception('Error al reentrenar')
      await interaction.followup.send(f'Error al reentrenar el modelo: {err}', ephemeral=True)


@app_commands.command(name='servidores', description='[Dueño] Servidores, configuración y feedback')
@app_commands.default_permissions(administrator=True)
@owner_only()
async def servidores(interaction: discord.Interaction):
  counts = {row['guild_id']: row for row in db.feedback_by_guild()}
  lines = []
  for guild in bot.guilds:
    cfg = db.get_guild_config(guild.id) or {}
    fb = counts.get(guild.id, {}).get('total', 0)
    lines.append(
        f'• **{guild.name}** `{guild.id}` — '
        f'{"activo" if cfg.get("mod_channel_id") else "sin configurar"}, '
        f'feedback {fb}, confianza: {"sí" if cfg.get("feedback_trusted") else "no"}'
    )
  legacy = counts.get(None, {}).get('total', 0)
  if legacy:
    lines.append(f'• Feedback anterior sin servidor (siempre se usa): {legacy}')
  await interaction.response.send_message(
      truncate('\n'.join(lines) or 'El bot no está en ningún servidor.', 1900), ephemeral=True
  )


@app_commands.command(name='confiar', description='[Dueño] Usar o no el feedback de un servidor al reentrenar')
@app_commands.describe(servidor_id='ID del servidor (ver /servidores)', confiar='¿Usar su feedback?')
@app_commands.default_permissions(administrator=True)
@owner_only()
async def confiar(interaction: discord.Interaction, servidor_id: str, confiar: bool):
  if not servidor_id.isdigit():
    await interaction.response.send_message('El ID debe ser numérico.', ephemeral=True)
    return
  db.set_guild_trusted(int(servidor_id), confiar)
  await interaction.response.send_message(
      f'Feedback del servidor `{servidor_id}`: **{"se usará" if confiar else "no se usará"}**'
      ' en el próximo /reentrenar.',
      ephemeral=True,
  )


OWNER_COMMANDS = [reentrenar, servidores, confiar]


def main():
  if not BOT_TOKEN:
    raise SystemExit('ERROR: falta DISCORD_BOT_TOKEN en el archivo .env')
  bot.run(BOT_TOKEN, log_handler=None)


if __name__ == '__main__':
  main()
