"""Fine-tuning de RoBERTuito para las 5 categorías (0-4).

Uso:
    python -m src.train_transformer --epochs 4 --batch-size 16

En CPU tarda bastante (decenas de minutos por época). Si tienes acceso a una
GPU (por ejemplo Google Colab), el mismo script la usa automáticamente.
"""

import argparse
from datetime import datetime
import json
import random

import numpy as np
import pandas as pd
from sklearn.metrics import classification_report, f1_score
from sklearn.model_selection import train_test_split
from sklearn.utils.class_weight import compute_class_weight

from src import config
from src.data import build_category_dataset, load_corpus
from src.preprocessing import clean_text, preprocess_for_transformer


def _set_seed(seed: int):
  import torch

  random.seed(seed)
  np.random.seed(seed)
  torch.manual_seed(seed)


def build_dataset(n_corpus_negatives: int) -> pd.DataFrame:
  df = build_category_dataset()
  if n_corpus_negatives > 0:
    # Ejemplos seguros extra de CorpusBullying para que el modelo vea más
    # lenguaje cotidiano (sus positivos no tienen categoría y se excluyen)
    neg = load_corpus(n_corpus_negatives)
    neg = neg[neg['ciberacoso'] == 0].copy()
    neg['categoria'] = 0
    neg['texto_limpio'] = neg['texto'].map(clean_text)
    neg = neg[~neg['texto_limpio'].isin(df['texto_limpio'])]
    df = pd.concat([df, neg], ignore_index=True)
  df['categoria'] = df['categoria'].astype(int)
  return df


def _batches(tokenizer, encodings, labels, batch_size, shuffle):
  """Padding dinámico por lote: mucho más rápido en CPU que padding global."""
  import torch

  idx = np.arange(len(labels))
  if shuffle:
    np.random.shuffle(idx)
  for start in range(0, len(idx), batch_size):
    b = idx[start:start + batch_size]
    features = [{k: encodings[k][i] for k in encodings.keys()} for i in b]
    yield (
        dict(tokenizer.pad(features, return_tensors='pt')),
        torch.as_tensor(labels[b], dtype=torch.long),
    )


def _evaluate(model, tokenizer, encodings, labels, batch_size, device):
  import torch

  model.eval()
  preds = []
  with torch.no_grad():
    for batch, _ in _batches(tokenizer, encodings, labels, batch_size, shuffle=False):
      batch = {k: v.to(device) for k, v in batch.items()}
      preds.append(model(**batch).logits.argmax(-1).cpu().numpy())
  return np.concatenate(preds)


