"""Autoetiquetado masivo de un CSV con el modelo clásico.

Usa sólo el modelo clásico (vectorizado) por velocidad; las filas con baja
confianza se marcan para revisión humana o para pasarlas por RoBERTa.
"""

import pandas as pd

from src import config
from src.predict import CyberbullyingDetector


def auto_label_dataset(
    input_csv_path=config.CORPUS_CSV,
    output_csv_path=config.PROCESSED_DIR / 'CorpusBullying_autolabeled.csv',
    sep: str = ';',
    text_column: str = 'SpanishTweet',
    confidence_threshold: float = config.CONFIDENCE_THRESHOLD,
):
  print(f'--> Cargando "{input_csv_path}"...')
  df = pd.read_csv(input_csv_path, sep=sep)
  if text_column not in df.columns:
    raise KeyError(f'La columna "{text_column}" no existe en el archivo.')
  df = df.dropna(subset=[text_column]).reset_index(drop=True)

  detector = CyberbullyingDetector(use_roberta=False)
  print(f'--> Clasificando {len(df)} textos...')
  out = detector.predict_classic_batch(df[text_column].astype(str))

  p = out['prob_ciberacoso']
  df['pred_ciberacoso'] = out['es_ciberacoso'].astype(int)
  df['prob_ciberacoso'] = p.round(4)
  df['pred_categoria'] = out['categoria']
  df['confianza'] = (
      pd.Series(p).where(out['es_ciberacoso'], 1 - p).round(4)
  )
  near_threshold = (abs(p - detector.binary_threshold) < config.UNCERTAINTY_MARGIN)
  low_category = out['es_ciberacoso'] & (out['confianza_categoria'] < confidence_threshold)
  df['requiere_revision'] = near_threshold | low_category

  config.PROCESSED_DIR.mkdir(parents=True, exist_ok=True)
  df.to_csv(output_csv_path, index=False, encoding='utf-8')
  print(f'\n Archivo generado: {output_csv_path}')
  print(df['pred_categoria'].value_counts().sort_index().to_string())
  print(f' Requieren revisión: {int(df["requiere_revision"].sum())}')


if __name__ == '__main__':
  auto_label_dataset()
