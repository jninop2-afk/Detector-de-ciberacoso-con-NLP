"""Rasgos lingüísticos manuales que complementan TF-IDF.

TF-IDF captura palabras y fragmentos, pero no "entiende" que un insulto va
dirigido a alguien o que una frase es una amenaza. Estos rasgos codifican
ese conocimiento del dominio de forma explícita.
"""

import re

import numpy as np
from sklearn.base import BaseEstimator, TransformerMixin

from src.preprocessing import clean_text

INSULT_LEXICON = {
    'hijueputa', 'gonorrea', 'malparido', 'maricon', 'huevon', 'pirobo',
    'mierda', 'verga', 'puta', 'perra', 'perro', 'estupido', 'idiota',
    'imbecil', 'malnacido', 'sapo', 'inutil', 'basura', 'asqueroso',
    'asquerosa', 'bruto', 'bruta', 'tonto', 'tonta', 'feo', 'fea', 'gordo',
    'gorda', 'mamarracho', 'lambon', 'zorra', 'ramera', 'cerdo', 'cerda',
    'rata', 'animal', 'retrasado', 'retrasada', 'mongolico', 'subnormal',
    'pendejo', 'pendeja', 'cabron', 'cabrona', 'payaso', 'ridiculo',
    'ridicula', 'analfabeta', 'ignorante', 'parasito', 'lacra', 'escoria',
    'careverga', 'carechimba', 'gamin', 'guisa', 'loca', 'enfermo',
    'desgraciado', 'desgraciada', 'maldito', 'maldita', 'lameculos',
}

DEFAMATION_LEXICON = {
    'ladron', 'ladrones', 'corrupto', 'corrupta', 'corruptos', 'asesino',
    'asesina', 'asesinos', 'criminal', 'delincuente', 'narco', 'narcotraficante',
    'guerrillero', 'paramilitar', 'terrorista', 'mentiroso', 'mentirosa',
    'estafador', 'violador', 'pedofilo', 'robo', 'robando', 'robaron',
    'presidente', 'senador', 'senadora', 'congresista', 'alcalde',
    'alcaldesa', 'gobierno', 'petro', 'uribe', 'fiscal', 'ministro',
    'ministra', 'comisionista', 'politico', 'politicos', 'tinterillo',
}

SECOND_PERSON = {
    'tu', 'te', 'ti', 'tus', 'contigo', 'usted', 'ustedes', 'vos', 'eres',
    'sos', 'estas', 'tenes', 'tienes', 'vas', 'usuario',
}

THREAT_PATTERNS = re.compile(
    r'\b(te|lo|la|los|las|les) (voy|vamos) a (matar|buscar|partir|romper|'
    r'quebrar|violar|encontrar|cascar|joder|reventar|chuzar|levantar|'
    r'desaparecer|publicar|quemar|picar|dar)'
    r'|\b(vas|van) a (morir|ver|pagar|llorar|sufrir|aparecer)'
    r'|\bya (se|sabemos|se donde)\b.*\b(vives|estudias|trabajas)'
    r'|\bse donde (vives|estudias|trabajas)'
    r'|\bcuidate\b|\bte tengo (fichado|fichada|en la mira)'
    r'|\bpepazo|\bplomo\b|\bbala\b|\bdar(te|le) (en la|un) (jeta|mano|tiro)'
    r'|\bpublicar (tus|sus) fotos'
)

HATE_DEATH_PATTERNS = re.compile(
    r'\bojala (te|se|le|les|lo|la|los|las) (muera|mueras|mueran|maten|'
    r'violen|pase|pudras|pudra)'
    r'|\b(matate|suicidate|tirate|arrojese|arrojate|ahorcate|muerete|'
    r'muerase|pegate un tiro)'
    r'|\b(deberian|merecen|hay que) (matar|morir|desaparecer|exterminar|'
    r'quemar|fusilar)'
    r'|\bmuerte a\b|\bnadie te quiere\b|\bno mereces vivir\b'
    r'|\bplaga\b|\bexterminar|\blimpieza social'
)


def lexicon_signals(text: str) -> dict:
  """Cuenta señales léxicas sobre el texto normalizado."""
  cleaned = clean_text(text)
  tokens = cleaned.split()
  return {
      'insultos': sum(t in INSULT_LEXICON for t in tokens),
      'difamacion': sum(t in DEFAMATION_LEXICON for t in tokens),
      'segunda_persona': sum(t in SECOND_PERSON for t in tokens),
      'amenazas': len(THREAT_PATTERNS.findall(cleaned)),
      'odio_muerte': len(HATE_DEATH_PATTERNS.findall(cleaned)),
      'n_tokens': len(tokens),
  }


class LexiconFeatures(BaseEstimator, TransformerMixin):
  """Transformer de sklearn que recibe texto crudo y devuelve rasgos densos."""

  feature_names = [
      'insultos', 'difamacion', 'segunda_persona', 'amenazas',
      'odio_muerte', 'insulto_dirigido', 'ratio_mayusculas',
      'exclamaciones', 'longitud',
  ]

  def fit(self, X, y=None):
    return self

  def transform(self, X):
    rows = []
    for text in X:
      text = text if isinstance(text, str) else ''
      s = lexicon_signals(text)
      letters = [c for c in text if c.isalpha()]
      caps_ratio = (
          sum(c.isupper() for c in letters) / len(letters) if letters else 0.0
      )
      rows.append([
          np.log1p(s['insultos']),
          np.log1p(s['difamacion']),
          np.log1p(s['segunda_persona']),
          float(s['amenazas'] > 0),
          float(s['odio_muerte'] > 0),
          # insulto + destinatario explícito = señal fuerte de acoso
          float(s['insultos'] > 0 and s['segunda_persona'] > 0),
          caps_ratio,
          np.log1p(text.count('!')),
          np.log1p(s['n_tokens']) / 5.0,
      ])
    return np.asarray(rows, dtype=np.float64)

  def get_feature_names_out(self, input_features=None):
    return np.asarray(self.feature_names, dtype=object)
