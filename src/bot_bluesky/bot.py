"""Bot de Bluesky por menciones.

Alguien responde a un post mencionando al bot (@tu-bot.bsky.social): el bot
analiza el post ORIGINAL y responde con la categoría detectada. Si la mención
no es una respuesta, analiza el texto de la propia mención.

Si la mención incluye la palabra "reportar", el bot además reporta el post a
la moderación de Bluesky (en modo simulación salvo BLUESKY_REPORTES_REALES=1).

Ejecutar desde la raíz del proyecto:
    python main.py bluesky
"""

import logging
import time

from atproto import Client, models

from src import config
from src.bot_bluesky.common import (
    MAX_CARACTERES, analizar, construir_respuesta, gestionar_reporte,
    get_detector, limpiar_menciones, login, modo_reportes,
)

log = logging.getLogger('bluesky')

PALABRA_COMANDO = 'reportar'


def obtener_objetivo(client: Client, notif):
  """Devuelve (texto, uri, cid) del post a analizar."""
  record = notif.record
  if record.reply is not None:
    padre = client.get_posts([record.reply.parent.uri]).posts
    if padre:
      return padre[0].record.text, padre[0].uri, padre[0].cid
  return limpiar_menciones(record.text), notif.uri, notif.cid


def responder(client: Client, notif, texto: str) -> None:
  padre = models.ComAtprotoRepoStrongRef.Main(uri=notif.uri, cid=notif.cid)
  raiz = notif.record.reply.root if notif.record.reply else padre
  client.send_post(
      text=texto[:MAX_CARACTERES],
      reply_to=models.AppBskyFeedPost.ReplyRef(parent=padre, root=raiz),
  )


def procesar_notificaciones(client: Client) -> None:
  respuesta = client.app.bsky.notification.list_notifications()
  # No leídas, sólo menciones y nunca las del propio bot (evita bucles)
  pendientes = [
      n for n in respuesta.notifications
      if not n.is_read and n.reason == 'mention'
      and n.author.handle != config.BLUESKY_HANDLE
  ]

  for notif in reversed(pendientes):  # de la más antigua a la más nueva
    try:
      texto, uri, cid = obtener_objetivo(client, notif)
      r = analizar(texto)
      mensaje = construir_respuesta(r)
      if PALABRA_COMANDO in notif.record.text.lower():
        mensaje = mensaje.split('\n')[0] + '\n' + gestionar_reporte(client, r, uri, cid)
      responder(client, notif, mensaje)
      log.info('Respondí a %s: %s (%s)', notif.author.handle,
               r['categoria_nombre'], r['accion_sugerida'])
    except Exception as err:
      log.error('Error procesando mención de %s: %s', notif.author.handle, err)

  # Marcar todo como visto para no reprocesarlo
  client.app.bsky.notification.update_seen({'seen_at': client.get_current_time_iso()})


def main() -> None:
  logging.basicConfig(level=logging.INFO, format='%(asctime)s [%(levelname)s] %(message)s')
  client = login()
  if client is None:
    return
  get_detector()
  print(f'Bot de Bluesky listo como: {config.BLUESKY_HANDLE} ({modo_reportes()})')
  while True:
    try:
      procesar_notificaciones(client)
    except Exception as err:
      log.error('Error en el ciclo principal: %s', err)
    time.sleep(config.BLUESKY_INTERVALO)


if __name__ == '__main__':
  main()
