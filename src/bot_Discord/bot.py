from datetime import timedelta
import os
import discord
from discord.ext import commands
from dotenv import load_dotenv

# Cargar las variables de entorno del archivo .env
load_dotenv()

# Obtener variables de entorno
BOT_TOKEN = os.getenv('DISCORD_BOT_TOKEN')
ADMIN_MOD_CHANNEL_ID = int(os.getenv('ADMIN_MOD_CHANNEL_ID', 0))

if not BOT_TOKEN:
  raise ValueError(' ERROR: No se encontró DISCORD_BOT_TOKEN en el archivo .env')

# Importaciones locales del proyecto
from src.bot_Discord.discord_ui import CategorizationView
from src.database import (
    get_user_data,
    init_db,
    register_user_alert,
    set_user_blocked,
    unblock_user_db,
)
from src.feedback import retrain_from_feedback
from src.predict import CyberbullyingDetector

# Configuración de Intenciones de Discord
intents = discord.Intents.default()
intents.message_content = True
intents.members = True

bot = commands.Bot(command_prefix='!', intents=intents)

# Inicializar Base de Datos y Detector NLP
init_db()
detector = CyberbullyingDetector(confidence_threshold=0.70)


@bot.event
async def on_ready():
  print(f' Bot de Moderación conectado como: {bot.user.name}')


