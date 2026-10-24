"""Entrenamiento del modelo clásico (TF-IDF + rasgos léxicos + clasificador lineal).

Dos etapas:
  1. Binario: ¿el mensaje es ciberacoso?
  2. Gravedad: si lo es, ¿qué categoría (1-4)?

Las métricas por clase del conjunto de prueba se guardan junto al modelo:
el detector las usa para decidir cuándo delegar en RoBERTa.
"""

from datetime import datetime
import json

import joblib
import numpy as np
from sklearn.calibration import CalibratedClassifierCV
from sklearn.feature_extraction.text import TfidfVectorizer
from sklearn.linear_model import LogisticRegression
from sklearn.metrics import (
    classification_report,
    confusion_matrix,
    f1_score,
)
from sklearn.model_selection import (
    StratifiedKFold,
    cross_val_predict,
    cross_val_score,
    train_test_split,
)
from sklearn.pipeline import FeatureUnion, Pipeline
from sklearn.svm import LinearSVC

from src import config
from src.data import build_binary_dataset, build_category_dataset, describe
from src.features import LexiconFeatures
from src.preprocessing import clean_text


def build_features() -> FeatureUnion:
  # Sin stopwords: pronombres como "te", "tu", "usted" indican a quién va
  # dirigido el mensaje y son clave para distinguir acoso de groserías.
  return FeatureUnion([
      (
          'word',
          TfidfVectorizer(
              preprocessor=clean_text,
              analyzer='word',
              ngram_range=(1, 2),
              min_df=2,
              max_features=40000,
              sublinear_tf=True,
          ),
      ),
      (
          'char',
          TfidfVectorizer(
              preprocessor=clean_text,
              analyzer='char_wb',
              ngram_range=(2, 5),
              min_df=2,
              max_features=60000,
              sublinear_tf=True,
          ),
      ),
      ('lexicon', LexiconFeatures()),
  ])


def candidate_models() -> dict:
  return {
      'logreg_C1': LogisticRegression(
          C=1.0, class_weight='balanced', max_iter=3000
      ),
      'logreg_C5': LogisticRegression(
          C=5.0, class_weight='balanced', max_iter=3000
      ),
      'svm_calibrada': CalibratedClassifierCV(
          LinearSVC(C=0.3, class_weight='balanced'), cv=3, method='sigmoid'
      ),
  }


def _select_model(X, y, scoring: str) -> tuple[str, object, dict]:
  cv = StratifiedKFold(n_splits=5, shuffle=True, random_state=config.RANDOM_STATE)
  scores = {}
  for name, model in candidate_models().items():
    scores[name] = float(cross_val_score(model, X, y, cv=cv, scoring=scoring).mean())
    print(f'     {name:<15} {scoring} CV = {scores[name]:.4f}')
  best = max(scores, key=scores.get)
  return best, candidate_models()[best], scores


def _best_threshold(y_true, probs) -> float:
  grid = np.arange(0.20, 0.81, 0.01)
  f1s = [f1_score(y_true, probs >= t) for t in grid]
  return float(round(grid[int(np.argmax(f1s))], 2))


def train_binary(df, refit_full: bool = True) -> tuple[Pipeline, float, dict]:
  print('\n--> [ETAPA 1] Detector binario')
  print(describe(df, 'ciberacoso'))
  X_tr, X_te, y_tr, y_te, src_tr, src_te = train_test_split(
      df['texto'], df['ciberacoso'], df['fuente'],
      test_size=0.20, random_state=config.RANDOM_STATE, stratify=df['ciberacoso'],
  )

  features = build_features()
  F_tr = features.fit_transform(X_tr)
  F_te = features.transform(X_te)

  best_name, model, cv_scores = _select_model(F_tr, y_tr, 'f1')

  # Umbral óptimo con predicciones fuera de pliegue (sin tocar el test)
  cv = StratifiedKFold(n_splits=5, shuffle=True, random_state=config.RANDOM_STATE)
  oof = cross_val_predict(model, F_tr, y_tr, cv=cv, method='predict_proba')[:, 1]
  threshold = _best_threshold(y_tr, oof)

  model.fit(F_tr, y_tr)
  probs = model.predict_proba(F_te)[:, 1]
  preds = (probs >= threshold).astype(int)

  report = classification_report(
      y_te, preds, target_names=['Seguro', 'Ciberacoso'], output_dict=True
  )
  print(f'\n   Modelo elegido: {best_name} | umbral = {threshold}')
  print(classification_report(y_te, preds, target_names=['Seguro', 'Ciberacoso']))

  # Rendimiento en el dominio objetivo (jerga colombiana)
  mask_col = (src_te == 'colombia').to_numpy()
  f1_col = float(f1_score(y_te[mask_col], preds[mask_col])) if mask_col.any() else None
  if f1_col is not None:
    print(f'   F1 sólo en datos colombianos: {f1_col:.4f}')

  metrics = {
      'modelo': best_name,
      'cv_scores': cv_scores,
      'umbral': threshold,
      'f1_ciberacoso': report['Ciberacoso']['f1-score'],
      'precision_ciberacoso': report['Ciberacoso']['precision'],
      'recall_ciberacoso': report['Ciberacoso']['recall'],
      'f1_seguro': report['Seguro']['f1-score'],
      'f1_colombia': f1_col,
      'accuracy': report['accuracy'],
      'matriz_confusion': confusion_matrix(y_te, preds).tolist(),
      'n_train': int(len(X_tr)),
      'n_test': int(len(X_te)),
  }

  pipeline = Pipeline([('features', features), ('clf', model)])
  if refit_full:
    pipeline = Pipeline([
        ('features', build_features()),
        ('clf', candidate_models()[best_name]),
    ])
    pipeline.fit(df['texto'], df['ciberacoso'])
  return pipeline, threshold, metrics


