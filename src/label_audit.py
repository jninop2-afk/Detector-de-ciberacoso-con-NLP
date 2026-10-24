"""Detección de etiquetas probablemente erróneas (aprendizaje con confianza).

Entrena con validación cruzada un clasificador 0-4 y, para cada ejemplo,
obtiene la probabilidad que el modelo asigna a su etiqueta actual SIN
haberlo visto en el entrenamiento. Si esa probabilidad es muy baja y otra
categoría es muy probable, la etiqueta es sospechosa.

Flujo de trabajo:
  1. python main.py audit           -> genera data/processed/label_review.csv
  2. Revisa el CSV y llena la columna 'categoria_corregida' donde aplique.
  3. Guarda las filas corregidas en data/raw/label_corrections.csv
     (columnas: texto, categoria_corregida).
  4. python main.py train           -> las correcciones se aplican solas.
"""

import numpy as np
from sklearn.linear_model import LogisticRegression
from sklearn.model_selection import StratifiedKFold, cross_val_predict

from src import config
from src.data import build_category_dataset
from src.train import build_features


def audit_labels(max_label_prob: float = 0.20, min_suggested_prob: float = 0.50):
  df = build_category_dataset()
  y = df['categoria'].to_numpy()
  print(f'--> Auditando {len(df)} ejemplos con categoría conocida...')

  features = build_features()
  X = features.fit_transform(df['texto'])
  model = LogisticRegression(C=2.0, class_weight='balanced', max_iter=3000)
  cv = StratifiedKFold(n_splits=5, shuffle=True, random_state=config.RANDOM_STATE)
  probs = cross_val_predict(model, X, y, cv=cv, method='predict_proba')

  classes = np.unique(y)
  label_idx = np.searchsorted(classes, y)
  df['prob_etiqueta_actual'] = probs[np.arange(len(y)), label_idx].round(3)
  df['categoria_sugerida'] = classes[probs.argmax(axis=1)]
  df['prob_sugerida'] = probs.max(axis=1).round(3)
  # Margen: cuánto más cree el modelo en la sugerida que en la actual
  df['sospecha'] = (df['prob_sugerida'] - df['prob_etiqueta_actual']).round(3)

  suspicious = df[
      (df['prob_etiqueta_actual'] < max_label_prob)
      & (df['prob_sugerida'] >= min_suggested_prob)
      & (df['categoria_sugerida'] != df['categoria'])
  ].sort_values('sospecha', ascending=False)

  out = suspicious[[
      'texto', 'fuente', 'categoria', 'categoria_sugerida',
      'prob_etiqueta_actual', 'prob_sugerida', 'sospecha',
  ]].copy()
  out['categoria_corregida'] = ''

  config.PROCESSED_DIR.mkdir(parents=True, exist_ok=True)
  out.to_csv(config.LABEL_REVIEW_CSV, index=False, encoding='utf-8-sig')

  print(f'\n {len(out)} etiquetas sospechosas ({len(out) / len(df):.1%} del total).')
  print(' Matriz etiqueta actual (filas) -> sugerida (columnas):')
  print(
      out.groupby(['categoria', 'categoria_sugerida']).size()
      .unstack(fill_value=0).to_string()
  )
  print(f'\n Archivo para revisión: {config.LABEL_REVIEW_CSV}')
  return out


if __name__ == '__main__':
  audit_labels()