def train_transformer(
    base_model: str = config.ROBERTA_BASE_MODEL,
    epochs: int = 4,
    batch_size: int = 16,
    lr: float = 3e-5,
    max_length: int = config.ROBERTA_MAX_LENGTH,
    n_corpus_negatives: int = 1500,
    limit: int | None = None,
    output_dir=config.ROBERTA_FINETUNED_DIR,
):
  import torch
  from transformers import (
      AutoModelForSequenceClassification,
      AutoTokenizer,
      get_linear_schedule_with_warmup,
  )

  _set_seed(config.RANDOM_STATE)
  device = 'cuda' if torch.cuda.is_available() else 'cpu'
  print(f'--> Dispositivo: {device}')

  df = build_dataset(n_corpus_negatives)
  if limit:
    per_class = max(2, limit // 5)
    df = pd.concat([
        g.sample(min(len(g), per_class), random_state=config.RANDOM_STATE)
        for _, g in df.groupby('categoria')
    ], ignore_index=True)
  print('--> Distribución de categorías:')
  print(df['categoria'].value_counts().sort_index().to_string())

  train_df, val_df = train_test_split(
      df, test_size=0.15, random_state=config.RANDOM_STATE, stratify=df['categoria']
  )

  tokenizer = AutoTokenizer.from_pretrained(base_model)
  model = AutoModelForSequenceClassification.from_pretrained(
      base_model,
      num_labels=5,
      id2label={i: config.CATEGORY_SHORT[i] for i in range(5)},
      label2id={config.CATEGORY_SHORT[i]: i for i in range(5)},
  ).to(device)

  def encode(texts):
    return tokenizer(
        [preprocess_for_transformer(t) for t in texts],
        truncation=True,
        max_length=max_length,
    )

  enc_tr, y_tr = encode(train_df['texto']), train_df['categoria'].to_numpy()
  enc_va, y_va = encode(val_df['texto']), val_df['categoria'].to_numpy()

  # Pesos por clase: las categorías 1 y 3 tienen pocos ejemplos
  weights = compute_class_weight('balanced', classes=np.arange(5), y=y_tr)
  loss_fn = torch.nn.CrossEntropyLoss(
      weight=torch.as_tensor(weights, dtype=torch.float, device=device)
  )
  optimizer = torch.optim.AdamW(model.parameters(), lr=lr, weight_decay=0.01)
  steps = epochs * int(np.ceil(len(y_tr) / batch_size))
  scheduler = get_linear_schedule_with_warmup(optimizer, int(0.1 * steps), steps)

  best_f1, best_report = -1.0, None
  for epoch in range(1, epochs + 1):
    model.train()
    total_loss = 0.0
    n_batches = int(np.ceil(len(y_tr) / batch_size))
    for i, (batch, labels) in enumerate(
        _batches(tokenizer, enc_tr, y_tr, batch_size, shuffle=True), start=1
    ):
      batch = {k: v.to(device) for k, v in batch.items()}
      loss = loss_fn(model(**batch).logits, labels.to(device))
      loss.backward()
      torch.nn.utils.clip_grad_norm_(model.parameters(), 1.0)
      optimizer.step()
      scheduler.step()
      optimizer.zero_grad()
      total_loss += loss.item()
      if i % 20 == 0 or i == n_batches:
        print(f'   época {epoch} lote {i}/{n_batches} loss={total_loss / i:.4f}', flush=True)

    preds = _evaluate(model, tokenizer, enc_va, y_va, batch_size * 2, device)
    macro_f1 = f1_score(y_va, preds, average='macro')
    print(f'--> Época {epoch}: F1 macro validación = {macro_f1:.4f}')
    if macro_f1 > best_f1:
      best_f1 = macro_f1
      best_report = classification_report(
          y_va, preds, labels=list(range(5)), output_dict=True, zero_division=0
      )
      output_dir.mkdir(parents=True, exist_ok=True)
      model.save_pretrained(output_dir)
      tokenizer.save_pretrained(output_dir)
      print(f'   Mejor modelo guardado en "{output_dir}"')

  metrics = {
      'entrenado_en': datetime.now().isoformat(timespec='seconds'),
      'modelo_base': base_model,
      'f1_macro': best_f1,
      'f1_por_clase': {
          str(c): best_report[str(c)]['f1-score'] for c in range(5)
      },
      'n_train': int(len(y_tr)),
      'n_val': int(len(y_va)),
  }
  (output_dir / 'metrics.json').write_text(
      json.dumps(metrics, indent=2, ensure_ascii=False), encoding='utf-8'
  )
  print(json.dumps(metrics, indent=2, ensure_ascii=False))
  return metrics


def main(argv=None):
  parser = argparse.ArgumentParser(description=__doc__)
  parser.add_argument('--base-model', default=config.ROBERTA_BASE_MODEL)
  parser.add_argument('--epochs', type=int, default=4)
  parser.add_argument('--batch-size', type=int, default=16)
  parser.add_argument('--lr', type=float, default=3e-5)
  parser.add_argument('--corpus-negatives', type=int, default=1500)
  parser.add_argument(
      '--limit', type=int, default=None,
      help='Usa sólo N ejemplos (prueba rápida del pipeline).',
  )
  args = parser.parse_args(argv)
  train_transformer(
      base_model=args.base_model,
      epochs=args.epochs,
      batch_size=args.batch_size,
      lr=args.lr,
      n_corpus_negatives=args.corpus_negatives,
      limit=args.limit,
  )


if __name__ == '__main__':
  main()
