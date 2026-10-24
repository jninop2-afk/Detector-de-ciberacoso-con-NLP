import os
import joblib
import nltk
import pandas as pd
from nltk.corpus import stopwords
from sklearn.feature_extraction.text import TfidfVectorizer
from sklearn.linear_model import LogisticRegression
from sklearn.metrics import classification_report
from sklearn.model_selection import train_test_split
from sklearn.pipeline import FeatureUnion

try:
  nltk.data.find('corpora/stopwords')
except LookupError:
  nltk.download('stopwords')


def build_robust_vectorizer(spanish_stopwords: list) -> FeatureUnion:
  word_vec = TfidfVectorizer(
      stop_words=spanish_stopwords,
      analyzer='word',
      ngram_range=(1, 2),
      max_features=5000,
  )
  char_vec = TfidfVectorizer(
      analyzer='char_wb', ngram_range=(3, 5), max_features=5000
  )
  return FeatureUnion([('word', word_vec), ('char', char_vec)])


def train_pipeline(
    binary_data_path: str = 'data/processed/stage1_binary.csv',
    categories_data_path: str = 'data/processed/stage2_categories.csv',
    models_dir: str = 'models',
):
  spanish_stopwords = stopwords.words('spanish')

  # ==========================================
  # ETAPA 1: Detector Binario Masivo
  # ==========================================
  print('--> [ETAPA 1] Entrenando Detector Binario Masivo...')
  df_bin = pd.read_csv(binary_data_path).dropna(subset=['texto_limpio'])

  vectorizer = build_robust_vectorizer(spanish_stopwords)
  X_bin_tfidf = vectorizer.fit_transform(df_bin['texto_limpio'])
  y_bin = df_bin['ciberacoso']

  X_tr_b, X_te_b, y_tr_b, y_te_b = train_test_split(
      X_bin_tfidf, y_bin, test_size=0.20, random_state=42, stratify=y_bin
  )

  binary_model = LogisticRegression(
      max_iter=1000, class_weight='balanced', random_state=42
  )
  binary_model.fit(X_tr_b, y_tr_b)

  print('\n[Reporte de Evaluación - Modelo Binario (Etapa 1)]')
  print(
      classification_report(
          y_te_b,
          binary_model.predict(X_te_b),
          target_names=['Seguro', 'Ciberacoso'],
      )
  )

  # ==========================================
  # ETAPA 2: Clasificador de Gravedad (Categorías)
  # ==========================================
  print('--> [ETAPA 2] Entrenando Clasificador de Gravedad...')
  df_cat = pd.read_csv(categories_data_path).dropna(subset=['texto_limpio'])
  df_acoso = df_cat[df_cat['ciberacoso'] == 1]

  X_acoso_tfidf = vectorizer.transform(df_acoso['texto_limpio'])
  y_severity = df_acoso['categoria']

  X_tr_s, X_te_s, y_tr_s, y_te_s = train_test_split(
      X_acoso_tfidf,
      y_severity,
      test_size=0.20,
      random_state=42,
      stratify=y_severity,
  )

  severity_model = LogisticRegression(
      max_iter=1000, class_weight='balanced', random_state=42
  )
  severity_model.fit(X_tr_s, y_tr_s)

  print('\n[Reporte de Evaluación - Gravedad/Categorías (Etapa 2)]')
  print(classification_report(y_te_s, severity_model.predict(X_te_s)))

  # Exportar Artefactos
  os.makedirs(models_dir, exist_ok=True)
  joblib.dump(
      vectorizer, os.path.join(models_dir, 'tfidf_vectorizer.pkl')
  )
  joblib.dump(
      binary_model, os.path.join(models_dir, 'binary_model.pkl')
  )
  joblib.dump(
      severity_model, os.path.join(models_dir, 'severity_model.pkl')
  )

  print(f'\n Modelos entrenados y exportados a "{models_dir}/".')


if __name__ == '__main__':
  train_pipeline()