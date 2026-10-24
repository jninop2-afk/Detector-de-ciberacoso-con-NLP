import os
import joblib
import numpy as np
import pandas as pd
from src.preprocessing import clean_text


def auto_label_dataset(
    input_csv_path: str = 'data/raw/CorpusBullying.csv',
    output_csv_path: str = 'data/processed/CorpusBullying_autolabeled.csv',
    models_dir: str = 'models',
    sep: str = ';',
    text_column: str = 'SpanishTweet',
    confidence_threshold: float = 0.70,
):
  """Carga un dataset no etiquetado o parcialmente etiquetado, genera predicciones

  binarias y de categoría en lote, y exporta un CSV enriquecido.
  """
  print(f'--> Cargando dataset desde "{input_csv_path}"...')
  if not os.path.exists(input_csv_path):
    raise FileNotFoundError(f'No se encontró el archivo: {input_csv_path}')

  # Cargar datos (soporta separadores como ';' o ',')
  df = pd.read_csv(input_csv_path, sep=sep)

  if text_column not in df.columns:
    raise KeyError(
        f'La columna de texto "{text_column}" no existe en el archivo.'
    )

  # 1. Cargar artefactos del modelo
  print(f'--> Cargando modelos entrenados desde "{models_dir}/"...')
  vectorizer = joblib.load(os.path.join(models_dir, 'tfidf_vectorizer.pkl'))
  binary_model = joblib.load(os.path.join(models_dir, 'binary_model.pkl'))
  severity_model = joblib.load(os.path.join(models_dir, 'severity_model.pkl'))

  # 2. Preprocesamiento de texto en lote
  print('--> Preprocesando textos (limpieza + leetspeak + normalización)...')
  df['texto_limpio'] = df[text_column].apply(clean_text)

  # Filtrar filas cuyo texto haya quedado totalmente vacío
  valid_mask = df['texto_limpio'] != ''
  df_valid = df[valid_mask].copy()

  # 3. Vectorización TF-IDF
  print('--> Vectorizando textos con TF-IDF...')
  X_tfidf = vectorizer.transform(df_valid['texto_limpio'])

  # 4. Predicción en Lote (Etapa 1: Filtro Binario)
  print('--> Clasificando ciberacoso (Etapa 1)...')
  binary_preds = binary_model.predict(X_tfidf)
  binary_probs = binary_model.predict_proba(X_tfidf)[:, 1]

  # 5. Predicción en Lote (Etapa 2: Gravedad / Categorías)
  print('--> Evaluando categorías de gravedad (Etapa 2)...')
  severity_preds = severity_model.predict(X_tfidf)
  severity_probs = np.max(severity_model.predict_proba(X_tfidf), axis=1)

  # 6. Asignar resultados al DataFrame
  df_valid['pred_ciberacoso'] = binary_preds
  df_valid['prob_ciberacoso'] = np.round(binary_probs, 4)

  # Asignar categoría únicamente cuando la predicción binaria es Ciberacoso (1)
  df_valid['pred_categoria'] = np.where(binary_preds == 1, severity_preds, 0)
  df_valid['prob_categoria'] = np.where(
      binary_preds == 1, np.round(severity_probs, 4), 1.0
  )

  # Confianza global combinada
  confianza = np.where(
      binary_preds == 1,
      (binary_probs + severity_probs) / 2,
      1.0 - binary_probs,
  )
  df_valid['confianza_global'] = np.round(confianza, 4)

  # Marcar registros dudosos para revisión humana
  df_valid['requiere_revision'] = (
      df_valid['confianza_global'] < confidence_threshold
  )

  # Reintegrar con el DataFrame original
  df_final = df_valid.drop(columns=['texto_limpio'])

  # 7. Exportar dataset enriquecido
  os.makedirs(os.path.dirname(output_csv_path), exist_ok=True)
  df_final.to_csv(output_csv_path, index=False, encoding='utf-8')

  print('\n Proceso de autotiquetado completado exitosamente.')
  print(f'   - Archivo generado: {output_csv_path}')
  print(
      '   - Mensajes clasificados como CIBERACOSO:'
      f' {(df_final["pred_ciberacoso"] == 1).sum()}'
  )
  print(
      '   - Mensajes clasificados como SEGUROS:'
      f' {(df_final["pred_ciberacoso"] == 0).sum()}'
  )
  print('\n Distribución de categorías asignadas:')
  print(df_final['pred_categoria'].value_counts().to_string())
  print(
      f'\n Registros con baja confianza (< {int(confidence_threshold*100)}%)'
      f' que requieren revisión: {df_final["requiere_revision"].sum()}'
  )


if __name__ == '__main__':
  # Ejecutar autotiquetado sobre CorpusBullying.csv
  auto_label_dataset(
      input_csv_path='data/raw/CorpusBullying.csv',
      output_csv_path='data/processed/CorpusBullying_autolabeled.csv',
      sep=';',
      text_column='SpanishTweet',
      confidence_threshold=0.70,
  )