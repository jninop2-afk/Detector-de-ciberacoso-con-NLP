"""Modo vigilancia de Bluesky.

El bot revisa por su cuenta, sin que lo mencionen, dos tipos de cuentas:
  - Las de BLUESKY_CUENTAS_VIGILADAS (.env, las decide el dueño del bot):
    respuestas recibidas y posts propios (si ANALIZAR_POSTS_PROPIOS = True).
  - Las que pidieron vigilancia mencionando al bot con "vigilar" (se guardan
    en la base de datos): sólo las respuestas que reciben, nunca sus posts.

La lista se relee en cada ciclo, así que las cuentas nuevas se incorporan sin
reiniciar el proceso.

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
from src import database as db
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


def obtener_posts(client: Client, cuenta: str, propios: bool):
  """Posts propios de la cuenta (si propios=True) y respuestas recibidas."""
  feed = client.get_author_feed(cuenta, limit=POSTS_POR_CUENTA).feed
  for item in feed:
    if propios and item.post.author.handle == cuenta:
      yield item.post
    if not item.post.reply_count:
      continue
    hilo = client.get_post_thread(item.post.uri, depth=1).thread
    if not isinstance(hilo, models.AppBskyFeedDefs.ThreadViewPost):
      continue
    for r in hilo.replies or []:
      if isinstance(r, models.AppBskyFeedDefs.ThreadViewPost):
        yield r.post


def revisar_cuenta(client: Client, cuenta: str, registro: dict, propios: bool) -> None:
  vistos = set(registro['vistos'])
  for post in obtener_posts(client, cuenta, propios):
    if post.uri in vistos or post.author.handle == config.BLUESKY_HANDLE:
      continue
    propio = post.author.handle == cuenta
    if propio and not propios:
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


def cuentas_a_vigilar() -> dict[str, bool]:
  """{cuenta: analizar_posts_propios}. Las del .env tienen prioridad."""
  cuentas = {c: False for c in db.list_bluesky_watch()}
  cuentas.update({c: ANALIZAR_POSTS_PROPIOS for c in config.BLUESKY_CUENTAS_VIGILADAS})
  return cuentas


def main() -> None:
  logging.basicConfig(level=logging.INFO, format='%(asctime)s [%(levelname)s] %(message)s')
  db.init_db()
  client = login()
  if client is None:
    return
  get_detector()
  print(f'Vigilancia activa ({modo_reportes()}, umbral {config.BLUESKY_UMBRAL_REPORTE * 100:.0f}%). '
        f'Fijas: {", ".join(config.BLUESKY_CUENTAS_VIGILADAS) or "ninguna"}; '
        f'solicitadas: {len(db.list_bluesky_watch())}')

  ultimo_total = None
  while True:
    cuentas = cuentas_a_vigilar()
    if len(cuentas) != ultimo_total:
      log.info('Vigilando %d cuenta(s)', len(cuentas))
      ultimo_total = len(cuentas)
    registro = cargar_registro()
    for cuenta, propios in cuentas.items():
      try:
        revisar_cuenta(client, cuenta, registro, propios)
      except Exception as err:
        log.error('Error revisando %s: %s', cuenta, err)
    guardar_registro(registro)
    time.sleep(config.BLUESKY_INTERVALO)


if __name__ == '__main__':
  main()
