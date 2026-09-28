import os
import sys
import re
import joblib
import pandas as pd
from deep_translator import GoogleTranslator
from sklearn.feature_extraction.text import TfidfVectorizer
from sklearn.model_selection import train_test_split
from sklearn.tree import DecisionTreeClassifier
from sklearn.naive_bayes import MultinomialNB
from sklearn.svm import LinearSVC
from sklearn.calibration import CalibratedClassifierCV
from sklearn.metrics import accuracy_score, classification_report

# Asegurar importación del módulo local app/
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))
from app.nlp.preprocessor import preprocesar_texto

# Rutas y constantes globales
URL_OFICIAL = "https://huggingface.co/datasets/FelipeGuerra/Colombian_Spanish_Cyberbullying_Dataset_1/resolve/main/DATASET_FINAL.csv"
RUTA_MAESTRO = os.path.join("data", "raw", "colombian_cyberbullying.csv")
translator = GoogleTranslator(source='en', target='es')


def subclasificar_acoso(texto: str, annotation: str = "") -> int:
    """Clasifica un texto de acoso en una de las 4 categorías ofensivas especificadas."""
    txt = str(texto).lower()
    annot = str(annotation).lower()
    
    patron_amenaza = re.compile(
        r'\b(matar|matarte|caer|golpear|sufrir|atacar|sabemos donde|cuidese|bala|muerte|buscarte|violencia|threat)\b', 
        re.I
    )
    patron_maldicion = re.compile(
        r'\b(ojala|maldit|deseo|pudras|estrelle|enfermedad|lisiad|desgracia|mueras|curse)\b', 
        re.I
    )
    patron_difamacion = re.compile(
        r'\b(ladron|ladrona|roba|robadas|acosador|violador|estafador|estafadora|falso|falsa|denunciad|calumnia|defamation)\b', 
        re.I
    )
    patron_insulto = re.compile(
        r'\b(tonto|bobo|inutil|carechimba|hpta|hijaputa|hijodeputa|basura|perro|estupido|estupida|miserable)\b', 
        re.I
    )

    if patron_amenaza.search(txt) or 'threat' in annot:
        return 2  # Amenaza
    elif patron_maldicion.search(txt) or 'curse' in annot:
        return 3  # Maldición / Deseo de daño
    elif patron_difamacion.search(txt) or 'defamation' in annot:
        return 4  # Difamación
    elif patron_insulto.search(txt):
        return 1  # Insulto / Ofensa general
    else:
        return 1  # Ofensa por defecto


def traducir_texto(texto: str) -> str:
    """Traduce texto de inglés a español de forma segura."""
    if not isinstance(texto, str) or not texto.strip():
        return ""
    try:
        return translator.translate(texto[:400])
    except Exception:
        return texto


def actualizar_dataset_maestro():
    print("\n--- INICIANDO PROCESO DE ACTUALIZACIÓN Y FUSIÓN DE DATASETS ---")
    
    if os.path.exists(RUTA_MAESTRO):
        df_maestro = pd.read_csv(RUTA_MAESTRO)
        registros_iniciales = len(df_maestro)
        print(f"Dataset maestro cargado exitosamente. Registros actuales: {registros_iniciales}")
    else:
        print("ADVERTENCIA: No se encontró el archivo maestro local. Se creará uno nuevo.")
        df_maestro = pd.DataFrame(columns=['texto', 'categoria'])
        registros_iniciales = 0

    nuevos_registros = []

    # Procesar CorpusBullying
    file_corpus = "CorpusBullying_2.csv" if os.path.exists("CorpusBullying_2.csv") else "CorpusBullying.csv"
        
    if os.path.exists(file_corpus):
        print(f"Procesando {file_corpus} (Español)...")
        df_corpus = pd.read_csv(file_corpus, sep=';' if ';' in open(file_corpus, encoding='utf-8', errors='ignore').readline() else ',')
        
        df_acoso = df_corpus[df_corpus['Label'] == 1].copy()
        df_normal = df_corpus[df_corpus['Label'] == 0].sample(n=min(3000, len(df_corpus[df_corpus['Label'] == 0])), random_state=42).copy()
        
        for _, row in df_acoso.iterrows():
            txt = str(row['SpanishTweet'])
            cat = subclasificar_acoso(txt)
            nuevos_registros.append({'texto': txt, 'categoria': cat})
            
        for _, row in df_normal.iterrows():
            nuevos_registros.append({'texto': str(row['SpanishTweet']), 'categoria': 0})

    # Procesar Datasets en Inglés
    datasets_ingles = [
        {'file': 'twitter_racism_parsed_dataset.csv', 'col_text': 'Text', 'col_label': 'oh_label', 'col_annot': 'Annotation'},
        {'file': 'twitter_sexism_parsed_dataset.csv', 'col_text': 'Text', 'col_label': 'oh_label', 'col_annot': 'Annotation'},
        {'file': 'youtube_parsed_dataset.csv', 'col_text': 'Text', 'col_label': 'oh_label', 'col_annot': 'Profanity in UserID'}
    ]

    for item in datasets_ingles:
        fpath = item['file']
        if os.path.exists(fpath):
            print(f"Procesando y traduciendo {fpath}...")
            df_ing = pd.read_csv(fpath)
            
            df_pos = df_ing[df_ing[item['col_label']] == 1].copy()
            df_neg = df_ing[df_ing[item['col_label']] == 0].sample(n=min(500, len(df_ing[df_ing[item['col_label']] == 0])), random_state=42).copy()
            
            for _, row in df_pos.iterrows():
                txt_es = traducir_texto(str(row[item['col_text']]))
                annot = str(row.get(item['col_annot'], ''))
                cat = subclasificar_acoso(txt_es, annot)
                nuevos_registros.append({'texto': txt_es, 'categoria': cat})

            for _, row in df_neg.iterrows():
                txt_es = traducir_texto(str(row[item['col_text']]))
                nuevos_registros.append({'texto': txt_es, 'categoria': 0})

    if nuevos_registros:
        df_nuevos = pd.DataFrame(nuevos_registros)
        df_final = pd.concat([df_maestro, df_nuevos], ignore_index=True)
        
        df_final['texto_clean'] = df_final['texto'].astype(str).str.lower().str.strip()
        df_final = df_final.drop_duplicates(subset=['texto_clean'], keep='first').drop(columns=['texto_clean'])
        
        os.makedirs(os.path.dirname(RUTA_MAESTRO), exist_ok=True)
        df_final.to_csv(RUTA_MAESTRO, index=False)
        
        print("\n==================================================")
        print(f"ÉXITO: Dataset actualizado en '{RUTA_MAESTRO}'")
        print(f"Registros anteriores: {registros_iniciales} | Registros totales: {len(df_final)}")
        print("\nDistribución final de clases:")
        print(df_final['categoria'].value_counts().sort_index())
        print("==================================================")


