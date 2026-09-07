import os
import sys
import joblib

# Asegurar importación del módulo local app/
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '../..')))
from app.nlp.preprocessor import preprocesar_texto

RUTA_VECTORIZADOR = os.path.join("models", "vectorizer.pkl")
RUTA_MODELO = os.path.join("models", "best_model.pkl")

# Carga de artefactos en memoria
vectorizador = joblib.load(RUTA_VECTORIZADOR)
modelo = joblib.load(RUTA_MODELO)

# Diccionario de traducción según la documentación del dataset
MAPA_CATEGORIAS = {
    0: "Sin ciberacoso (Texto normal o jerga)",
    1: "Insulto",
    2: "Amenaza",
    3: "Maldición / Deseo de daño",
    4: "Difamación"
}

def predecir_ciberacoso(texto: str) -> dict:
    """Procesa un texto entrante y retorna la predicción traducida del modelo SVM."""
    texto_limpio = preprocesar_texto(texto)
    
    if not texto_limpio:
        return {
            "texto_original": texto,
            "texto_limpio": "",
            "categoria_detectada": "Sin contenido relevante",
            "probabilidad": 0.0
        }

    vector = vectorizador.transform([texto_limpio])
    prediccion_num = int(modelo.predict(vector)[0])
    
    # Mapeo a etiqueta legible
    categoria_legible = MAPA_CATEGORIAS.get(prediccion_num, f"Categoría {prediccion_num}")

    probabilidades = modelo.predict_proba(vector)[0]
    probabilidad_maxima = float(max(probabilidades))

    return {
        "texto_original": texto,
        "texto_limpio": texto_limpio,
        "categoria_detectada": categoria_legible,
        "probabilidad": round(probabilidad_maxima, 4)
    }

if __name__ == "__main__":
    # Prueba rápida
    ejemplo = "Ojalá te mueras y te pase lo peor"
    res = predecir_ciberacoso(ejemplo)
    print(f"\nTexto: {res['texto_original']}")
    print(f"Categoría: {res['categoria_detectada']} | Confianza: {res['probabilidad']}")