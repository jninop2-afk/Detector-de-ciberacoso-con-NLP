"""
Modo vigilancia: el bot revisa SOLO, sin que lo mencionen, las respuestas que
reciben los posts recientes de las cuentas que tú indiques, y detecta ciberacoso.

- NO responde públicamente (evita parecer spam). Registra lo detectado en
  data/vigilancia_bluesky.json y lo muestra en la terminal.
- Si la confianza supera el umbral, reporta (en simulación por defecto).

Configura en el .env las cuentas a vigilar (separadas por coma, sin arroba):
    BLUESKY_CUENTAS_VIGILADAS=juandavid-ya31.bsky.social

Ejecutar desde la raíz del proyecto:
    python -m app.botBluesky.vigilancia
"""
import json
import os
import sys
import time
from datetime import datetime

from atproto import Client, models

sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '..', '..')))
from app.botBluesky.bot_bluesky import (
    HANDLE, APP_PASSWORD, REPORTES_REALES, UMBRAL_REPORTE,
    es_ciberacoso, gestionar_reporte, limpiar_menciones,
)
from app.services.predictor import predecir_ciberacoso

CUENTAS = [c.strip().lstrip("@") for c in os.getenv("BLUESKY_CUENTAS_VIGILADAS", "").split(",") if c.strip()]
INTERVALO_SEGUNDOS = 60     # cada cuánto revisa las cuentas
POSTS_POR_CUENTA = 10       # cuántos posts recientes de cada cuenta revisa
ARCHIVO = os.path.join("data", "vigilancia_bluesky.json")


def cargar_registro() -> dict:
    if os.path.exists(ARCHIVO):
        with open(ARCHIVO, "r", encoding="utf-8") as f:
            return json.load(f)
    return {"vistos": [], "detectados": []}


def guardar_registro(registro: dict) -> None:
    os.makedirs(os.path.dirname(ARCHIVO), exist_ok=True)
    with open(ARCHIVO, "w", encoding="utf-8") as f:
        json.dump(registro, f, ensure_ascii=False, indent=4)


def obtener_respuestas(client: Client, cuenta: str):
    """Devuelve las respuestas (PostView) recibidas en los posts recientes de la cuenta."""
    feed = client.get_author_feed(cuenta, limit=POSTS_POR_CUENTA).feed
    for item in feed:
        if not item.post.reply_count:
            continue
        hilo = client.get_post_thread(item.post.uri, depth=1).thread
        if not isinstance(hilo, models.AppBskyFeedDefs.ThreadViewPost):
            continue
        for r in hilo.replies or []:
            if isinstance(r, models.AppBskyFeedDefs.ThreadViewPost):
                yield r.post


def revisar_cuenta(client: Client, cuenta: str, registro: dict) -> None:
    vistos = set(registro["vistos"])
    for post in obtener_respuestas(client, cuenta):
        if post.uri in vistos or post.author.handle in (cuenta, HANDLE):
            continue
        vistos.add(post.uri)
        registro["vistos"].append(post.uri)

        texto = limpiar_menciones(getattr(post.record, "text", "") or "")
        resultado = predecir_ciberacoso(texto)
        if not es_ciberacoso(resultado):
            continue

        accion = gestionar_reporte(client, resultado, post.uri, post.cid).strip()
        registro["detectados"].append({
            "fecha": datetime.now().isoformat(timespec="seconds"),
            "cuenta_vigilada": cuenta,
            "autor": post.author.handle,
            "texto": texto,
            "categoria": resultado["categoria_detectada"],
            "probabilidad": resultado["probabilidad"],
            "uri": post.uri,
            "accion": accion,
        })
        print(f"[!] {post.author.handle} -> {cuenta}: {resultado['categoria_detectada']} "
              f"({resultado['probabilidad'] * 100:.0f}%) | {accion}")


def iniciar_vigilancia() -> None:
    if not HANDLE or not APP_PASSWORD:
        print("ERROR: faltan BLUESKY_HANDLE y/o BLUESKY_APP_PASSWORD en el archivo .env")
        return
    if not CUENTAS:
        print("ERROR: define BLUESKY_CUENTAS_VIGILADAS en el .env (ej: usuario.bsky.social)")
        return

    client = Client()
    client.login(HANDLE, APP_PASSWORD)
    modo = "REPORTES REALES" if REPORTES_REALES else "simulación de reportes"
    print(f"Vigilancia activa sobre {', '.join(CUENTAS)} ({modo}, umbral {UMBRAL_REPORTE * 100:.0f}%)")

    while True:
        registro = cargar_registro()
        for cuenta in CUENTAS:
            try:
                revisar_cuenta(client, cuenta, registro)
            except Exception as e:
                print(f"Error revisando {cuenta}: {e}")
        guardar_registro(registro)
        time.sleep(INTERVALO_SEGUNDOS)


if __name__ == "__main__":
    iniciar_vigilancia()
