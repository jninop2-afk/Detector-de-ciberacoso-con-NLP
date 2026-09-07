from app.services.predictor import predecir_ciberacoso

def prueba_por_consola():
    
    print("\n\t----BIENVENIDO PRUEBA DE DETECCIÓN DE CIBERACOSO (NLP)----")
    print("Digite el mensaje que quiere analizar ó la palabra 'salir' para terminar la prueba")
    while True:
        texto_User = input("Ingresar texto:")
        if texto_User.lower().strip()== "salir":
            print("Saliendo del programa...")
            break
        if not texto_User.strip():
            continue
        resultado = predecir_ciberacoso(texto_User)
        print("\n--IMPRIMIENDO RESULTADO DEL ANÁLSIS--")
        print(f"Texto limpio: {resultado['texto_limpio']}")
        print(f"Categoría:       {resultado['categoria_detectada']}")
        print(f"Confianza/Prob:  {resultado['probabilidad'] * 100:.2f}%\n")
        break

if __name__ == "__main__":
    prueba_por_consola()