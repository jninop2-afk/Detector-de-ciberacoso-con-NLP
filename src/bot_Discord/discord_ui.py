"""Componentes de interfaz: revisión de mensajes dudosos por administradores.

Los botones son DynamicItem: su custom_id incluye el id de la revisión
guardada en SQLite, así siguen funcionando aunque el bot se reinicie.
"""

import discord

from src import config
from src import database as db
from src.bot_Discord.moderation import apply_infraction, truncate

BUTTON_STYLES = {
    0: discord.ButtonStyle.success,
    1: discord.ButtonStyle.danger,
    2: discord.ButtonStyle.primary,
    3: discord.ButtonStyle.danger,
    4: discord.ButtonStyle.primary,
}


class ReviewButton(
    discord.ui.DynamicItem[discord.ui.Button],
    template=r'review:(?P<review_id>[0-9]+):(?P<category>[0-4])',
):

  def __init__(self, review_id: int, category: int):
    super().__init__(
        discord.ui.Button(
            label=f'{category}: {config.CATEGORY_SHORT[category]}',
            style=BUTTON_STYLES[category],
            custom_id=f'review:{review_id}:{category}',
        )
    )
    self.review_id = review_id
    self.category = category

  @classmethod
  async def from_custom_id(cls, interaction, item, match):
    return cls(int(match['review_id']), int(match['category']))

  async def interaction_check(self, interaction: discord.Interaction) -> bool:
    perms = getattr(interaction.user, 'guild_permissions', None)
    if perms is None or not perms.manage_messages:
      await interaction.response.send_message(
          'Sólo moderadores pueden clasificar mensajes.', ephemeral=True
      )
      return False
    return True

  async def callback(self, interaction: discord.Interaction):
    review = db.get_review(self.review_id)
    if review is None:
      await interaction.response.send_message('La revisión no existe.', ephemeral=True)
      return
    if not db.resolve_review(self.review_id, self.category, interaction.user.id):
      await interaction.response.send_message(
          'Otro moderador ya clasificó este mensaje.', ephemeral=True
      )
      return

    embed = interaction.message.embeds[0] if interaction.message.embeds else discord.Embed()
    embed.color = discord.Color.green() if self.category == 0 else discord.Color.red()
    embed.add_field(
        name='Resolución',
        value=(
            f'{interaction.user.mention} → **{config.CATEGORIES[self.category]}**'
            ' (guardado para reentrenamiento)'
        ),
        inline=False,
    )
    await interaction.response.edit_message(embed=embed, view=None)

    if self.category == 0:
      return

    # Confirmado como ciberacoso: borrar el mensaje original y sancionar
    guild = interaction.guild
    channel = guild.get_channel(review['channel_id'])
    if channel is not None:
      try:
        original = await channel.fetch_message(review['message_id'])
        await original.delete()
      except (discord.NotFound, discord.Forbidden):
        pass

    member = guild.get_member(review['user_id'])
    if member is None:
      try:
        member = await guild.fetch_member(review['user_id'])
      except discord.NotFound:
        await interaction.followup.send('El usuario ya no está en el servidor.', ephemeral=True)
        return

    _, _, sanction = await apply_infraction(
        member, channel or interaction.channel, review['message_text'],
        self.category, interaction.channel,
    )
    await interaction.followup.send(
        f'Alerta registrada a {member.mention}'
        + (f' (sanción: {sanction}).' if sanction else '.'),
        ephemeral=True,
    )


def build_review_view(review_id: int) -> discord.ui.View:
  view = discord.ui.View(timeout=None)
  for category in range(5):
    view.add_item(ReviewButton(review_id, category))
  return view


def build_review_embed(message: discord.Message, result: dict) -> discord.Embed:
  embed = discord.Embed(
      title='Revisión requerida: mensaje dudoso',
      description=f'[Ir al mensaje]({message.jump_url}) en {message.channel.mention}',
      color=discord.Color.gold(),
  )
  embed.add_field(
      name='Usuario', value=f'{message.author.mention} (`{message.author.id}`)', inline=False
  )
  embed.add_field(name='Contenido', value=f'"{truncate(message.content)}"', inline=False)
  embed.add_field(
      name='Predicción',
      value=f'{config.CATEGORIES[result["categoria"]]} ({result["confianza"] * 100:.1f}%)',
      inline=True,
  )
  embed.add_field(name='Motor', value=result['motor'], inline=True)
  probs = []
  if result['prob_clasico'] is not None:
    probs.append(f'clásico {result["prob_clasico"]:.2f}')
  if result['prob_roberta'] is not None:
    probs.append(f'RoBERTa {result["prob_roberta"]:.2f}')
  if probs:
    embed.add_field(name='P(ciberacoso)', value=' | '.join(probs), inline=True)
  if result['motivos_sospecha']:
    embed.add_field(
        name='Motivos de sospecha',
        value=truncate('\n'.join(f'• {r}' for r in result['motivos_sospecha'])),
        inline=False,
    )
  embed.set_footer(text='Selecciona la categoría correcta. Se usará para reentrenar el modelo.')
  return embed
