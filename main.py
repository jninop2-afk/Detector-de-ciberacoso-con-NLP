import sys
from src.predict import CyberbullyingDetector

# Diccionario descriptivo de las categorías para la consola
CATEGORY_DESCRIPTIONS = {
    0: "0 - Sin Ciberacoso (Mensaje Normal)",
    1: "1 - Hostigamiento y Amenazas Directas",
    2: "2 - Insultos y Ofensas Personales",
    3: "3 - Incitación al Odio y Muerte",
    4: "4 - Difamación, Calumnia y Ataques Políticos",
}


def run_interactive_cli():
  print("=" * 65)
  print("   DETECTOR DE CIBERACOSO NLP - CONSOLA DE PRUEBAS")
  print("=" * 65)
  print("Cargando artefactos del modelo...")

  try:
    detector = CyberbullyingDetector(
        models_dir="models", confidence_threshold=0.70
    )
    print(" Modelos cargados correctamente.")
  except Exception as e:
    print(f" Error al cargar el detector: {e}")
    sys.exit(1)

  print("\nEscribe cualquier texto para analizarlo.")
  print("Escribe 'salir' o 'exit' para terminar la ejecución.\n")
  print("-" * 65)

  while True:
    try:
      user_input = input("\n Ingrese un mensaje > ").strip()

      if not user_input:
        continue

      if user_input.lower() in ["salir", "exit", "quit"]:
        print("\n¡Hasta luego! Finalizando consola de pruebas...")
        break

      # Ejecutar predicción
      result = detector.predict(user_input)

      # Formatear salida en pantalla
      print("\n" + "─" * 50)
      print(f" Entrada original : \"{result['texto_original']}\"")
      print(f" Preprocesado NLP : \"{result['texto_limpio']}\"")
      print("─" * 50)

      if result["es_ciberacoso"]:
        cat_id = result.get("categoria_gravedad", 0)
        cat_desc = CATEGORY_DESCRIPTIONS.get(cat_id, f"Categoría {cat_id}")

        print(" DIAGNÓSTICO       : [ ⚠️  POSIBLE CIBERACOSO ]")
        print(f" GRAVEDAD DETECTADA: {cat_desc}")
      else:
        print(" DIAGNÓSTICO       : [ MENSAJE SEGURO ]")

      print(f" CONFIANZA MODELO  : {result['confianza'] * 100:.2f}%")
      print(f" NOTIFICAR ADMIN   : {result['notificar_admin']}")
      print(f" ACCIÓN SUGERIDA   : {result['accion_sugerida']}")
      print("─" * 50)

    except KeyboardInterrupt:
      print("\n\nSaliendo...")
      break
    except Exception as err:
      print(f" Ocurrió un error al procesar el mensaje: {err}")


if __name__ == "__main__":
  run_interactive_cli()