@bot.event
async def on_message(message: discord.Message):
  # 1. Ignorar mensajes de bots, comandos y mensajes del canal de moderación
  if (
      message.author.bot
      or message.content.startswith('!')
      or message.channel.id == ADMIN_MOD_CHANNEL_ID
  ):
    await bot.process_commands(message)
    return

  user_id = message.author.id
  guild_id = message.guild.id if message.guild else 0
  user_info = get_user_data(user_id)

  # Si el usuario ya está bloqueado, se elimina el mensaje
  if user_info['is_blocked']:
    try:
      await message.delete()
      await message.channel.send(
          f' {message.author.mention}, tu cuenta se encuentra bloqueada por'
          ' violaciones de ciberacoso.',
          delete_after=5,
      )
    except Exception:
      pass
    return

  # 2. Análisis NLP
  result = detector.predict(message.content)

  # 3. Notificación de baja confianza al Administrador
  if result['notificar_admin']:
    mod_channel = bot.get_channel(ADMIN_MOD_CHANNEL_ID)
    if mod_channel:
      embed = discord.Embed(
          title='⚠️ Alerta: Mensaje de Baja Confianza Detectado',
          color=discord.Color.gold(),
      )
      embed.add_field(
          name='Usuario',
          value=f'{message.author.mention} (`{user_id}`)',
          inline=False,
      )
      embed.add_field(
          name='Contenido Original',
          value=f'"{result["texto_original"]}"',
          inline=False,
      )
      embed.add_field(
          name='Confianza Calculada',
          value=f'{result["confianza"]*100:.1f}%',
          inline=True,
      )
      embed.set_footer(
          text=(
              'Por favor, selecciona una categoría para registrar y reentrenar'
              ' el modelo.'
          )
      )

      view = CategorizationView(
          target_user_id=user_id, message_content=result['texto_original']
      )
      await mod_channel.send(embed=embed, view=view)

  # 4. Caso: Ciberacoso Detectado
  if result['es_ciberacoso']:
    # Borrar el mensaje del canal público
    try:
      await message.delete()
    except Exception:
      pass

    # Registrar alerta en SQLite
    total_alerts, consecutive_alerts = register_user_alert(user_id, guild_id)
    mod_channel = bot.get_channel(ADMIN_MOD_CHANNEL_ID)
    cat_id = result.get('categoria_gravedad', 0)

    
    # NOTIFICACIÓN POR MENSAJE DIRECTO (DM) AL USUARIO
    
    try:
      embed_dm = discord.Embed(
          title=' Advertencia de Moderación: Ciberacoso Detectado',
          description=(
              f'Tu mensaje en el servidor **{message.guild.name}** ha sido'
              ' eliminado automáticamente porque vulnera nuestras políticas de'
              ' convivencia.'
          ),
          color=discord.Color.red(),
      )
      embed_dm.add_field(
          name='Contenido Eliminado',
          value=f'"{result["texto_original"]}"',
          inline=False,
      )
      embed_dm.add_field(
          name='Categoría de Gravedad', value=f'Nivel {cat_id}', inline=True
      )
      embed_dm.add_field(
          name='Estado de Alertas',
          value=f'{total_alerts}/3 acumuladas',
          inline=True,
      )

      if total_alerts >= 4:
        embed_dm.add_field(
            name='Sanción Aplicada',
            value=(
                '**Has sido silenciado temporalmente.** Evita continuar con este'
                ' comportamiento para prevenir suspensiones permanentes.'
            ),
            inline=False,
        )
      else:
        embed_dm.add_field(
            name='Aviso',
            value=(
                'Recuerda que acumular más de 3 alertas resultará en un'
                ' bloqueo temporal o definitivo.'
            ),
            inline=False,
        )

      embed_dm.set_footer(
          text='Sistema Automatizado de Detección de Ciberacoso NLP'
      )

      await message.author.send(embed=embed_dm)
    except discord.Forbidden:
      print(
          f'[Aviso] No se pudo enviar mensaje directo a {message.author.name}'
          ' (MD bloqueados).'
      )
    except Exception as err:
      print(f'[Error MD] {err}')

    
    # RESPUESTAS PÚBLICAS Y SANCIONES SEGÚN REGLAS
    

    # REGLA 1: Primeras 3 alertas
    if total_alerts <= 3:
      await message.channel.send(
          f' **ALERTA ({total_alerts}/3)** {message.author.mention}: Tu'
          ' mensaje fue detectado como posible ciberacoso, ha sido borrado y'
          ' se te ha enviado una advertencia por mensaje privado.',
          delete_after=10,
      )

    # REGLA 2: Límite superado (4ª alerta) -> Timeout 1 hora
    elif total_alerts == 4 and consecutive_alerts < 4:
      set_user_blocked(user_id, duration_hours=1)
      try:
        await message.author.timeout(
            timedelta(hours=1), reason='Acumulación de 4 alertas de ciberacoso'
        )
      except Exception:
        pass

      await message.channel.send(
          f' {message.author.mention} ha superado el límite de 3 alertas.'
          ' Ha sido **bloqueado por 1 hora**.'
      )

      if mod_channel:
        await mod_channel.send(
            f' **REPORTE DE GRAVEDAD**: {message.author.mention} ha superado'
            ' las 3 alertas. Se le aplicó un **bloqueo temporal de 1 hora**.'
        )

    # REGLA 3: 4ª alerta consecutiva -> Bloqueo Indefinido
    elif consecutive_alerts >= 4:
      set_user_blocked(user_id, duration_hours=None)
      try:
        await message.author.timeout(
            timedelta(days=28),
            reason='4 infracciones consecutivas de ciberacoso',
        )
      except Exception:
        pass

      await message.channel.send(
          f' {message.author.mention} ha generado una **4ta alerta'
          ' consecutiva**. Su cuenta ha sido **bloqueada de forma'
          ' indefinida**.'
      )

      if mod_channel:
        await mod_channel.send(
            f' **ALERTA CRÍTICA**: {message.author.mention} alcanzó 4'
            ' infracciones consecutivas. **Usuario bloqueado indefinidamente'
            ' requiere revisión y desbloqueo manual del admin** con el comando'
            f' `!desbloquear {user_id}`.'
        )

  await bot.process_commands(message)


@bot.command(name='desbloquear')
@commands.has_permissions(administrator=True)
async def desbloquear(ctx, member: discord.Member):
  unblock_user_db(member.id)
  try:
    await member.timeout(None, reason='Desbloqueo manual por Administrador')
  except Exception:
    pass

  await ctx.send(
      f' El usuario {member.mention} ha sido **desbloqueado** y sus alertas'
      ' han sido reiniciadas a 0.'
  )


@bot.command(name='reentrenar')
@commands.has_permissions(administrator=True)
async def reentrenar_modelo(ctx):
  await ctx.send(
      ' Iniciando reentrenamiento del modelo con la retroalimentación de los'
      ' administradores...'
  )
  try:
    retrain_from_feedback()
    global detector
    detector = CyberbullyingDetector(confidence_threshold=0.70)
    await ctx.send(
        '🏆 ¡Reentrenamiento completado! El bot ahora utiliza el modelo'
        ' actualizado.'
    )
  except Exception as e:
    await ctx.send(f' Error al reentrenar el modelo: {e}')


if __name__ == '__main__':
  bot.run(BOT_TOKEN)