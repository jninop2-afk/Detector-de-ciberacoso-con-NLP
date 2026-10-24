"""Clasificador RoBERTa (RoBERTuito) usado como segunda opinión.

Modos de funcionamiento:
  - 'finetuned': modelo propio en models/roberta_finetuned (5 categorías),
    generado con src/train_transformer.py. Es el modo recomendado.
  - 'zero_shot': si aún no existe el modelo propio, usa
    pysentimiento/robertuito-hate-speech para estimar sólo la probabilidad
    de ciberacoso (no la categoría).
"""

import threading

from src import config
from src.preprocessing import preprocess_for_transformer


class RobertaClassifier:

  def __init__(
      self,
      finetuned_dir=config.ROBERTA_FINETUNED_DIR,
      zero_shot_model: str = config.ROBERTA_ZERO_SHOT_MODEL,
      max_length: int = config.ROBERTA_MAX_LENGTH,
  ):
    self.finetuned_dir = finetuned_dir
    self.zero_shot_model = zero_shot_model
    self.max_length = max_length
    self.mode = (
        'finetuned' if (finetuned_dir / 'config.json').exists() else 'zero_shot'
    )
    self._model = None
    self._tokenizer = None
    self._lock = threading.Lock()

  def _load(self):
    # Importación diferida: torch tarda en cargar y es opcional
    import torch
    from transformers import AutoModelForSequenceClassification, AutoTokenizer

    source = (
        str(self.finetuned_dir) if self.mode == 'finetuned' else self.zero_shot_model
    )
    self._torch = torch
    self._tokenizer = AutoTokenizer.from_pretrained(source)
    self._model = AutoModelForSequenceClassification.from_pretrained(source)
    self._model.eval()
    self._id2label = {int(k): v for k, v in self._model.config.id2label.items()}

  def ensure_loaded(self):
    with self._lock:
      if self._model is None:
        self._load()

  def predict(self, text: str) -> dict:
    """Devuelve prob_ciberacoso y, en modo finetuned, la distribución 0-4."""
    self.ensure_loaded()
    torch = self._torch
    inputs = self._tokenizer(
        preprocess_for_transformer(text),
        truncation=True,
        max_length=self.max_length,
        return_tensors='pt',
    )
    with self._lock, torch.no_grad():
      logits = self._model(**inputs).logits[0]

    if self.mode == 'finetuned':
      # Los ids del modelo propio coinciden con las categorías 0-4
      probs = torch.softmax(logits, dim=-1).tolist()
      dist = {c: float(probs[c]) for c in range(len(probs))}
      return {
          'modo': self.mode,
          'prob_ciberacoso': 1.0 - dist[0],
          'probabilidades': dist,
      }

    # zero_shot: etiquetas multietiqueta (hateful, targeted, aggressive)
    scores = torch.sigmoid(logits).tolist()
    by_label = {self._id2label[i]: s for i, s in enumerate(scores)}
    prob = max(by_label.get('hateful', 0.0), by_label.get('aggressive', 0.0))
    return {
        'modo': self.mode,
        'prob_ciberacoso': float(prob),
        'probabilidades': None,
        'detalle': by_label,
    }
