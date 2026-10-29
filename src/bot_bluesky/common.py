"""Utilidades compartidas por los bots de Bluesky (menciones y vigilancia)."""

import logging
import re

from atproto import Client, models

from src import config
from src.predict import CyberbullyingDetector

log = logging.getLogger('bluesky')

MAX_CARACTERES = 300  # límite de un post en Bluesky

_detector: CyberbullyingDetector | None = None


def get_detector() -> CyberbullyingDetector:
  """Carga el detector híbrido una sola vez (clásico + RoBERTa si está activo)."""
  global _detector
  if _detector is None:
    _detector = CyberbullyingDetector()
    _detector.warmup()
    log.info('Detector listo. RoBERTa: %s', _detector.roberta_mode)
  return _detector


def analizar(texto: str) -> dict:
  return get_detector().predict(texto)


def login() -> Client | None:
  if not config.BLUESKY_HANDLE or not config.BLUESKY_APP_PASSWORD:
    print('ERROR: faltan BLUESKY_HANDLE y/o BLUESKY_APP_PASSWORD en el archivo .env')
    return None
  client = Client()
  client.login(config.BLUESKY_HANDLE, config.BLUESKY_APP_PASSWORD)
  return client


def modo_reportes() -> str:
  return 'REPORTES REALES' if config.BLUESKY_REPORTES_REALES else 'simulación de reportes'


def limpiar_menciones(texto: str) -> str:
  """Quita los @handles para analizar sólo el contenido."""
  return re.sub(r'@\S+', '', texto or '').strip()


def construir_respuesta(r: dict) -> str:
  prob = r['confianza'] * 100
  if not r['es_ciberacoso']:
    texto = f'No detecté ciberacoso en ese mensaje ({prob:.0f}% de confianza).'
  else:
    texto = (
        f'Posible ciberacoso detectado: {r["categoria_nombre"]} ({prob:.0f}% de confianza).\n'
        'Es un análisis automático y puede equivocarse.'
    )
    if r['accion_sugerida'] == 'REVISAR_POR_ADMIN':
      texto += ' Caso dudoso: requiere revisión humana.'
  return texto[:MAX_CARACTERES]


def _reportar_post(client: Client, uri: str, cid: str, r: dict) -> None:
  client.com.atproto.moderation.create_report(
      models.ComAtprotoModerationCreateReport.Data(
          reason_type=models.ComAtprotoModerationDefs.ReasonRude,
          reason=(
              'Detección automática (proyecto universitario): '
              f'{r["categoria_nombre"]} ({r["confianza"] * 100:.0f}% de confianza)'
          ),
          subject=models.ComAtprotoRepoStrongRef.Main(uri=uri, cid=cid),
      )
  )


def gestionar_reporte(client: Client, r: dict, uri: str, cid: str) -> str:
  """Decide si se reporta el post y devuelve el texto de la acción tomada.

  Igual que en Discord, sólo se actúa automáticamente cuando el detector
  sugiere SANCIONAR; los casos dudosos (REVISAR_POR_ADMIN) no se reportan.
  """
  if not r['es_ciberacoso']:
    return 'No hay nada que reportar.'
  if r['accion_sugerida'] == 'REVISAR_POR_ADMIN':
    return 'No lo reporté: caso dudoso, requiere revisión humana.'
  umbral = config.BLUESKY_UMBRAL_REPORTE
  if r['confianza'] < umbral:
    return f'No lo reporté: la confianza es menor a {umbral * 100:.0f}%.'
  if not config.BLUESKY_REPORTES_REALES:
    return '[Simulación] Este post se habría reportado a la moderación.'
  _reportar_post(client, uri, cid, r)
  return 'Reporte enviado a la moderación de Bluesky.'
