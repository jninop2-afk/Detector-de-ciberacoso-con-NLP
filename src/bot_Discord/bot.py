"""Bot de Discord para moderación de ciberacoso.

Ejecutar desde la raíz del proyecto:
    python -m src.bot_Discord.bot
"""

import asyncio
import logging
import os

import discord
from discord.ext import commands

from src import config
from src import database as db
from src.bot_Discord.discord_ui import ReviewButton, build_review_embed, build_review_view
from src.bot_Discord.moderation import apply_infraction, truncate
from src.feedback import retrain_from_feedback
from src.predict import CyberbullyingDetector

logging.basicConfig(level=logging.INFO, format='%(asctime)s [%(levelname)s] %(name)s: %(message)s')
log = logging.getLogger('bot')

BOT_TOKEN = os.getenv('DISCORD_BOT_TOKEN')
ADMIN_MOD_CHANNEL_ID = int(os.getenv('ADMIN_MOD_CHANNEL_ID', '0'))


class ModerationBot(commands.Bot):

  def __init__(self):
    intents = discord.Intents.default()
    intents.message_content = True
    intents.members = True
    super().__init__(command_prefix='!', intents=intents)
    self.detector: CyberbullyingDetector | None = None
    self.retrain_lock = asyncio.Lock()

  async def setup_hook(self):
    db.init_db()
    # Los botones de revisiones pendientes siguen activos tras reiniciar
    self.add_dynamic_items(ReviewButton)
    self.detector = await asyncio.to_thread(self._load_detector)
    log.info('Detector listo. RoBERTa: %s', self.detector.roberta_mode)

  @staticmethod
  def _load_detector(previous: CyberbullyingDetector | None = None):
    detector = CyberbullyingDetector()
    if previous is not None and previous.roberta is not None:
      detector.roberta = previous.roberta  # evita recargar el transformer
    detector.warmup()
    return detector

  @property
  def mod_channel(self) -> discord.TextChannel | None:
    return self.get_channel(ADMIN_MOD_CHANNEL_ID)


bot = ModerationBot()


@bot.event
async def on_ready():
  log.info('Conectado como %s', bot.user)
  if bot.mod_channel is None:
    log.warning('ADMIN_MOD_CHANNEL_ID=%s no corresponde a un canal visible.', ADMIN_MOD_CHANNEL_ID)


async def send_to_review(message: discord.Message, result: dict):
  mod_channel = bot.mod_channel
  if mod_channel is None:
    log.warning('Mensaje dudoso sin canal de moderación configurado: %r', message.content)
    return
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
  if (
      message.content.startswith(bot.command_prefix)
      or message.channel.id == ADMIN_MOD_CHANNEL_ID
  ):
    await bot.process_commands(message)
    return
  if not message.content.strip() or bot.detector is None:
    return

  guild_id, user_id = message.guild.id, message.author.id

  if db.get_user_status(guild_id, user_id)['is_blocked']:
    try:
      await message.delete()
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
      'msg=%r -> %s cat=%s conf=%.2f motor=%s',
      truncate(message.content, 80), action, result['categoria'],
      result['confianza'], result['motor'],
  )

  if action == 'PERMITIR_MENSAJE':
    db.reset_consecutive(guild_id, user_id)
  elif action == 'REVISAR_POR_ADMIN':
    # No se sanciona automáticamente: decide un moderador
    await send_to_review(message, result)
  elif action == 'SANCIONAR':
    try:
      await message.delete()
    except discord.HTTPException:
      log.warning('No se pudo borrar el mensaje (¿falta permiso "Gestionar mensajes"?)')
    await apply_infraction(
        message.author, message.channel, message.content,
        result['categoria'], bot.mod_channel,
    )


# ----------------------------------------------------------------------
# Comandos de administración
# ----------------------------------------------------------------------
@bot.command(name='desbloquear')
@commands.has_permissions(administrator=True)
async def desbloquear(ctx: commands.Context, member: discord.Member):
  db.unblock_user(ctx.guild.id, member.id)
  try:
    await member.timeout(None, reason='Desbloqueo manual por administrador')
  except discord.HTTPException:
    pass
  await ctx.send(f'{member.mention} fue **desbloqueado** y sus alertas se reiniciaron a 0.')


