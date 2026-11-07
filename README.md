# Detector de ciberacoso (NLP + ML + RoBERTa) — Bots de Discord y Bluesky

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
python main.py bluesky          # bot de Bluesky (responde a menciones)
python main.py vigilancia       # vigila cuentas de Bluesky sin menciones
python main.py bluesky-diag     # últimas notificaciones de la cuenta del bot
python main.py traducir         # traduce los datasets en inglés (una vez)
python main.py audit            # busca etiquetas mal asignadas
python main.py backup           # copia de seguridad de la base de datos
```

Opciones de fine-tuning: `--epochs 4 --batch-size 16 --lr 3e-5
--corpus-negatives 1500`; `--limit 200 --epochs 1` para una prueba rápida.
En CPU cada época tarda decenas de minutos; en GPU (p. ej. Colab) pocos
minutos. Copia la carpeta resultante a `models/roberta_finetuned/`.

### `.env`

Copia `.env.example` a `.env` y completa los valores. El token de Discord
puede llamarse `DISCORD_BOT_TOKEN` o `DISCORD_TOKEN` (nombre del proyecto
anterior).

Los intents *Message Content* y *Server Members* deben estar activados en el
portal de desarrolladores. Al arrancar, el bot imprime su **enlace de
invitación** con los permisos necesarios: *Gestionar mensajes*, *Moderar
miembros*, *Gestionar canales* y *Gestionar roles* (los dos últimos sirven
para crear el canal privado de moderación). Su rol debe estar por encima de
los usuarios que deba silenciar.

## Bot de Discord (multi-servidor)

Cualquier servidor puede añadir el bot con el enlace de invitación. **No
analiza ningún mensaje hasta que un administrador use `/configurar`**; el
dueño del servidor recibe estas instrucciones por MD al añadirlo.

### Privacidad: sólo los administradores ven y deciden

- Todos los comandos son *slash commands* restringidos a **Administrador**:
  Discord no se los muestra al resto de miembros, y las respuestas son
  efímeras (sólo las ve quien ejecutó el comando).
- `/configurar` crea un canal **privado** (`#moderacion-ciberacoso`) o vuelve
  privado el canal indicado. Si otros roles tienen acceso explícito al canal,
  el bot lo avisa.
- Los botones de revisión sólo funcionan para administradores.
- Por defecto **no se publica nada en los canales**: el infractor recibe un
  MD y los administradores un reporte en el canal privado. Los avisos
  públicos se activan con `/configurar avisos_publicos:True`.

### Comandos de administradores (cada servidor)

| Comando | Descripción |
|---------|-------------|
| `/configurar [canal] [avisos_publicos]` | Activa el bot y define el canal privado de moderación |
| `/analizar texto` | Prueba el detector sin sancionar |
| `/estado usuario` | Alertas y bloqueo del usuario |
| `/desbloquear usuario` | Quita bloqueo y reinicia alertas |
| `/modelo` | Métricas del modelo y feedback del servidor |

### Comandos del dueño del bot (sólo en `OWNER_GUILD_ID`)

| Comando | Descripción |
|---------|-------------|
| `/reentrenar` | Hace una copia de seguridad y reentrena el clásico con el feedback de confianza |
| `/servidores` | Servidores donde está el bot, si están configurados y cuánto feedback aportan |
| `/confiar servidor_id confiar` | Decide si el feedback de un servidor se usa al reentrenar |

Todos los servidores comparten el mismo modelo, así que **sólo se entrena con
feedback de servidores de confianza** (el tuyo lo es automáticamente, y el
feedback anterior a este cambio también se usa). Así un administrador externo
no puede estropear el modelo clasificando mal a propósito.

Reglas de sanción: alertas 1-3 → advertencia; alerta 4 o más → silencio de
1 hora; 4 alertas consecutivas (sin mensajes limpios entre ellas) → bloqueo
indefinido.

## Bluesky

Ambos modos usan el mismo detector híbrido que Discord y la cuenta definida
en `BLUESKY_HANDLE` / `BLUESKY_APP_PASSWORD`.

**Menciones** (`python main.py bluesky`): alguien responde a un post
mencionando al bot y éste analiza el post original (o la propia mención si
no es respuesta) y contesta con la categoría. Si la mención incluye la
palabra `reportar`, además reporta el post a la moderación.

