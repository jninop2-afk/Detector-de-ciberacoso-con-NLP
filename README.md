# Detector de ciberacoso (NLP + ML + RoBERTa) — Bot de Discord

Sistema híbrido para detectar ciberacoso en español colombiano y de redes
sociales, con 5 categorías:

| Id | Categoría |
|----|-----------|
| 0 | Sin ciberacoso |
| 1 | Hostigamiento y amenazas directas |
| 2 | Insultos y ofensas personales |
| 3 | Incitación al odio y muerte |
| 4 | Difamación, calumnia y ataques políticos |

## Arquitectura

```
mensaje ──► preprocesado NLP ──► MODELO CLÁSICO (rápido, todos los mensajes)
            (jerga, leetspeak,     etapa 1: ¿acoso? (umbral optimizado)
             emojis, risas)        etapa 2: categoría 1-4
                                          │
                     ¿sospecha? ──no──► decisión
                          │ sí
                          ▼
                 RoBERTuito (RoBERTa en español, tweets)
                 fusión de probabilidades (peso 0.7)
                          │
                          ▼
         SANCIONAR | REVISAR_POR_ADMIN | PERMITIR_MENSAJE
```

**Modelo clásico**: TF-IDF de palabras (1-2 gramas) + TF-IDF de caracteres
(2-5 gramas, robusto a errores ortográficos) + rasgos léxicos (insultos,
insulto dirigido a segunda persona, patrones de amenaza y de odio/muerte,
términos de difamación, ratio de mayúsculas). El clasificador
(regresión logística o SVM calibrada) se elige por validación cruzada.

**Cuándo se consulta RoBERTa** (`src/predict.py`):
- la probabilidad de acoso está a menos de `UNCERTAINTY_MARGIN` del umbral,
- la confianza de la categoría es menor que `CONFIDENCE_THRESHOLD`,
- la categoría predicha tuvo F1 de validación menor que `MIN_CLASS_F1`,
- el clásico dice "seguro" pero hay patrones explícitos de amenaza/odio.

**RoBERTa** (`src/transformer.py`):
- `finetuned`: modelo propio con las 5 categorías (recomendado, ver abajo).
- `zero_shot`: si aún no existe, usa `pysentimiento/robertuito-hate-speech`
  sólo para la probabilidad de acoso (la categoría la da el clásico).

Si ambos modelos discrepan, o la confianza final es baja, el mensaje **no se
sanciona**: se envía al canal de moderación con botones para que un
moderador elija la categoría. Esa decisión se guarda y se usa al reentrenar.

## Uso

```bash
pip install torch --index-url https://download.pytorch.org/whl/cpu
pip install -r requirements.txt

python main.py train            # entrena el modelo clásico (~minutos)
python main.py train-roberta    # fine-tuning de RoBERTuito (lento en CPU)
python main.py                  # consola de pruebas
python main.py bot              # bot de Discord
python main.py audit            # busca etiquetas mal asignadas
```

Opciones de fine-tuning: `--epochs 4 --batch-size 16 --lr 3e-5
--corpus-negatives 1500`; `--limit 200 --epochs 1` para una prueba rápida.
En CPU cada época tarda decenas de minutos; en GPU (p. ej. Colab) pocos
minutos. Copia la carpeta resultante a `models/roberta_finetuned/`.

### `.env`

```
DISCORD_BOT_TOKEN=...
ADMIN_MOD_CHANNEL_ID=...
# Opcionales
ROBERTA_ENABLED=1
CONFIDENCE_THRESHOLD=0.70
UNCERTAINTY_MARGIN=0.20
MIN_CLASS_F1=0.60
ROBERTA_WEIGHT=0.70
```

El bot necesita los permisos *Gestionar mensajes* y *Moderar miembros*, y los
intents *Message Content* y *Server Members* activados en el portal de
desarrolladores.

## Comandos del bot

| Comando | Permiso | Descripción |
|---------|---------|-------------|
| `!analizar <texto>` | Gestionar mensajes | Prueba el detector sin sancionar |
| `!estado @usuario` | Gestionar mensajes | Alertas y bloqueo del usuario |
| `!modelo` | Gestionar mensajes | Métricas del modelo cargado |
| `!desbloquear @usuario` | Administrador | Quita bloqueo y reinicia alertas |
| `!reentrenar` | Administrador | Reentrena el clásico con el feedback |

Reglas de sanción: alertas 1-3 → advertencia; alerta 4 o más → silencio de
1 hora; 4 alertas consecutivas (sin mensajes limpios entre ellas) → bloqueo
indefinido.

## Mejorar la calidad de las etiquetas

Las categorías del dataset tienen ruido. `python main.py audit` entrena con
validación cruzada y lista en `data/processed/label_review.csv` los ejemplos
cuya etiqueta el modelo considera muy improbable. Revisa el archivo, rellena
`categoria_corregida` donde corresponda y guarda esas filas (columnas
`texto,categoria_corregida`) en `data/raw/label_corrections.csv`. El próximo
entrenamiento las aplica automáticamente, sin modificar los CSV originales.

## Estructura

```
src/config.py            rutas, categorías y umbrales
src/preprocessing.py     normalización (jerga colombiana, leetspeak, emojis)
src/features.py          rasgos léxicos (amenazas, odio, insulto dirigido)
src/data.py              carga/unificación de datasets + feedback
src/train.py             entrenamiento del modelo clásico
src/train_transformer.py fine-tuning de RoBERTuito
src/transformer.py       inferencia RoBERTa
src/predict.py           detector híbrido en cascada
src/label_audit.py       detección de etiquetas erróneas
src/database.py          SQLite del bot
src/bot_Discord/         bot, botones de revisión y reglas de sanción
```
