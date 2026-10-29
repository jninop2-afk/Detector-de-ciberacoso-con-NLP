"""Traducción de los datasets en inglés al español (heredado del proyecto original).

Traduce los mensajes ofensivos (oh_label = 1) y una muestra de los no
ofensivos de los datasets de Twitter (racismo, sexismo) y YouTube, y les
asigna una categoría 1-4 con reglas léxicas. El resultado se guarda en
data/processed/ingles_traducido.csv y src/data.py lo incorpora al
entrenamiento de la ETAPA 1 (binario).

La traducción es lenta (usa Google Translate vía deep-translator), por eso:
  - se hace una sola vez y queda en caché,
  - es reanudable: si se interrumpe, vuelve a ejecutarse desde donde iba.

Uso:
    python main.py traducir                      # todo
    python main.py traducir --max-por-archivo 300  # prueba rápida
"""

import argparse
import re

import pandas as pd

from src import config
from src.preprocessing import clean_text

# Las categorías siguen el esquema del dataset colombiano (config.CATEGORIES):
#   1 amenazas, 2 insultos, 3 odio/muerte, 4 difamación
_AMENAZA = re.compile(
    r'\b(matar|matarte|golpear|sufrir|atacar|sabemos donde|cuidese|cuidate|bala|'
    r'buscarte|violencia|te voy a|vas a pagar)\b'
)
_ODIO_MUERTE = re.compile(
    r'\b(ojala|maldit\w*|pudras|muerete|mueras|muerte a|exterminar|plaga|'
    r'deberian morir|no mereces vivir)\b'
)
_DIFAMACION = re.compile(
    r'\b(ladron\w*|roba\w*|acosador\w*|violador\w*|estafador\w*|corrupt\w*|'
    r'asesin\w*|criminal\w*|delincuente\w*|calumni\w*)\b'
)


def subclasificar(texto_es: str, anotacion: str = '') -> int:
  """Asigna una categoría 1-4 a un texto ya marcado como ofensivo."""
  txt = clean_text(texto_es)
  annot = str(anotacion or '').lower()
  if _AMENAZA.search(txt) or 'threat' in annot:
    return 1
  if _ODIO_MUERTE.search(txt) or 'curse' in annot:
    return 3
  if _DIFAMACION.search(txt) or 'defamation' in annot:
    return 4
  return 2  # insulto / ofensa general por defecto


def _translator():
  try:
    from deep_translator import GoogleTranslator
  except ImportError as err:
    raise SystemExit(
        'Falta deep-translator. Instálalo con: pip install deep-translator'
    ) from err
  return GoogleTranslator(source='en', target='es')


def _traducir(translator, texto: str) -> str | None:
  if not isinstance(texto, str) or not texto.strip():
    return None
  try:
    return translator.translate(texto[:400])
  except Exception:
    return None  # se reintenta en la próxima ejecución


def _muestras(spec: dict, n_negativos: int, max_por_archivo: int | None) -> pd.DataFrame:
  df = pd.read_csv(spec['file'])
  df = df.dropna(subset=[spec['col_text'], spec['col_label']])
  pos = df[df[spec['col_label']] == 1]
  neg = df[df[spec['col_label']] == 0]
  neg = neg.sample(n=min(n_negativos, len(neg)), random_state=config.RANDOM_STATE)
  if max_por_archivo:
    pos = pos.head(max_por_archivo)
    neg = neg.head(max(1, max_por_archivo // 4))
  out = pd.concat([pos, neg])
  annot_col = spec.get('col_annot')
  return pd.DataFrame({
      'origen': spec['file'].name,
      'texto_en': out[spec['col_text']].astype(str).values,
      'ciberacoso': out[spec['col_label']].astype(int).values,
      'anotacion': out[annot_col].astype(str).values if annot_col else '',
  })


def traducir_datasets(n_negativos: int = 500, max_por_archivo: int | None = None):
  config.PROCESSED_DIR.mkdir(parents=True, exist_ok=True)
  cache = config.ENGLISH_TRANSLATED_CSV
  hechos = pd.read_csv(cache) if cache.exists() else pd.DataFrame(
      columns=['origen', 'texto_en', 'texto', 'ciberacoso', 'categoria'])
  ya = set(zip(hechos['origen'], hechos['texto_en']))
  translator = _translator()

  nuevos = []
  for spec in config.ENGLISH_DATASETS:
    if not spec['file'].exists():
      print(f'   (omitido, no existe) {spec["file"].name}')
      continue
    muestras = _muestras(spec, n_negativos, max_por_archivo)
    pendientes = [r for r in muestras.itertuples() if (r.origen, r.texto_en) not in ya]
    print(f'--> {spec["file"].name}: {len(muestras)} filas, {len(pendientes)} por traducir')
    for i, r in enumerate(pendientes, 1):
      es = _traducir(translator, r.texto_en)
      if es is None:
        continue
      cat = subclasificar(es, r.anotacion) if r.ciberacoso == 1 else 0
      nuevos.append({'origen': r.origen, 'texto_en': r.texto_en, 'texto': es,
                     'ciberacoso': r.ciberacoso, 'categoria': cat})
      if i % 200 == 0:  # guardado parcial: el proceso es reanudable
        print(f'     {i}/{len(pendientes)}')
        hechos = pd.concat([hechos, pd.DataFrame(nuevos)], ignore_index=True)
        hechos.to_csv(cache, index=False)
        nuevos = []

  hechos = pd.concat([hechos, pd.DataFrame(nuevos)], ignore_index=True)
  hechos.to_csv(cache, index=False)
  print(f'\n Traducciones guardadas en "{cache}" ({len(hechos)} filas).')
  print(hechos.groupby(['origen', 'categoria']).size().unstack(fill_value=0).to_string())
  print('\n Ejecuta "python main.py train" para incluirlas en el entrenamiento.')


def main(argv=None):
  parser = argparse.ArgumentParser(prog='main.py traducir')
  parser.add_argument('--negativos', type=int, default=500,
                      help='mensajes no ofensivos por archivo (default 500)')
  parser.add_argument('--max-por-archivo', type=int, default=None,
                      help='limita las filas por archivo (para pruebas)')
  args = parser.parse_args(argv)
  traducir_datasets(args.negativos, args.max_por_archivo)


if __name__ == '__main__':
  main()
