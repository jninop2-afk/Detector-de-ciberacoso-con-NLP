import os
import pandas as pd
from src.preprocessing import clean_text, prepare_datasets
from src.train import train_pipeline

FEEDBACK_FILE = 'data/raw/feedback_admin.csv'
RAW_DATA_FILE = 'data/raw/colombian_cyberbullying.csv'


def save_admin_correction(texto: str, es_ciberacoso: int, categoria: int = 0):
  """Guarda la corrección del admin en el CSV acumulativo de feedback."""
  os.makedirs(os.path.dirname(FEEDBACK_FILE), exist_ok=True)

  new_entry = pd.DataFrame([{
      'texto': texto,
      'ciberacoso': int(es_ciberacoso),
      'categoria': int(categoria),
  }])

  if not os.path.exists(FEEDBACK_FILE):
    new_entry.to_csv(FEEDBACK_FILE, index=False, encoding='utf-8')
  else:
    new_entry.to_csv(
        FEEDBACK_FILE, mode='a', header=False, index=False, encoding='utf-8'
    )


def retrain_from_feedback():
  """Combina las correcciones guardadas con el dataset base y reentrena los modelos."""
  if not os.path.exists(FEEDBACK_FILE):
    print('No hay nuevos registros de feedback para reentrenar.')
    return

  df_raw = pd.read_csv(RAW_DATA_FILE)
  df_feedback = pd.read_csv(FEEDBACK_FILE)

  # Anexar feedback al dataset original
  df_combined = pd.concat([df_raw, df_feedback], ignore_index=True)
  df_combined.to_csv(RAW_DATA_FILE, index=False, encoding='utf-8')

  # Reprocesar y reentrenar
  prepare_datasets()
  train_pipeline()
  print(' Modelos reentrenados exitosamente con el nuevo feedback.')