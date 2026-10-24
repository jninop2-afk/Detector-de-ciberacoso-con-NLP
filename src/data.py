"""Carga y unificación de datasets para entrenamiento.

Los CSV crudos nunca se modifican: el feedback de los administradores y las
correcciones de etiquetas se aplican en memoria cada vez que se entrena.
"""

import sqlite3

import pandas as pd

from src import config
from src.preprocessing import clean_text

# Prioridad al deduplicar: a igual texto gana la fuente con mayor valor
SOURCE_PRIORITY = {
    'corpus': 0,
    'colombia': 1,
    'refuerzo': 2,
    'feedback': 3,
    'correccion': 4,
}


def load_colombian() -> pd.DataFrame:
  df = pd.read_csv(config.COLOMBIAN_CSV)
  # Algunas filas tienen el texto partido en una columna extra por comas
  extra_cols = [c for c in df.columns if c.startswith('Unnamed')]
  for col in extra_cols:
    df['texto'] = df['texto'].fillna('') + ' ' + df[col].fillna('')
  df['texto'] = df['texto'].astype(str).str.strip()

  df['categoria'] = pd.to_numeric(
      df['categoria'].astype(str).str.strip().replace({'o': '0', 'O': '0'}),
      errors='coerce',
  )
  df = df.dropna(subset=['categoria'])
  df['categoria'] = df['categoria'].astype(int)
  df = df[df['categoria'].between(0, 4) & (df['texto'] != '')]
  # La etiqueta binaria se deriva de la categoría para que sean coherentes
  df['ciberacoso'] = (df['categoria'] > 0).astype(int)
  return df[['texto', 'ciberacoso', 'categoria']].assign(fuente='colombia')


def load_corpus(n_negatives: int | None = 6000) -> pd.DataFrame:
  """CorpusBullying: etiqueta binaria, sin categoría de gravedad."""
  if not config.CORPUS_CSV.exists():
    return pd.DataFrame(columns=['texto', 'ciberacoso', 'categoria', 'fuente'])
  df = pd.read_csv(config.CORPUS_CSV, sep=';').dropna(
      subset=['SpanishTweet', 'Label']
  )
  df = df.rename(columns={'SpanishTweet': 'texto', 'Label': 'ciberacoso'})
  df['ciberacoso'] = df['ciberacoso'].astype(int)
  positives = df[df['ciberacoso'] == 1]
  negatives = df[df['ciberacoso'] == 0]
  if n_negatives is not None and len(negatives) > n_negatives:
    negatives = negatives.sample(n=n_negatives, random_state=config.RANDOM_STATE)
  out = pd.concat([positives, negatives], ignore_index=True)
  out['categoria'] = pd.NA
  return out[['texto', 'ciberacoso', 'categoria']].assign(fuente='corpus')


def load_refuerzo() -> pd.DataFrame:
  if not config.REFUERZO_CSV.exists():
    return pd.DataFrame(columns=['texto', 'ciberacoso', 'categoria', 'fuente'])
  df = pd.read_csv(config.REFUERZO_CSV).dropna(subset=['texto', 'categoria'])
  df['texto'] = df['texto'].astype(str).str.strip('" ')
  df['categoria'] = df['categoria'].astype(int)
  df['ciberacoso'] = (df['categoria'] > 0).astype(int)
  return df[['texto', 'ciberacoso', 'categoria']].assign(fuente='refuerzo')


def load_feedback() -> pd.DataFrame:
  """Feedback de administradores: CSV heredado + tabla SQLite del bot."""
  frames = []
  if config.LEGACY_FEEDBACK_CSV.exists():
    df = pd.read_csv(config.LEGACY_FEEDBACK_CSV)
    if {'texto', 'categoria'} <= set(df.columns):
      frames.append(df[['texto', 'categoria']])

  if config.DB_PATH.exists():
    with sqlite3.connect(config.DB_PATH) as conn:
      has_table = conn.execute(
          "SELECT 1 FROM sqlite_master WHERE type='table' AND name='admin_feedback'"
      ).fetchone()
      if has_table:
        frames.append(
            pd.read_sql_query(
                'SELECT message_text AS texto, category AS categoria'
                ' FROM admin_feedback ORDER BY id',
                conn,
            )
        )

  if not frames:
    return pd.DataFrame(columns=['texto', 'ciberacoso', 'categoria', 'fuente'])
  df = pd.concat(frames, ignore_index=True).dropna()
  df['categoria'] = df['categoria'].astype(int)
  df['ciberacoso'] = (df['categoria'] > 0).astype(int)
  return df[['texto', 'ciberacoso', 'categoria']].assign(fuente='feedback')


def load_corrections() -> pd.DataFrame:
  """Correcciones manuales generadas tras revisar label_review.csv."""
  if not config.LABEL_CORRECTIONS_CSV.exists():
    return pd.DataFrame(columns=['texto', 'ciberacoso', 'categoria', 'fuente'])
  df = pd.read_csv(config.LABEL_CORRECTIONS_CSV).dropna(
      subset=['texto', 'categoria_corregida']
  )
  df['categoria'] = df['categoria_corregida'].astype(int)
  df['ciberacoso'] = (df['categoria'] > 0).astype(int)
  return df[['texto', 'ciberacoso', 'categoria']].assign(fuente='correccion')


def _finalize(df: pd.DataFrame, min_tokens: int = 2) -> pd.DataFrame:
  """Limpia, filtra ruido y deduplica dando prioridad a fuentes humanas."""
  df = df.copy()
  df['texto_limpio'] = df['texto'].map(clean_text)
  n_tokens = df['texto_limpio'].str.split().str.len()
  trusted = df['fuente'].isin(['feedback', 'correccion'])
  # Textos de 1 palabra (p. ej. sólo un nombre de usuario) son ruido,
  # salvo que un humano los haya etiquetado explícitamente
  df = df[(n_tokens >= min_tokens) | (trusted & (n_tokens >= 1))]
  df['_prio'] = df['fuente'].map(SOURCE_PRIORITY)
  df = df.sort_values('_prio', kind='stable').drop_duplicates(
      subset=['texto_limpio'], keep='last'
  )
  return df.drop(columns=['_prio']).reset_index(drop=True)


def build_binary_dataset(n_corpus_negatives: int | None = 6000) -> pd.DataFrame:
  """Dataset para la etapa 1: ¿es ciberacoso? (0/1)."""
  df = pd.concat(
      [
          load_corpus(n_corpus_negatives),
          load_colombian(),
          load_refuerzo(),
          load_feedback(),
          load_corrections(),
      ],
      ignore_index=True,
  )
  df = _finalize(df)
  df['ciberacoso'] = df['ciberacoso'].astype(int)
  return df


def build_category_dataset() -> pd.DataFrame:
  """Dataset con categoría 0-4 conocida (sin CorpusBullying)."""
  df = pd.concat(
      [load_colombian(), load_refuerzo(), load_feedback(), load_corrections()],
      ignore_index=True,
  )
  df = _finalize(df)
  df['categoria'] = df['categoria'].astype(int)
  return df


def describe(df: pd.DataFrame, label: str) -> str:
  counts = df.groupby(['fuente', label]).size().unstack(fill_value=0)
  return counts.to_string()