def train_severity(df, refit_full: bool = True) -> tuple[Pipeline, dict]:
  print('\n--> [ETAPA 2] Clasificador de gravedad (categorías 1-4)')
  df = df[df['categoria'] > 0]
  print(describe(df, 'categoria'))
  X_tr, X_te, y_tr, y_te = train_test_split(
      df['texto'], df['categoria'],
      test_size=0.20, random_state=config.RANDOM_STATE, stratify=df['categoria'],
  )

  features = build_features()
  F_tr = features.fit_transform(X_tr)
  F_te = features.transform(X_te)

  best_name, model, cv_scores = _select_model(F_tr, y_tr, 'f1_macro')
  model.fit(F_tr, y_tr)
  preds = model.predict(F_te)

  report = classification_report(y_te, preds, output_dict=True, zero_division=0)
  print(f'\n   Modelo elegido: {best_name}')
  print(classification_report(y_te, preds, zero_division=0))

  metrics = {
      'modelo': best_name,
      'cv_scores': cv_scores,
      'f1_macro': report['macro avg']['f1-score'],
      'f1_por_clase': {
          str(c): report[str(c)]['f1-score'] for c in sorted(y_te.unique())
      },
      'matriz_confusion': confusion_matrix(y_te, preds).tolist(),
      'n_train': int(len(X_tr)),
      'n_test': int(len(X_te)),
  }

  pipeline = Pipeline([('features', features), ('clf', model)])
  if refit_full:
    pipeline = Pipeline([
        ('features', build_features()),
        ('clf', candidate_models()[best_name]),
    ])
    pipeline.fit(df['texto'], df['categoria'])
  return pipeline, metrics


def train_classic(refit_full: bool = True) -> dict:
  binary_df = build_binary_dataset()
  category_df = build_category_dataset()

  binary_pipe, threshold, bin_metrics = train_binary(binary_df, refit_full)
  severity_pipe, sev_metrics = train_severity(category_df, refit_full)

  metrics = {
      'entrenado_en': datetime.now().isoformat(timespec='seconds'),
      'binario': bin_metrics,
      'gravedad': sev_metrics,
  }

  config.MODELS_DIR.mkdir(parents=True, exist_ok=True)
  joblib.dump(
      {
          'binary_pipeline': binary_pipe,
          'severity_pipeline': severity_pipe,
          'binary_threshold': threshold,
          'metrics': metrics,
      },
      config.CLASSIC_MODEL_PATH,
      compress=3,
  )
  config.CLASSIC_METRICS_PATH.write_text(
      json.dumps(metrics, indent=2, ensure_ascii=False), encoding='utf-8'
  )

  weak = [
      c for c, f1 in sev_metrics['f1_por_clase'].items()
      if f1 < config.MIN_CLASS_F1
  ]
  print(f'\n Modelo clásico guardado en "{config.CLASSIC_MODEL_PATH}".')
  if weak:
    print(
        f' Categorías con F1 < {config.MIN_CLASS_F1}: {weak}. '
        'Sus predicciones se delegarán a RoBERTa.'
    )
  return metrics


if __name__ == '__main__':
  train_classic()
