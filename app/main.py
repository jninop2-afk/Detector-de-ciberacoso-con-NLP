import sys
import os

sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

from app.services.predictor import predecir_ciberacoso
from scripts.train_pipeline import ejecutar_pipeline, actualizar_dataset_maestro


def cargarDatasetet():
    print("\n\t == MÓDULO DE ENTRENAMIENTO Y ACTUALIZACIÓN ==")
    # 1. Homologa y fusiona los nuevos CSVs en el dataset maestro
    actualizar_dataset_maestro()
    # 2. Reentrena el modelo con los datos unificados
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


def mostrar_menu():
    while True:
        print("\n==================================================")
        print("   SISTEMA DE DETECCIÓN DE CIBERACOSO (COLOMBIA)  ")
        print("==================================================")
        print("1. Actualizar Datasets y Reentrenar Modelo")
        print("2. Ir a Prueba por Consola")
        print("3. Salir")
        
        opcion = input("\nSeleccione una opción (1-3): ").strip()
        
        if opcion == "1":
            cargarDatasetet()
        elif opcion == "2":
            prueba_por_consola()
        elif opcion == "3":
            print("Saliendo del programa...")
            break
        else:
            print("Opción no válida. Intente nuevamente.")


if __name__ == "__main__":
    mostrar_menu()