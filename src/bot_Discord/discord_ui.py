import discord
from src.database import save_admin_feedback
from src.feedback import save_admin_correction


class CategorizationView(discord.ui.View):

  def __init__(self, target_user_id: int, message_content: str):
    super().__init__(timeout=None)  # Los botones persisten
    self.target_user_id = target_user_id
    self.message_content = message_content

  async def process_category(
      self, interaction: discord.Interaction, category: int, label: str
  ):
    # Determine binary classification (0 if category 0, 1 otherwise)
    es_acoso = 0 if category == 0 else 1

    # 1. Save in SQLite
    save_admin_feedback(self.target_user_id, self.message_content, category)

    # 2. Save in dataset CSV for re-training
    save_admin_correction(
        texto=self.message_content, es_ciberacoso=es_acoso, categoria=category
    )

    # Deshabilitar botones tras responder
    for child in self.children:
      child.disabled = True

    await interaction.response.edit_message(
        content=(
            f" **Mensaje Categorizado por {interaction.user.mention}**\n"
            f'Texto: "{self.message_content}"\n'
            f"Categoría asignada: **{label}** (Guardado para reentrenamiento)."
        ),
        view=self,
    )

  @discord.ui.button(
      label="0: Seguro", style=discord.ButtonStyle.secondary, custom_id="cat_0"
  )
  async def cat_0_button(
      self, interaction: discord.Interaction, button: discord.ui.Button
  ):
    await self.process_category(interaction, 0, "0 - Seguro")

  @discord.ui.button(
      label="1: Amenaza", style=discord.ButtonStyle.danger, custom_id="cat_1"
  )
  async def cat_1_button(
      self, interaction: discord.Interaction, button: discord.ui.Button
  ):
    await self.process_category(
        interaction, 1, "1 - Hostigamiento/Amenaza Directa"
    )

  @discord.ui.button(
      label="2: Insulto", style=discord.ButtonStyle.primary, custom_id="cat_2"
  )
  async def cat_2_button(
      self, interaction: discord.Interaction, button: discord.ui.Button
  ):
    await self.process_category(interaction, 2, "2 - Insulto/Ofensa Personal")

  @discord.ui.button(
      label="3: Odio/Muerte",
      style=discord.ButtonStyle.danger,
      custom_id="cat_3",
  )
  async def cat_3_button(
      self, interaction: discord.Interaction, button: discord.ui.Button
  ):
    await self.process_category(
        interaction, 3, "3 - Incitación al Odio/Muerte"
    )

  @discord.ui.button(
      label="4: Calumnia", style=discord.ButtonStyle.primary, custom_id="cat_4"
  )
  async def cat_4_button(
      self, interaction: discord.Interaction, button: discord.ui.Button
  ):
    await self.process_category(
        interaction, 4, "4 - Difamación/Calumnia Política"
    )