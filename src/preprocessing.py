import os
import re
import pandas as pd

LEET_DICT = {
    '4': 'a',
    '@': 'a',
    '3': 'e',
    '1': 'i',
    '!': 'i',
    '0': 'o',
    '5': 's',
    '$': 's',
    '7': 't',
}


def decode_leetspeak(text: str) -> str:
  for leet, char in LEET_DICT.items():
    text = text.replace(leet, char)
  return text


def clean_text(text: str) -> str:
  if not isinstance(text, str):
    return ''

  text = text.lower()
  text = decode_leetspeak(text)
  text = re.sub(r'(.)\1{2,}', r'\1\1', text)
  text = re.sub(r'https?://\S+|www\.\S+', '', text)
  text = re.sub(r'@\w+', '', text)
  text = re.sub(r'#(\w+)', r'\1', text)
  text = re.sub(r'[\r\n\t]+', ' ', text)
  text = re.sub(r'\d+', '', text)
  text = re.sub(r'[^a-záéíóúñü\s]', ' ', text)
  text = re.sub(r'\s+', ' ', text).strip()
  return text


def prepare_datasets(
    colombia_path: str = 'data/raw/colombian_cyberbullying.csv',
    corpus_path: str = 'data/raw/CorpusBullying.csv',
    refuerzo_path: str = 'data/raw/refuerzo_categorias.csv',
    out_binary_path: str = 'data/processed/stage1_binary.csv',
    out_categories_path: str = 'data/processed/stage2_categories.csv',
):
  # ----------------------------------------------------
  # DATASET 1: ETAPA 1 (Binario Masivo)
  # ----------------------------------------------------
  print('--> Generando Dataset para Etapa 1 (Filtro Binario)...')
  df_col = pd.read_csv(colombia_path).dropna(subset=['ciberacoso', 'texto'])
  df_col_bin = df_col[['texto', 'ciberacoso']].rename(
      columns={'texto': 'text'}
  )
  df_col_bin['ciberacoso'] = df_col_bin['ciberacoso'].astype(int)

  df_corp = pd.read_csv(corpus_path, sep=';').dropna(
      subset=['SpanishTweet', 'Label']
  )
  df_corp_bin = df_corp[['SpanishTweet', 'Label']].rename(
      columns={'SpanishTweet': 'text', 'Label': 'ciberacoso'}
  )
  df_corp_bin['ciberacoso'] = df_corp_bin['ciberacoso'].astype(int)

  # Muestreo balanceado de la clase negativa de Corpus
  positives_corp = df_corp_bin[df_corp_bin['ciberacoso'] == 1]
  negatives_corp = df_corp_bin[df_corp_bin['ciberacoso'] == 0].sample(
      n=6000, random_state=42
  )

  df_merged_bin = pd.concat(
      [df_col_bin, positives_corp, negatives_corp], ignore_index=True
  )
  df_merged_bin['texto_limpio'] = df_merged_bin['text'].apply(clean_text)
  df_merged_bin = df_merged_bin[
      df_merged_bin['texto_limpio'] != ''
  ].drop_duplicates(subset=['texto_limpio'])

  os.makedirs(os.path.dirname(out_binary_path), exist_ok=True)
  df_merged_bin[['texto_limpio', 'ciberacoso']].to_csv(
      out_binary_path, index=False, encoding='utf-8'
  )

  # ----------------------------------------------------
  # DATASET 2: ETAPA 2 (Categorías Controladas + Refuerzo)
  # ----------------------------------------------------
  print('--> Generando Dataset para Etapa 2 (Gravedad/Categorías)...')
  df_col_cat = df_col.copy()
  df_col_cat['categoria'] = (
      df_col_cat['categoria'].replace({'o': '0'}).fillna(0).astype(int)
  )

  # Si existe archivo de refuerzo manual, lo sumamos
  if os.path.exists(refuerzo_path):
    print(f'   - Anexando refuerzos manuales desde: {refuerzo_path}')
    df_ref = pd.read_csv(refuerzo_path)
    df_ref['ciberacoso'] = 1  # Por definición son acoso
    df_col_cat = pd.concat([df_col_cat, df_ref], ignore_index=True)

  df_col_cat['texto_limpio'] = df_col_cat['texto'].apply(clean_text)
  df_col_cat = df_col_cat[df_col_cat['texto_limpio'] != ''].drop_duplicates(
      subset=['texto_limpio']
  )

  df_col_cat[['texto_limpio', 'ciberacoso', 'categoria']].to_csv(
      out_categories_path, index=False, encoding='utf-8'
  )

  print('\n Procesamiento finalizado:')
  print(
      f'   - Etapa 1 (Binario)    : {len(df_merged_bin)} muestras en'
      f' "{out_binary_path}"'
  )
  print(
      f'   - Etapa 2 (Categorías) : {len(df_col_cat)} muestras en'
      f' "{out_categories_path}"'
  )


if __name__ == '__main__':
  prepare_datasets()