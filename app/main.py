import sys
import os

sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

from app.services.predictor import predecir_ciberacoso
from scripts.train_pipeline import ejecutar_pipeline

def cargarDatasetet():
    print("\n\t == MÓDULO DE ENTRENAMIENTO ==")
    ejecutar_pipeline()

def prueba_por_consola():
    print("\n\t---- BIENVENIDO PRUEBA DE DETECCIÓN DE CIBERACOSO (NLP) ----")
    print("Digite el mensaje que quiere analizar ó la palabra 'salir' para terminar la prueba")
    while True:
        texto_User = input("\nIngresar texto: ")
        
        if texto_User.lower().strip() == "salir":
            print("Saliendo del modo de prueba...")
            break
            
        if not texto_User.strip():
            continue
            
        try:
            resultado = predecir_ciberacoso(texto_User)
            print("\n-- IMPRIMIENDO RESULTADO DEL ANÁLISIS --")
            print(f"Texto limpio:    {resultado['texto_limpio']}")
            print(f"Categoría:       {resultado['categoria_detectada']}")
            print(f"Confianza/Prob:  {resultado['probabilidad'] * 100:.2f}%\n")
        except Exception as e:
            print(f"Error en la predicción (¿Ya entrenaste el modelo?): {e}")



if __name__ == "__main__":
    ejecutar_pipeline()
    prueba_por_consola()