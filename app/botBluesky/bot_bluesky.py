"""
Bot de Bluesky para el detector de ciberacoso.

Uso: alguien responde a un post mencionando al bot (@tu-bot.bsky.social).
El bot analiza el post ORIGINAL y responde con la categoría detectada.
Si la mención no es una respuesta, analiza el texto de la propia mención.

Comando extra: si la mención incluye la palabra "reportar" y la confianza
supera el umbral, el bot reporta el post a la moderación de Bluesky.
Por defecto funciona en MODO SIMULACIÓN (no envía reportes reales).
Para activar reportes reales, agrega BLUESKY_REPORTES_REALES=1 al .env.

Ejecutar SIEMPRE desde la raíz del proyecto (el predictor usa rutas relativas):
    python -m app.botBluesky.bot_bluesky
"""
import os
import re
import sys
import time

from atproto import Client, models
from dotenv import load_dotenv

# Conectar la ruta base del proyecto (igual que en bot_Discord.py)
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '..', '..')))
from app.services.predictor import predecir_ciberacoso

load_dotenv()
HANDLE = os.getenv("BLUESKY_HANDLE")            # ej: nlpguardbot.bsky.social
APP_PASSWORD = os.getenv("BLUESKY_APP_PASSWORD")  # App Password, NO la contraseña real
REPORTES_REALES = os.getenv("BLUESKY_REPORTES_REALES") == "1"

INTERVALO_SEGUNDOS = 15     # cada cuánto revisa notificaciones
MAX_CARACTERES = 300        # límite de un post en Bluesky
UMBRAL_REPORTE = 0.60       # confianza mínima para reportar un post
PALABRA_COMANDO = "reportar"


def limpiar_menciones(texto: str) -> str:
    """Quita los @handles para analizar solo el contenido."""
    return re.sub(r"@\S+", "", texto).strip()


def obtener_objetivo(client: Client, notif):
    """Devuelve (texto, uri, cid) del post a analizar.
    Si la mención es una respuesta, es el post padre; si no, la propia mención."""
    record = notif.record
    if record.reply is not None:
        padre = client.get_posts([record.reply.parent.uri]).posts
        if padre:
            return padre[0].record.text, padre[0].uri, padre[0].cid
    return limpiar_menciones(record.text), notif.uri, notif.cid


def es_ciberacoso(resultado: dict) -> bool:
    categoria = resultado["categoria_detectada"]
    return "Sin ciberacoso" not in categoria and "Sin contenido" not in categoria


def construir_respuesta(resultado: dict) -> str:
    categoria = resultado["categoria_detectada"]
    prob = resultado["probabilidad"] * 100

    if not es_ciberacoso(resultado):
        texto = f"No detecté ciberacoso en ese mensaje ({prob:.0f}% de confianza)."
    else:
        texto = (
            f"Posible ciberacoso detectado: {categoria} ({prob:.0f}% de confianza).\n"
            "Es un análisis automático y puede equivocarse."
        )
    return texto[:MAX_CARACTERES]


def reportar_post(client: Client, uri: str, cid: str, resultado: dict) -> None:
    """Envía un reporte de moderación a Bluesky sobre el post indicado."""
    prob = resultado["probabilidad"] * 100
    client.com.atproto.moderation.create_report(
        models.ComAtprotoModerationCreateReport.Data(
            reason_type=models.ComAtprotoModerationDefs.ReasonRude,
            reason=(
                f"Detección automática (proyecto universitario): "
                f"{resultado['categoria_detectada']} ({prob:.0f}% de confianza)"
            ),
            subject=models.ComAtprotoRepoStrongRef.Main(uri=uri, cid=cid),
        )
    )


def gestionar_reporte(client: Client, resultado: dict, uri: str, cid: str) -> str:
    """Decide si se reporta y devuelve la línea extra para la respuesta."""
    if not es_ciberacoso(resultado):
        return "\nNo hay nada que reportar."
    if resultado["probabilidad"] < UMBRAL_REPORTE:
        return f"\nNo lo reporté: la confianza es menor a {UMBRAL_REPORTE * 100:.0f}%."
    if not REPORTES_REALES:
        return "\n[Simulación] Este post se habría reportado a la moderación."
    reportar_post(client, uri, cid, resultado)
    return "\nReporte enviado a la moderación de Bluesky."


def responder(client: Client, notif, texto: str) -> None:
    padre = models.ComAtprotoRepoStrongRef.Main(uri=notif.uri, cid=notif.cid)
    raiz = notif.record.reply.root if notif.record.reply else padre
    client.send_post(
        text=texto[:MAX_CARACTERES],
        reply_to=models.AppBskyFeedPost.ReplyRef(parent=padre, root=raiz),
    )


def procesar_notificaciones(client: Client) -> None:
    respuesta = client.app.bsky.notification.list_notifications()
    # No leídas, solo menciones, y nunca las del propio bot (evita bucles)
    pendientes = [
        n for n in respuesta.notifications
        if not n.is_read and n.reason == "mention" and n.author.handle != HANDLE
    ]

    for notif in reversed(pendientes):  # de la más antigua a la más nueva
        try:
            texto, uri, cid = obtener_objetivo(client, notif)
            resultado = predecir_ciberacoso(texto)
            mensaje = construir_respuesta(resultado)

            if PALABRA_COMANDO in notif.record.text.lower():
                mensaje = mensaje.split("\n")[0] + gestionar_reporte(client, resultado, uri, cid)

            responder(client, notif, mensaje)
            print(f"Respondí a {notif.author.handle}: {resultado['categoria_detectada']}")
        except Exception as e:
            print(f"Error procesando mención de {notif.author.handle}: {e}")

    # Marcar todo como visto para no reprocesarlo
    client.app.bsky.notification.update_seen({"seen_at": client.get_current_time_iso()})


def iniciar_bot() -> None:
    if not HANDLE or not APP_PASSWORD:
        print("ERROR: faltan BLUESKY_HANDLE y/o BLUESKY_APP_PASSWORD en el archivo .env")
        return

    client = Client()
    client.login(HANDLE, APP_PASSWORD)
    modo = "REPORTES REALES" if REPORTES_REALES else "modo simulación de reportes"
    print(f"Bot de Bluesky listo como: {HANDLE} ({modo})")

    while True:
        try:
            procesar_notificaciones(client)
        except Exception as e:
            print(f"Error en el ciclo principal: {e}")
        time.sleep(INTERVALO_SEGUNDOS)


if __name__ == "__main__":
    iniciar_bot()