def ejecutar_pipeline():
    print("\n--- ENTRENAMIENTO DEL MODELO ---")
    
    if os.path.exists(RUTA_MAESTRO):
        print("1. Cargando dataset actualizado desde copia local...")
        df = pd.read_csv(RUTA_MAESTRO)
    else:
        print("1. Descargando dataset oficial desde Hugging Face...")
        try:
            df = pd.read_csv(URL_OFICIAL)
            os.makedirs(os.path.dirname(RUTA_MAESTRO), exist_ok=True)
            df.to_csv(RUTA_MAESTRO, index=False)
        except Exception as e:
            print(f"Error al descargar dataset: {e}")
            return

    col_texto = next((col for col in ['texto', 'text', 'comment', 'mensaje'] if col in df.columns), df.columns[0])
    col_etiqueta = next((col for col in ['categoria', 'label', 'etiqueta', 'target', 'class'] if col in df.columns), df.columns[1])

    df = df.dropna(subset=[col_texto, col_etiqueta])
    df = df[df[col_texto].astype(str).str.strip() != ""]

    print("\n2. Aplicando limpieza NLP con soporte Leetspeak...")
    df['texto_limpio'] = df[col_texto].astype(str).apply(preprocesar_texto)
    df = df[df['texto_limpio'].str.strip() != ""]

    conteo_clases = df[col_etiqueta].value_counts()
    clases_validas = conteo_clases[conteo_clases >= 2].index
    df = df[df[col_etiqueta].isin(clases_validas)]

    print("\n3. Vectorizando con TF-IDF...")
    vectorizador = TfidfVectorizer(
        max_features=15000, 
        ngram_range=(1, 3), 
        sublinear_tf=True
    )
    
    # Asignación de X e y
    X = vectorizador.fit_transform(df['texto_limpio'])
    y = df[col_etiqueta]

    print("\n4. Dividiendo en Entrenamiento y Prueba...")
    X_train, X_test, y_train, y_test = train_test_split(
        X, y, test_size=0.2, random_state=42, stratify=y
    )

    print("\n5. Entrenando y comparando modelos...")
    modelos = {
        "Árbol de Decisión (J48)": DecisionTreeClassifier(random_state=42),
        "Naive Bayes": MultinomialNB(),
        "SVM Calibrado": CalibratedClassifierCV(
            LinearSVC(class_weight='balanced', random_state=42)
        )
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

    print("\n6. Serializando artefactos...")
    os.makedirs("models", exist_ok=True)
    joblib.dump(vectorizador, os.path.join("models", "vectorizer.pkl"))
    joblib.dump(mejor_modelo, os.path.join("models", "best_model.pkl"))
    print(" Modelos guardados con éxito en: 'models/vectorizer.pkl' y 'models/best_model.pkl'.")


if __name__ == "__main__":
    actualizar_dataset_maestro()
    ejecutar_pipeline()