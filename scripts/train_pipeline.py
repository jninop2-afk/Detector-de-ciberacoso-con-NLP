import os
import sys
import joblib
import pandas as pd
from sklearn.feature_extraction.text import TfidfVectorizer
from sklearn.model_selection import train_test_split
from sklearn.tree import DecisionTreeClassifier
from sklearn.naive_bayes import MultinomialNB
from sklearn.svm import SVC
from sklearn.metrics import accuracy_score, classification_report

# Asegurar importación del módulo local app/
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))
from app.nlp.preprocessor import preprocesar_texto

def ejecutar_pipeline():
    print("1. Descargando Dataset de Ciberacoso Colombiano desde Hugging Face...")
    url_dataset = "https://huggingface.co/datasets/FelipeGuerra/Colombian_Spanish_Cyberbullying_Dataset_1/resolve/main/DATASET_FINAL.csv"
    
    try:
        df = pd.read_csv(url_dataset)
    except Exception as e:
        print(f"Error al leer el dataset remoto: {e}")
        return

    col_texto = next((col for col in ['texto', 'text', 'comment', 'mensaje'] if col in df.columns), df.columns[0])
    col_etiqueta = next((col for col in ['categoria', 'label', 'etiqueta', 'target', 'class'] if col in df.columns), df.columns[1])

    # Limpieza de nulos y vacíos
    df = df.dropna(subset=[col_texto, col_etiqueta])
    df = df[df[col_texto].astype(str).str.strip() != ""]

    print("\n2. Aplicando limpieza NLP (Issues #2 y #3)...")
    df['texto_limpio'] = df[col_texto].astype(str).apply(preprocesar_texto)
    df = df[df['texto_limpio'].str.strip() != ""]

    # Filtrar clases con menos de 2 registros
    conteo_clases = df[col_etiqueta].value_counts()
    clases_validas = conteo_clases[conteo_clases >= 2].index
    df = df[df[col_etiqueta].isin(clases_validas)]

    print("\n3. Vectorizando con TF-IDF (Issue #4)...")
    vectorizador = TfidfVectorizer(max_features=5000)
    X = vectorizador.fit_transform(df['texto_limpio'])
    y = df[col_etiqueta]

    print("\n4. Dividiendo en Entrenamiento y Prueba (Issue #5)...")
    X_train, X_test, y_train, y_test = train_test_split(
        X, y, test_size=0.2, random_state=42, stratify=y
    )

    print("\n5. Entrenando y comparando modelos (Issue #6)...")
    modelos = {
        "Árbol de Decisión (J48)": DecisionTreeClassifier(random_state=42),
        "Naive Bayes": MultinomialNB(),
        "SVM (Support Vector Machine)": SVC(kernel='linear', probability=True, random_state=42)
    }

    mejor_modelo = None
    mejor_precision = 0.0
    nombre_mejor_modelo = ""

    for nombre, modelo in modelos.items():
        modelo.fit(X_train, y_train)
        predicciones = modelo.predict(X_test)
        acc = accuracy_score(y_test, predicciones)
        print(f"\n--- {nombre} ---")
        print(f"Accuracy: {acc:.4f}")
        print(classification_report(y_test, predicciones, zero_division=0))

        if acc > mejor_precision:
            mejor_precision = acc
            mejor_modelo = modelo
            nombre_mejor_modelo = nombre

    print(f"\n El mejor modelo fue: {nombre_mejor_modelo} con {mejor_precision:.4f} de Accuracy.")

    print("\n6. Serializando artefactos (Issue #7)...")
    os.makedirs("models", exist_ok=True)
    joblib.dump(vectorizador, os.path.join("models", "vectorizer.pkl"))
    joblib.dump(mejor_modelo, os.path.join("models", "best_model.pkl"))
    print("Modelos guardados con éxito en: 'models/vectorizer.pkl' y 'models/best_model.pkl'.")

if __name__ == "__main__":
    ejecutar_pipeline()