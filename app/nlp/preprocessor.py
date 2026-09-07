import re
import unicodedata


#Función para quitar acentos del texto. Se llama en prepocesar_texto
def quitar_acentos(texto: str) -> str:
    """Normaliza y elimina los acentos de la cadena de texto."""
    nfkd = unicodedata.normalize('NFKD', texto)
    return "".join([c for c in nfkd if not unicodedata.combining(c)])



#Función para procesar texto.
def preprocesar_texto(texto: str) -> str:
    """
    Limpia y normaliza un mensaje para el pipeline de NLP.
    Cumple con los Issues #2 y #3.
    """
    if not texto or not isinstance(texto, str):
        return ""

    # 1. Convertir a minúsculas
    texto = texto.lower()

    # 2. Eliminar URLs
    texto = re.sub(r'https?://\S+|www\.\S+', '', texto)

    # 3. Eliminar acentos
    texto = quitar_acentos(texto)

    # 4. Eliminar caracteres especiales y números (mantiene solo letras y espacios)
    texto = re.sub(r'[^a-z\s]', '', texto)

    # 5. Tokenización simple y eliminación de espacios extra
    tokens = texto.split()

    # Retorna el texto limpio reunificado (listo para TF-IDF)
    return " ".join(tokens)