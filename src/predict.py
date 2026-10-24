"""Detector híbrido de ciberacoso: modelo clásico + RoBERTa en cascada.

El modelo clásico (rápido) analiza todos los mensajes. RoBERTa (lento pero
más preciso con el contexto) sólo se ejecuta cuando el clásico tiene
"sospechas":
  - la probabilidad binaria cae cerca del umbral de decisión,
  - la categoría predicha tiene confianza baja,
  - la categoría predicha tiene F1 de validación bajo (métricas pobres),
  - el clásico dice "seguro" pero hay patrones de amenaza/odio explícitos.
"""

import logging

import joblib
import numpy as np

from src import config
from src.features import lexicon_signals
from src.preprocessing import clean_text

log = logging.getLogger(__name__)


class CyberbullyingDetector:

  def __init__(
      self,
      model_path=config.CLASSIC_MODEL_PATH,
      confidence_threshold: float = config.CONFIDENCE_THRESHOLD,
      use_roberta: bool = config.ROBERTA_ENABLED,
  ):
    if not model_path.exists():
      raise FileNotFoundError(
          f'No existe "{model_path}". Entrena primero con: python main.py train'
      )
    artifact = joblib.load(model_path)
    self.binary = artifact['binary_pipeline']
    self.severity = artifact['severity_pipeline']
    self.binary_threshold = artifact['binary_threshold']
    self.metrics = artifact['metrics']
    self.threshold = confidence_threshold
    self.severity_classes = [int(c) for c in self.severity.classes_]

    self.binary_f1 = self.metrics['binario']['f1_ciberacoso']
    self.class_f1 = {
        int(c): f for c, f in self.metrics['gravedad']['f1_por_clase'].items()
    }

    self.roberta = None
    if use_roberta:
      try:
        from src.transformer import RobertaClassifier

        self.roberta = RobertaClassifier()
      except ImportError as err:
        log.warning('RoBERTa deshabilitado (falta dependencia): %s', err)

  @property
  def roberta_mode(self) -> str:
    return self.roberta.mode if self.roberta else 'deshabilitado'

  def warmup(self):
    """Carga RoBERTa por adelantado para que el primer mensaje no espere."""
    if self.roberta:
      try:
        self.roberta.ensure_loaded()
      except Exception as err:
        log.error('No se pudo cargar RoBERTa, se usará sólo el clásico: %s', err)
        self.roberta = None

  # ------------------------------------------------------------------
  # Modelo clásico
  # ------------------------------------------------------------------
  def _classic(self, text: str) -> dict:
    p_bully = float(self.binary.predict_proba([text])[0][1])
    cond = self.severity.predict_proba([text])[0]
    cond_dist = {c: float(p) for c, p in zip(self.severity_classes, cond)}
    # Distribución completa 0-4: P(0) = 1 - p, P(k) = p * P(k | acoso)
    dist = {0: 1.0 - p_bully}
    dist.update({c: p_bully * cond_dist.get(c, 0.0) for c in range(1, 5)})
    return {'prob_ciberacoso': p_bully, 'condicional': cond_dist, 'dist': dist}

  def _suspicion_reasons(self, classic: dict, signals: dict) -> list[str]:
    reasons = []
    p = classic['prob_ciberacoso']
    is_bully = p >= self.binary_threshold
    category = max(classic['condicional'], key=classic['condicional'].get)
    cat_conf = classic['condicional'][category]

    if abs(p - self.binary_threshold) < config.UNCERTAINTY_MARGIN:
      reasons.append(f'probabilidad {p:.2f} cercana al umbral {self.binary_threshold:.2f}')
    if self.binary_f1 < config.MIN_CLASS_F1:
      reasons.append(f'F1 binario bajo ({self.binary_f1:.2f})')
    if is_bully:
      overall = (p + cat_conf) / 2
      if cat_conf < self.threshold:
        reasons.append(f'categoría {category} con confianza baja ({cat_conf:.2f})')
      elif overall < self.threshold:
        reasons.append(f'confianza global baja ({overall:.2f})')
      f1 = self.class_f1.get(category, 0.0)
      if f1 < config.MIN_CLASS_F1:
        reasons.append(f'categoría {category} con F1 de validación bajo ({f1:.2f})')
    elif signals['amenazas'] or signals['odio_muerte']:
      reasons.append('patrones de amenaza/odio pese a predicción segura')
    return reasons

  # ------------------------------------------------------------------
  # Predicción híbrida
  # ------------------------------------------------------------------
  def predict(self, text: str) -> dict:
    cleaned = clean_text(text)
    if not cleaned:
      return self._result(text, cleaned, {0: 1.0}, 'clasico', [], False)

    classic = self._classic(text)
    signals = lexicon_signals(text)
    reasons = self._suspicion_reasons(classic, signals)

    dist = classic['dist']
    engine = 'clasico'
    roberta_out = None
    disagreement = False

    if reasons and self.roberta is not None:
      try:
        roberta_out = self.roberta.predict(text)
      except Exception as err:
        log.error('Fallo en RoBERTa, se usa el clásico: %s', err)
        reasons.append('RoBERTa no disponible')

    if roberta_out is not None:
      engine = f'roberta_{roberta_out["modo"]}'
      w = config.ROBERTA_WEIGHT
      if roberta_out['probabilidades'] is not None:
        dist = {
            c: w * roberta_out['probabilidades'].get(c, 0.0) + (1 - w) * dist[c]
            for c in range(5)
        }
      else:
        # Zero-shot: RoBERTa sólo aporta la probabilidad binaria; la
        # categoría se toma del clásico
        p = w * roberta_out['prob_ciberacoso'] + (1 - w) * classic['prob_ciberacoso']
        dist = {0: 1.0 - p}
        dist.update({c: p * classic['condicional'].get(c, 0.0) for c in range(1, 5)})
      classic_bully = classic['prob_ciberacoso'] >= self.binary_threshold
      roberta_bully = roberta_out['prob_ciberacoso'] >= 0.5
      disagreement = classic_bully != roberta_bully
      decision_threshold = 0.5
    else:
      decision_threshold = self.binary_threshold

    return self._result(
        text, cleaned, dist, engine, reasons, disagreement,
        decision_threshold=decision_threshold,
        classic=classic, roberta=roberta_out,
    )

  def _result(
      self, text, cleaned, dist, engine, reasons, disagreement,
      decision_threshold=0.5, classic=None, roberta=None,
  ) -> dict:
    dist = {c: float(dist.get(c, 0.0)) for c in range(5)}
    p_bully = 1.0 - dist[0]
    is_bully = p_bully >= decision_threshold

    if is_bully:
      category = max(range(1, 5), key=lambda c: dist[c])
      cat_conf = dist[category] / p_bully if p_bully > 0 else 0.0
      confidence = (p_bully + cat_conf) / 2
    else:
      category, cat_conf = 0, 1.0
      confidence = 1.0 - p_bully

    # Sin RoBERTa disponible, las sospechas del clásico van al admin
    unresolved = bool(reasons) and roberta is None
    needs_admin = is_bully and (
        confidence < self.threshold or disagreement or unresolved
    )
    # Un "seguro" con amenaza explícita que nadie pudo confirmar también se revisa
    if not is_bully and disagreement:
      needs_admin = True

    if needs_admin:
      action = 'REVISAR_POR_ADMIN'
    elif is_bully:
      action = 'SANCIONAR'
    else:
      action = 'PERMITIR_MENSAJE'

    return {
        'texto_original': text,
        'texto_limpio': cleaned,
        'es_ciberacoso': bool(is_bully),
        'categoria': int(category),
        'categoria_gravedad': int(category),
        'categoria_nombre': config.CATEGORIES[category],
        'prob_ciberacoso': round(p_bully, 4),
        'confianza': round(float(confidence), 4),
        'confianza_categoria': round(float(cat_conf), 4),
        'probabilidades': {c: round(p, 4) for c, p in dist.items()},
        'motor': engine,
        'motivos_sospecha': reasons,
        'desacuerdo_modelos': disagreement,
        'prob_clasico': round(classic['prob_ciberacoso'], 4) if classic else None,
        'prob_roberta': round(roberta['prob_ciberacoso'], 4) if roberta else None,
        'notificar_admin': bool(needs_admin),
        'accion_sugerida': action,
    }

  def predict_classic_batch(self, texts) -> dict:
    """Predicción vectorizada sólo con el clásico (para etiquetado masivo)."""
    p_bully = self.binary.predict_proba(texts)[:, 1]
    cond = self.severity.predict_proba(texts)
    categories = np.asarray(self.severity_classes)[cond.argmax(axis=1)]
    is_bully = p_bully >= self.binary_threshold
    return {
        'prob_ciberacoso': p_bully,
        'es_ciberacoso': is_bully,
        'categoria': np.where(is_bully, categories, 0),
        'confianza_categoria': cond.max(axis=1),
    }


if __name__ == '__main__':
  detector = CyberbullyingDetector()
  for msg in [
      'Hola a todos, ¿cómo van hoy?',
      'Eres un inútil de mierda',
      'S4P4 HIJ0 D3 PUT4',
      'Ojalá te mueras desgraciado',
  ]:
    res = detector.predict(msg)
    print(f'"{msg}" -> {res["categoria_nombre"]} ({res["confianza"]:.2f}) '
          f'[{res["motor"]}] {res["accion_sugerida"]}')
