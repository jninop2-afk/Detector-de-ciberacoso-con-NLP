"""Modo vigilancia de Bluesky.

El bot revisa por su cuenta, sin que lo mencionen, las cuentas indicadas en
BLUESKY_CUENTAS_VIGILADAS y detecta ciberacoso en:
  1) las respuestas que reciben los posts recientes de esas cuentas,
  2) los posts que publican esas cuentas (si ANALIZAR_POSTS_PROPIOS = True).

No responde públicamente (evita parecer spam): registra lo detectado en
data/vigilancia_bluesky.json y lo muestra en la terminal. Si el detector
sugiere SANCIONAR y la confianza supera el umbral, reporta el post (en
simulación por defecto).

    BLUESKY_CUENTAS_VIGILADAS=usuario1.bsky.social,usuario2.bsky.social
    python main.py vigilancia
"""

from datetime import datetime
import json
import logging
import time

from atproto import Client, models

from src import config
from src.bot_bluesky.common import (
    analizar, gestionar_reporte, get_detector, limpiar_menciones, login, modo_reportes,
)

log = logging.getLogger('bluesky')

POSTS_POR_CUENTA = 10        # cuántos posts recientes de cada cuenta revisa
ANALIZAR_POSTS_PROPIOS = True


def cargar_registro() -> dict:
  if config.BLUESKY_VIGILANCIA_JSON.exists():
    return json.loads(config.BLUESKY_VIGILANCIA_JSON.read_text(encoding='utf-8'))
  return {'vistos': [], 'detectados': []}


def guardar_registro(registro: dict) -> None:
  config.BLUESKY_VIGILANCIA_JSON.parent.mkdir(parents=True, exist_ok=True)
  config.BLUESKY_VIGILANCIA_JSON.write_text(
      json.dumps(registro, ensure_ascii=False, indent=4), encoding='utf-8'
  )


def obtener_posts(client: Client, cuenta: str):
  """Posts propios de la cuenta (si está activado) y respuestas recibidas."""
  feed = client.get_author_feed(cuenta, limit=POSTS_POR_CUENTA).feed
  for item in feed:
    if ANALIZAR_POSTS_PROPIOS and item.post.author.handle == cuenta:
      yield item.post
    if not item.post.reply_count:
      continue
    hilo = client.get_post_thread(item.post.uri, depth=1).thread
    if not isinstance(hilo, models.AppBskyFeedDefs.ThreadViewPost):
      continue
    for r in hilo.replies or []:
      if isinstance(r, models.AppBskyFeedDefs.ThreadViewPost):
        yield r.post


def revisar_cuenta(client: Client, cuenta: str, registro: dict) -> None:
  vistos = set(registro['vistos'])
  for post in obtener_posts(client, cuenta):
    if post.uri in vistos or post.author.handle == config.BLUESKY_HANDLE:
      continue
    propio = post.author.handle == cuenta
    if propio and not ANALIZAR_POSTS_PROPIOS:
      continue
    vistos.add(post.uri)
    registro['vistos'].append(post.uri)

    texto = limpiar_menciones(getattr(post.record, 'text', '') or '')
    r = analizar(texto)
    if not r['es_ciberacoso']:
      continue

    accion = gestionar_reporte(client, r, post.uri, post.cid)
    registro['detectados'].append({
        'fecha': datetime.now().isoformat(timespec='seconds'),
        'cuenta_vigilada': cuenta,
        'autor': post.author.handle,
        'tipo': 'publicación propia' if propio else 'respuesta recibida',
        'texto': texto,
        'categoria': r['categoria'],
        'categoria_nombre': r['categoria_nombre'],
        'confianza': r['confianza'],
        'motor': r['motor'],
        'accion_sugerida': r['accion_sugerida'],
        'uri': post.uri,
        'accion': accion,
    })
    destino = '(publicación propia)' if propio else f'-> {cuenta}'
    print(f'[!] {post.author.handle} {destino}: {r["categoria_nombre"]} '
          f'({r["confianza"] * 100:.0f}%, {r["motor"]}) | {accion}')


def main() -> None:
  logging.basicConfig(level=logging.INFO, format='%(asctime)s [%(levelname)s] %(message)s')
  if not config.BLUESKY_CUENTAS_VIGILADAS:
    print('ERROR: define BLUESKY_CUENTAS_VIGILADAS en el .env (ej: usuario.bsky.social)')
    return
  client = login()
  if client is None:
    return
  get_detector()
  print(f'Vigilancia activa sobre {", ".join(config.BLUESKY_CUENTAS_VIGILADAS)} '
        f'({modo_reportes()}, umbral {config.BLUESKY_UMBRAL_REPORTE * 100:.0f}%)')

  while True:
    registro = cargar_registro()
    for cuenta in config.BLUESKY_CUENTAS_VIGILADAS:
      try:
        revisar_cuenta(client, cuenta, registro)
      except Exception as err:
        log.error('Error revisando %s: %s', cuenta, err)
    guardar_registro(registro)
    time.sleep(config.BLUESKY_INTERVALO)


if __name__ == '__main__':
  main()
