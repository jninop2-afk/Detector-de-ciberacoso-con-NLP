"""Normalización de texto para español coloquial colombiano y de redes sociales.

Se exponen dos funciones:
  - clean_text: normalización agresiva para el modelo clásico (TF-IDF).
  - preprocess_for_transformer: normalización ligera para RoBERTa, que
    conserva la estructura de la frase.
"""

import re
import unicodedata

try:
  import emoji
except ImportError:  # el paquete es opcional
  emoji = None

LEET_TABLE = str.maketrans({
    '4': 'a',
    '@': 'a',
    '3': 'e',
    '1': 'i',
    '!': 'i',
    '0': 'o',
    '5': 's',
    '$': 's',
    '7': 't',
})

# Variantes de jerga / abreviaturas -> forma canónica.
# Unificar variantes hace que el modelo vea "hp", "hpta" e "hijueputa" como
# la misma señal en vez de tres palabras raras.
SLANG_MAP = {
    # hijueputa
    'hp': 'hijueputa', 'hpt': 'hijueputa', 'hpta': 'hijueputa',
    'hptas': 'hijueputa', 'hps': 'hijueputa', 'jp': 'hijueputa',
    'hjp': 'hijueputa', 'hdp': 'hijueputa', 'hijueputas': 'hijueputa',
    'jueputa': 'hijueputa', 'hijoeputa': 'hijueputa',
    'hijodeputa': 'hijueputa', 'hijuetantas': 'hijueputa',
    'hijuemadre': 'hijueputa', 'hijuep': 'hijueputa',
    # gonorrea
    'gonorrea': 'gonorrea', 'gonorreas': 'gonorrea', 'gonorria': 'gonorrea',
    'gonorriento': 'gonorrea', 'gonorrienta': 'gonorrea', 'gnrr': 'gonorrea',
    # malparido
    'mlp': 'malparido', 'malparida': 'malparido', 'malparidos': 'malparido',
    'malparidas': 'malparido', 'malparidez': 'malparido',
    # marica / maricón (se mantienen separados: "marica" suele ser coloquial)
    'mk': 'marica', 'mka': 'marica', 'marika': 'marica', 'maricas': 'marica',
    'marikon': 'maricon', 'maricones': 'maricon', 'maricona': 'maricon',
    # huevón
    'gueva': 'huevon', 'guevon': 'huevon', 'guevona': 'huevon',
    'guevones': 'huevon', 'gvn': 'huevon', 'huevona': 'huevon',
    'huevones': 'huevon', 'weon': 'huevon', 'webon': 'huevon',
    'guebon': 'huevon', 'huevonazo': 'huevon',
    # pirobo
    'piroba': 'pirobo', 'pirobos': 'pirobo', 'pirobas': 'pirobo',
    # otros insultos frecuentes
    'mrd': 'mierda', 'mierd': 'mierda', 'vrg': 'verga', 'vrga': 'verga',
    'ptm': 'puta madre', 'pta': 'puta', 'putas': 'puta', 'perras': 'perra',
    'estupida': 'estupido', 'estupidos': 'estupido', 'idiotas': 'idiota',
    'imbeciles': 'imbecil', 'malnacida': 'malnacido', 'malnacidos': 'malnacido',
    'sapos': 'sapo', 'sapa': 'sapo', 'sapas': 'sapo', 'lambon': 'lambon',
    'guerrillo': 'guerrillero', 'paraco': 'paramilitar', 'paracos': 'paramilitar',
    # abreviaturas de chat
    'q': 'que', 'k': 'que', 'ke': 'que', 'xq': 'porque', 'pq': 'porque',
    'porq': 'porque', 'tb': 'tambien', 'tmb': 'tambien', 'ud': 'usted',
    'uds': 'ustedes', 'pa': 'para', 'tqm': 'te quiero mucho',
    'ntp': 'no te preocupes', 'nd': 'nada', 'bn': 'bien', 'xfa': 'por favor',
    'pls': 'por favor', 'dnd': 'donde', 'msj': 'mensaje',
}

