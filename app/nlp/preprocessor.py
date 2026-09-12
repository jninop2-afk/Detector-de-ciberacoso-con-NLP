import re
import unicodedata

def decodificar_leetspeak(texto: str) -> str:
    """Traduce números usados como letras al alfabeto estándar."""
    mapa_leet = {
        '0': 'o',
        '1': 'i',
        '3': 'e',
        '4': 'a',
        '5': 's',
        '7': 't'
    }
    for num, letra in mapa_leet.items():
        texto = texto.replace(num, letra)
    return texto

def preprocesar_texto(texto: str) -> str:
    """Limpia y estandariza el texto para el modelo NLP."""
    if not isinstance(texto, str):
        return ""
    
    # 1. Convertir a minúsculas
    texto = texto.lower()
    
    # 2. Decodificar leetspeak (Ej: p3rr4 -> perra)
    texto = decodificar_leetspeak(texto)
    
    # 3. Quitar acentos 
    texto = ''.join(c for c in unicodedata.normalize('NFD', texto) if unicodedata.category(c) != 'Mn')
    
    # 4. Eliminar caracteres especiales, puntuación y URLs
    texto = re.sub(r'http\S+|www\S+|https\S+', '', texto, flags=re.MULTILINE)
    texto = re.sub(r'[^a-z\s]', '', texto)
    
    # 5. Eliminar espacios extra
    texto = re.sub(r'\s+', ' ', texto).strip()
    
    return texto