**Vigilancia** (`python main.py vigilancia`): revisa cada
`BLUESKY_INTERVALO` segundos las respuestas que reciben los posts recientes
de las cuentas vigiladas. No publica nada: registra lo detectado en
`data/vigilancia_bluesky.json`. Hay dos tipos de cuentas vigiladas:

- Las de `BLUESKY_CUENTAS_VIGILADAS` (las decide el dueño del bot); de ellas
  también se analizan sus propios posts.
- Las que lo piden **mencionando al bot con `vigilar`** (y salen con
  `dejar de vigilar`). Cada persona sólo puede pedirlo para su propia cuenta
  y de ella sólo se analizan las respuestas que recibe, nunca sus posts. Hay
  un máximo de `BLUESKY_MAX_VIGILADAS` cuentas. La lista se relee en cada
  ciclo: no hace falta reiniciar la vigilancia.

**Reportes**: sólo se reporta cuando el detector sugiere `SANCIONAR` y la
confianza supera `BLUESKY_UMBRAL_REPORTE`; los casos `REVISAR_POR_ADMIN` no
se reportan. Por defecto es una simulación; `BLUESKY_REPORTES_REALES=1`
envía reportes reales.

## Base de datos y copias de seguridad

`data/bot_database.db` (SQLite) es compartida por todos los bots. Usa modo
WAL, así que el bot de Discord, el de Bluesky y la vigilancia pueden correr
a la vez sin errores de "database is locked".

El bot de Discord hace una copia automática cada 24 horas (y otra antes de
cada `/reentrenar`); también puede lanzarse con `python main.py backup`. Las
copias van a `BACKUP_DIR` (por defecto `backups/`) y se conservan las
últimas `BACKUP_KEEP`. Para protegerse si se pierde la máquina, apunta
`BACKUP_DIR` a una carpeta sincronizada fuera de ella.

## Despliegue en un servidor (Hetzner Cloud / Ubuntu 24.04)

Los bots sólo hacen conexiones salientes: no hace falta abrir puertos.
Plan recomendado: 2 vCPU, 4 GB de RAM, 40 GB de disco.

```bash
# 1. En el servidor recién creado, como root (una sola vez)
curl -fsSLO https://raw.githubusercontent.com/jninop2-afk/Detector-de-ciberacoso-con-NLP/Main/deploy/prepare_server.sh
bash prepare_server.sh                       # usuario cyberbot, swap, cortafuegos, SSH seguro

# 2. Como cyberbot (ssh cyberbot@<IP>)
git clone https://github.com/jninop2-afk/Detector-de-ciberacoso-con-NLP.git MPB
cd MPB && bash deploy/setup.sh               # Python, entorno y dependencias
```

```powershell
# 3. En tu PC (con el bot local detenido): modelos, base de datos y .env
powershell -ExecutionPolicy Bypass -File deploy\subir_al_servidor.ps1 -Servidor <IP>
```

```bash
# 4. En el servidor
bash deploy/install_services.sh bot          # añade bluesky vigilancia si los usas
```

Cada bot es un servicio systemd (`cyberbot@bot`, `cyberbot@bluesky`,
`cyberbot@vigilancia`): arranca solo al encender la máquina y se reinicia si
se cae. `deploy/constraints.txt` fija las versiones con las que se entrenaron
los modelos.

| Tarea | Comando |
|-------|---------|
| Ver registros en vivo | `journalctl -u cyberbot@bot -f` |
| Estado | `systemctl status cyberbot@bot` |
| Reiniciar / parar | `sudo systemctl restart cyberbot@bot` / `sudo systemctl stop cyberbot@bot` |
| Actualizar código | `bash deploy/update.sh` |

No ejecutes el mismo bot en tu PC y en el servidor a la vez: ambos
responderían a cada mensaje (sanciones y respuestas duplicadas).

## Datasets en inglés

`data/raw/` incluye los datasets de Twitter (racismo, sexismo) y YouTube.
`python main.py traducir` traduce al español los mensajes ofensivos y una
muestra de 500 no ofensivos por archivo (`--negativos N`,
`--max-por-archivo N` para una prueba rápida), y los guarda en
`data/processed/ingles_traducido.csv`. Es lento pero reanudable. En el
siguiente `python main.py train` esos textos se usan **sólo en la etapa
binaria**: su categoría 1-4 sale de reglas léxicas y metería ruido en el
clasificador de gravedad.

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
src/bot_bluesky/         bot por menciones, vigilancia y diagnóstico
src/translate_english.py traducción de los datasets en inglés
```