@bot.command(name='estado')
@commands.has_permissions(manage_messages=True)
async def estado(ctx: commands.Context, member: discord.Member):
  s = db.get_user_status(ctx.guild.id, member.id)
  bloqueo = 'no'
  if s['is_blocked']:
    bloqueo = f'hasta {s["blocked_until"]}' if s['blocked_until'] else 'indefinido'
  await ctx.send(
      f'{member.mention}: alertas **{s["alerts_count"]}**, consecutivas'
      f' **{s["consecutive_alerts"]}**, bloqueo: **{bloqueo}**.'
  )


@bot.command(name='analizar')
@commands.has_permissions(manage_messages=True)
async def analizar(ctx: commands.Context, *, texto: str):
  """Prueba el detector sin aplicar sanciones."""
  r = await asyncio.to_thread(bot.detector.predict, texto)
  probs = ' '.join(f'{c}:{p:.2f}' for c, p in r['probabilidades'].items())
  motivos = '; '.join(r['motivos_sospecha']) or 'ninguno'
  await ctx.send(
      f'```\nTexto     : {truncate(texto, 300)}\n'
      f'Limpio    : {truncate(r["texto_limpio"], 300)}\n'
      f'Resultado : {r["categoria_nombre"]} (confianza {r["confianza"]:.2f})\n'
      f'Acción    : {r["accion_sugerida"]}\n'
      f'Motor     : {r["motor"]}\n'
      f'P(acoso)  : clásico={r["prob_clasico"]} roberta={r["prob_roberta"]}\n'
      f'Dist. 0-4 : {probs}\n'
      f'Sospechas : {motivos}\n```'
  )


@bot.command(name='modelo')
@commands.has_permissions(manage_messages=True)
async def modelo(ctx: commands.Context):
  m = bot.detector.metrics
  b, g = m['binario'], m['gravedad']
  per_class = ', '.join(f'{c}: {f:.2f}' for c, f in g['f1_por_clase'].items())
  await ctx.send(
      f'**Modelo clásico** (entrenado {m["entrenado_en"]})\n'
      f'• Binario `{b["modelo"]}`: F1 acoso {b["f1_ciberacoso"]:.3f},'
      f' umbral {b["umbral"]}\n'
      f'• Gravedad `{g["modelo"]}`: F1 macro {g["f1_macro"]:.3f} ({per_class})\n'
      f'• RoBERTa: `{bot.detector.roberta_mode}`\n'
      f'• Feedback acumulado: {db.count_feedback()} mensajes'
  )


@bot.command(name='reentrenar')
@commands.has_permissions(administrator=True)
async def reentrenar(ctx: commands.Context):
  if bot.retrain_lock.locked():
    await ctx.send('Ya hay un reentrenamiento en curso.')
    return
  async with bot.retrain_lock:
    await ctx.send('Reentrenando el modelo clásico con el feedback de los moderadores...')
    try:
      metrics = await asyncio.to_thread(retrain_from_feedback)
      bot.detector = await asyncio.to_thread(bot._load_detector, bot.detector)
      await ctx.send(
          'Reentrenamiento completado. F1 binario:'
          f' {metrics["binario"]["f1_ciberacoso"]:.3f} | F1 macro gravedad:'
          f' {metrics["gravedad"]["f1_macro"]:.3f}'
      )
    except Exception as err:
      log.exception('Error al reentrenar')
      await ctx.send(f'Error al reentrenar el modelo: {err}')


@bot.event
async def on_command_error(ctx: commands.Context, error: commands.CommandError):
  if isinstance(error, commands.MissingPermissions):
    await ctx.send('No tienes permisos para usar este comando.', delete_after=5)
  elif isinstance(error, (commands.MissingRequiredArgument, commands.BadArgument)):
    await ctx.send(f'Uso incorrecto: {error}', delete_after=8)
  elif isinstance(error, commands.CommandNotFound):
    return
  else:
    log.error('Error en comando %s: %s', ctx.command, error)


def main():
  if not BOT_TOKEN:
    raise SystemExit('ERROR: falta DISCORD_BOT_TOKEN en el archivo .env')
  bot.run(BOT_TOKEN, log_handler=None)


if __name__ == '__main__':
  main()
