import os
import joblib
from src.preprocessing import clean_text


class CyberbullyingDetector:

  def __init__(
      self, models_dir: str = 'models', confidence_threshold: float = 0.70
  ):
    """Carga los modelos binario y multiclase junto al vectorizador TF-IDF.

    Args:
        models_dir: Carpeta contenedora de los artefactos .pkl
        confidence_threshold: Umbral de confianza mínimo (0.70 = 70%) para
          sanción automática.
    """
    vectorizer_path = os.path.join(models_dir, 'tfidf_vectorizer.pkl')
    binary_path = os.path.join(models_dir, 'binary_model.pkl')
    severity_path = os.path.join(models_dir, 'severity_model.pkl')

    if (
        not os.path.exists(vectorizer_path)
        or not os.path.exists(binary_path)
        or not os.path.exists(severity_path)
    ):
      raise FileNotFoundError(
          
      )

    self.vectorizer = joblib.load(vectorizer_path)
    self.binary_model = joblib.load(binary_path)
    self.severity_model = joblib.load(severity_path)
    self.threshold = confidence_threshold

  def predict(self, text: str) -> dict:
    cleaned = clean_text(text)

    if not cleaned:
      return {
          'texto_original': text,
          'es_ciberacoso': False,
          'categoria': 0,
          'confianza': 1.0,
          'notificar_admin': False,
          'accion_sugerida': 'NINGUNA',
      }

    # 1. Transformar texto
    text_tfidf = self.vectorizer.transform([cleaned])

    # 2. Etapa 1: Predicción Binaria
    is_cyberbullying = self.binary_model.predict(text_tfidf)[0] == 1
    prob_binary = float(self.binary_model.predict_proba(text_tfidf)[0][1])

    # Si es un mensaje normal
    if not is_cyberbullying:
      return {
          'texto_original': text,
          'texto_limpio': cleaned,
          'es_ciberacoso': False,
          'categoria': 0,
          'confianza': round(1.0 - prob_binary, 4),
          'notificar_admin': False,
          'accion_sugerida': 'PERMITIR_MENSAJE',
      }

    # 3. Etapa 2: Si es ciberacoso, evaluar Categoría de Gravedad
    category = int(self.severity_model.predict(text_tfidf)[0])
    prob_category = float(
        max(self.severity_model.predict_proba(text_tfidf)[0])
    )

    # Confianza general combinada
    confianza_final = round((prob_binary + prob_category) / 2, 4)

    # Evaluación de umbral para el Admin de Discord
    requires_admin = confianza_final < self.threshold

    accion = 'REVISAR_POR_ADMIN' if requires_admin else f'SANCTION_CAT_{category}'

    return {
        'texto_original': text,
        'texto_limpio': cleaned,
        'es_ciberacoso': True,
        'categoria_gravedad': category,
        'confianza': confianza_final,
        'notificar_admin': requires_admin,
        'accion_sugerida': accion,
    }


if __name__ == '__main__':
  detector = CyberbullyingDetector(confidence_threshold=0.70)

  test_msgs = [
      'Hola a todos, ¿cómo van hoy?',
      'Eres un inútil de mierda',
      'S4P4 HIJ0 D3 PUT4',
      'Ojalá te mueras desgraciado',
  ]

  for msg in test_msgs:
    res = detector.predict(msg)
    print(f'Mensaje: "{res["texto_original"]}"')
    print(
        f'Acoso: {res["es_ciberacoso"]} | Categoria: {res.get("categoria_gravedad", 0)}'
    )
    print(
        f'Confianza: {res["confianza"]*100:.1f}% | Notificar Admin:'
        f' {res["notificar_admin"]}'
    )
    print(f'Acción: {res["accion_sugerida"]}\n' + '-' * 50)