_URL_RE = re.compile(r'https?://\S+|www\.\S+')
_MENTION_RE = re.compile(r'@\w+')
_HASHTAG_RE = re.compile(r'#(\w+)')
_ELONGATION_RE = re.compile(r'([^\W\d_])\1{2,}')
_LAUGH_RE = re.compile(r'\b(?:j+[aeiou]+){2,}j*\b|\b(?:j+[sk]+){2,}\b|\b(?:ha){2,}h?\b')
_RT_RE = re.compile(r'^rt\b')
_NON_LETTER_RE = re.compile(r'[^a-zñü_\s]')
_SPACES_RE = re.compile(r'\s+')
_LEET_CHARS = set('4@31!05$7')


def strip_accents(text: str) -> str:
  """Elimina tildes conservando la ñ (CorpusBullying viene sin tildes)."""
  text = text.replace('ñ', '\0')
  text = ''.join(
      c for c in unicodedata.normalize('NFKD', text)
      if not unicodedata.combining(c)
  )
  return text.replace('\0', 'ñ')


def _decode_leet_token(token: str) -> str:
  """Decodifica leetspeak sólo en tokens mixtos ("s4p4", "hpt444").

  No toca números puros ("2000") ni la puntuación final ("hola!").
  """
  match = re.match(r'^(\W*)(.*?)(\W*)$', token)
  prefix, core, suffix = match.groups()
  if not core or not any(c.isalpha() for c in core):
    return token
  if not any(c in _LEET_CHARS for c in core):
    return token
  return prefix + core.translate(LEET_TABLE) + suffix


def decode_leetspeak(text: str) -> str:
  return ' '.join(_decode_leet_token(tok) for tok in text.split())


def emojis_to_tokens(text: str) -> str:
  """Convierte emojis a tokens (🤡 -> " emoji_cara_de_payaso ")."""
  if emoji is None:
    return text
  return emoji.demojize(
      text, language='es', delimiters=(' emoji_', ' ')
  )


def normalize_slang(text: str) -> str:
  return ' '.join(SLANG_MAP.get(tok, tok) for tok in text.split())


def clean_text(text: str) -> str:
  """Normalización completa para el modelo clásico."""
  if not isinstance(text, str):
    return ''

  text = unicodedata.normalize('NFC', text)
  text = _URL_RE.sub(' ', text)
  text = _MENTION_RE.sub(' usuario ', text)
  text = _HASHTAG_RE.sub(r'\1', text)
  text = emojis_to_tokens(text)
  text = text.lower()
  text = decode_leetspeak(text)
  text = _ELONGATION_RE.sub(r'\1', text)
  text = _LAUGH_RE.sub(' jaja ', text)
  text = strip_accents(text)
  text = _RT_RE.sub(' ', text)
  text = _NON_LETTER_RE.sub(' ', text)
  text = normalize_slang(_SPACES_RE.sub(' ', text).strip())
  return _SPACES_RE.sub(' ', text).strip()


def preprocess_for_transformer(text: str) -> str:
  """Normalización ligera estilo pysentimiento para RoBERTuito."""
  if not isinstance(text, str):
    return ''
  text = unicodedata.normalize('NFC', text)
  text = _URL_RE.sub(' url ', text)
  text = _MENTION_RE.sub(' @usuario ', text)
  text = _HASHTAG_RE.sub(r' hashtag \1 ', text)
  if emoji is not None:
    text = emoji.demojize(text, language='es', delimiters=(' emoji ', ' '))
  text = text.lower()
  text = decode_leetspeak(text)
  text = _ELONGATION_RE.sub(r'\1\1', text)
  text = _LAUGH_RE.sub(' jaja ', text)
  return _SPACES_RE.sub(' ', text).strip()
