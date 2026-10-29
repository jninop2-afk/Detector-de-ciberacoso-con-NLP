"""Configuración central del proyecto (rutas, categorías y umbrales)."""

import os
from pathlib import Path

from dotenv import load_dotenv

load_dotenv()

BASE_DIR = Path(__file__).resolve().parent.parent
DATA_DIR = BASE_DIR / 'data'
RAW_DIR = DATA_DIR / 'raw'
PROCESSED_DIR = DATA_DIR / 'processed'
MODELS_DIR = BASE_DIR / 'models'

# Fuentes de datos
COLOMBIAN_CSV = RAW_DIR / 'colombian_cyberbullying.csv'
CORPUS_CSV = RAW_DIR / 'CorpusBullying.csv'
REFUERZO_CSV = RAW_DIR / 'refuerzo_Categoria.csv'
LEGACY_FEEDBACK_CSV = RAW_DIR / 'feedback_admin.csv'
# Correcciones manuales de etiquetas (texto, categoria_corregida)
LABEL_CORRECTIONS_CSV = RAW_DIR / 'label_corrections.csv'
LABEL_REVIEW_CSV = PROCESSED_DIR / 'label_review.csv'

# Datasets en inglés (Twitter racismo/sexismo y YouTube). Se traducen una sola
# vez con "python main.py traducir" y se cachean en data/processed/.
ENGLISH_DATASETS = [
    {'file': RAW_DIR / 'twitter_racism_parsed_dataset.csv',
     'col_text': 'Text', 'col_label': 'oh_label', 'col_annot': 'Annotation'},
    {'file': RAW_DIR / 'twitter_sexism_parsed_dataset.csv',
     'col_text': 'Text', 'col_label': 'oh_label', 'col_annot': 'Annotation'},
    {'file': RAW_DIR / 'youtube_parsed_dataset.csv',
     'col_text': 'Text', 'col_label': 'oh_label', 'col_annot': None},
]
ENGLISH_TRANSLATED_CSV = PROCESSED_DIR / 'ingles_traducido.csv'

DB_PATH = DATA_DIR / 'bot_database.db'

# --- Bluesky ---
BLUESKY_HANDLE = os.getenv('BLUESKY_HANDLE')
BLUESKY_APP_PASSWORD = os.getenv('BLUESKY_APP_PASSWORD')
# Por defecto los reportes son simulados; BLUESKY_REPORTES_REALES=1 los envía
BLUESKY_REPORTES_REALES = os.getenv('BLUESKY_REPORTES_REALES') == '1'
BLUESKY_UMBRAL_REPORTE = float(os.getenv('BLUESKY_UMBRAL_REPORTE', '0.60'))
BLUESKY_INTERVALO = int(os.getenv('BLUESKY_INTERVALO', '15'))
BLUESKY_CUENTAS_VIGILADAS = [
    c.strip().lstrip('@')
    for c in os.getenv('BLUESKY_CUENTAS_VIGILADAS', '').split(',')
    if c.strip()
]
BLUESKY_VIGILANCIA_JSON = DATA_DIR / 'vigilancia_bluesky.json'

# Artefactos de modelos
CLASSIC_MODEL_PATH = MODELS_DIR / 'classic_model.joblib'
CLASSIC_METRICS_PATH = MODELS_DIR / 'classic_metrics.json'
ROBERTA_FINETUNED_DIR = MODELS_DIR / 'roberta_finetuned'

PRETRAINED_DIR = MODELS_DIR / 'pretrained'


def _local_or_hub(repo_id: str) -> str:
  """Usa la copia descargada en models/pretrained/ si está completa."""
  local = PRETRAINED_DIR / repo_id.split('/')[-1]
  return str(local) if (local / '.complete').exists() else repo_id


# RoBERTuito: RoBERTa preentrenado con tweets en español
ROBERTA_BASE_MODEL = os.getenv(
    'ROBERTA_BASE_MODEL', _local_or_hub('pysentimiento/robertuito-base-uncased')
)
# Modelo de respaldo cuando aún no existe el fine-tuning propio
ROBERTA_ZERO_SHOT_MODEL = os.getenv(
    'ROBERTA_ZERO_SHOT_MODEL', _local_or_hub('pysentimiento/robertuito-hate-speech')
)
ROBERTA_ENABLED = os.getenv('ROBERTA_ENABLED', '1') == '1'
ROBERTA_MAX_LENGTH = 128

CATEGORIES = {
    0: 'Sin ciberacoso',
    1: 'Hostigamiento y amenazas directas',
    2: 'Insultos y ofensas personales',
    3: 'Incitación al odio y muerte',
    4: 'Difamación, calumnia y ataques políticos',
}
CATEGORY_SHORT = {
    0: 'Seguro',
    1: 'Amenaza',
    2: 'Insulto',
    3: 'Odio/Muerte',
    4: 'Calumnia',
}

# --- Cascada clásico -> RoBERTa ---
# Confianza mínima para sancionar automáticamente
CONFIDENCE_THRESHOLD = float(os.getenv('CONFIDENCE_THRESHOLD', '0.70'))
# Banda alrededor del umbral binario donde el modelo clásico "duda"
UNCERTAINTY_MARGIN = float(os.getenv('UNCERTAINTY_MARGIN', '0.20'))
# F1 de validación por debajo del cual una clase se considera poco fiable
MIN_CLASS_F1 = float(os.getenv('MIN_CLASS_F1', '0.60'))
# Peso de RoBERTa al fusionar probabilidades
ROBERTA_WEIGHT = float(os.getenv('ROBERTA_WEIGHT', '0.70'))

RANDOM_STATE = 42
