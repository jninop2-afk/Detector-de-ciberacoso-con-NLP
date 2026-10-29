"""Diagnóstico: muestra las últimas notificaciones de la cuenta del bot.

Útil para comprobar que las menciones llegan y si ya están marcadas como
leídas (el bot sólo procesa las no leídas).

    python main.py bluesky-diag
"""

from src.bot_bluesky.common import login


def main(n: int = 8) -> None:
  client = login()
  if client is None:
    return
  for notif in client.app.bsky.notification.list_notifications().notifications[:n]:
    texto = getattr(notif.record, 'text', '') or ''
    print(notif.indexed_at, '|', notif.reason, '| leída:', notif.is_read,
          '|', notif.author.handle, '|', texto[:60])


if __name__ == '__main__':
  main()
