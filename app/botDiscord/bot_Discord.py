import json
import os
import sys
import discord
from discord.ext import commands
from dotenv import load_dotenv


# Conectar la ruta base del proyecto
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))
from app.services.predictor import predecir_ciberacoso


#Llamando el token
load_dotenv()
TOKEN = os.getenv("DISCORD_TOKEN")
DATA_FILE = os.path.join("data", "moderacion_usuarios.json") #Base de datos del usuario

# Gestor de sanciones
#Carga el historial del usuario
def cargar_historial():
    if os.path.exists(DATA_FILE):
        with open(DATA_FILE, "r", encoding="utf-8") as f:
            return json.load(f)
    return {}


#Guarda el historial del usuario
def guardar_historial(datos):
    os.makedirs(os.path.dirname(DATA_FILE), exist_ok=True)
    with open(DATA_FILE, "w", encoding="utf-8") as f:
        json.dump(datos, f, ensure_ascii=False, indent=4)

# Configuración de permisos
intents = discord.Intents.default()
intents.message_content = True
intents.members = True 

bot = commands.Bot(command_prefix="!", intents=intents)

@bot.event
async def on_ready():
    print(f" Bot de moderación avanzado listo como: {bot.user.name}")

@bot.event
async def on_message(message):
    if message.author.bot or not message.guild:
        return

    texto = message.content.strip()

    if texto and not texto.startswith("!"):
        try:
            resultado = predecir_ciberacoso(texto)
            categoria = resultado['categoria_detectada']
            
            if "Sin ciberacoso" not in categoria:
                user_id = str(message.author.id)
                historial = cargar_historial()

                if user_id not in historial:
                    historial[user_id] = {"advertencias": 0, "baneos": 0}

                historial[user_id]["advertencias"] += 1
                adv_actuales = historial[user_id]["advertencias"]
                baneos_actuales = historial[user_id]["baneos"]

                # 1. Eliminar mensaje ofensivo
                try:
                    await message.delete()
                except discord.Forbidden:
                    print("No tengo permisos para borrar mensajes.")

                # 2. Enviar advertencia privada (DM)
                try:
                    await message.author.send(
                        f"!! **ADVERTENCIA DE MODERACIÓN** !!\n"
                        f"Tu mensaje en **{message.guild.name}** fue detectado como: **{categoria}**.\n"
                        f"Llevas **{adv_actuales}/5** advertencias."
                        f"A la quinta advertencia, recibe una suspención temporal."
                        f"A la tercera suspención quedá baneado del servidor"
                    )
                except discord.HTTPException:
                    pass

                # 3. Publicar alerta en el canal
                embed = discord.Embed(
                    title="!! **Infracción de Ciberacoso Detectada** !!",
                    color=discord.Color.red()
                )
                embed.add_field(name="Usuario", value=message.author.mention, inline=True)
                embed.add_field(name="Categoría", value=categoria, inline=True)
                embed.add_field(name="Advertencias", value=f"{adv_actuales}/5", inline=True)
                embed.set_footer(text="El mensaje fue eliminado automáticamente.")
                await message.channel.send(embed=embed)

                # 4. Evaluación de Baneo (5 advertencias)
                if adv_actuales >= 5:
                    historial[user_id]["advertencias"] = 0
                    historial[user_id]["baneos"] += 1
                    baneos_actuales = historial[user_id]["baneos"]

                    # Evaluación de Expulsión Definitiva (3 baneos)
                    if baneos_actuales >= 3:
                        guardar_historial(historial)
                        await message.guild.kick(
                            message.author, 
                            reason="Acumulación de 3 baneos por reincidencia en ciberacoso."
                        )
                        await message.channel.send(
                            f" El usuario {message.author.mention} ha sido **EXPULSADO** del servidor por acumular 3 baneos."
                        )
                    else:
                        guardar_historial(historial)
                        await message.guild.ban(
                            message.author, 
                            reason=f"Acumulación de 5 advertencias de ciberacoso. Baneo #{baneos_actuales}."
                        )
                        await message.channel.send(
                            f"🔨 El usuario {message.author.mention} ha sido **BANEADO** (Baneo {baneos_actuales}/3)."
                        )
                else:
                    guardar_historial(historial)

        except Exception as e:
            print(f"Error procesando infracción: {e}")

    await bot.process_commands(message)

def iniciar_bot():
    if not TOKEN:
        print("ERROR: No se encontró DISCORD_TOKEN en el archivo .env")
        return
    bot.run(TOKEN)



if __name__ == "__main__":
    iniciar_bot()

