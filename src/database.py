from datetime import datetime, timedelta
import sqlite3

DB_PATH = 'data/bot_database.db'


def init_db():
  """Inicializa las tablas necesarias en SQLite."""
  conn = sqlite3.connect(DB_PATH)
  cursor = conn.cursor()

  # Tabla de usuarios y alertas
  cursor.execute("""
        CREATE TABLE IF NOT EXISTS users (
            user_id INTEGER PRIMARY KEY,
            guild_id INTEGER,
            alerts_count INTEGER DEFAULT 0,
            consecutive_alerts INTEGER DEFAULT 0,
            is_blocked INTEGER DEFAULT 0,
            blocked_until TEXT
        )
    """)

  # Tabla de retroalimentación para reentrenamiento
  cursor.execute("""
        CREATE TABLE IF NOT EXISTS feedback_logs (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER,
            message_text TEXT,
            category_assigned INTEGER,
            timestamp TEXT
        )
    """)

  conn.commit()
  conn.close()


def get_user_data(user_id: int):
  """Obtiene el registro de un usuario."""
  conn = sqlite3.connect(DB_PATH)
  cursor = conn.cursor()
  cursor.execute(
      'SELECT alerts_count, consecutive_alerts, is_blocked, blocked_until FROM'
      ' users WHERE user_id = ?',
      (user_id,),
  )
  row = cursor.fetchone()
  conn.close()
  if row:
    return {
        'alerts_count': row[0],
        'consecutive_alerts': row[1],
        'is_blocked': bool(row[2]),
        'blocked_until': row[3],
    }
  return {
      'alerts_count': 0,
      'consecutive_alerts': 0,
      'is_blocked': False,
      'blocked_until': None,
  }


def register_user_alert(user_id: int, guild_id: int):
  """Incrementa las alertas del usuario y retorna los conteos actualizados."""
  conn = sqlite3.connect(DB_PATH)
  cursor = conn.cursor()

  user = get_user_data(user_id)
  new_alerts = user['alerts_count'] + 1
  new_consecutive = user['consecutive_alerts'] + 1

  cursor.execute(
      """
        INSERT INTO users (user_id, guild_id, alerts_count, consecutive_alerts)
        VALUES (?, ?, ?, ?)
        ON CONFLICT(user_id) DO UPDATE SET
            alerts_count = ?,
            consecutive_alerts = ?
    """,
      (
          user_id,
          guild_id,
          new_alerts,
          new_consecutive,
          new_alerts,
          new_consecutive,
      ),
  )

  conn.commit()
  conn.close()
  return new_alerts, new_consecutive


def set_user_blocked(user_id: int, duration_hours: int = None):
  """Aplica bloqueo temporal (en horas) o permanente (durante horas=None)."""
  conn = sqlite3.connect(DB_PATH)
  cursor = conn.cursor()

  blocked_until_str = None
  if duration_hours:
    blocked_until = datetime.now() + timedelta(hours=duration_hours)
    blocked_until_str = blocked_until.isoformat()

  cursor.execute(
      """
        UPDATE users 
        SET is_blocked = 1, blocked_until = ?
        WHERE user_id = ?
    """,
      (blocked_until_str, user_id),
  )

  conn.commit()
  conn.close()


def unblock_user_db(user_id: int):
  """Restablece el estado de bloqueo y reinicia el conteo de alertas del usuario."""
  conn = sqlite3.connect(DB_PATH)
  cursor = conn.cursor()
  cursor.execute(
      """
        UPDATE users 
        SET is_blocked = 0, blocked_until = NULL, alerts_count = 0, consecutive_alerts = 0
        WHERE user_id = ?
    """,
      (user_id,),
  )
  conn.commit()
  conn.close()


def save_admin_feedback(user_id: int, message_text: str, category: int):
  """Guarda la categorización corregida por el admin para reentrenar el modelo."""
  conn = sqlite3.connect(DB_PATH)
  cursor = conn.cursor()
  cursor.execute(
      """
        INSERT INTO feedback_logs (user_id, message_text, category_assigned, timestamp)
        VALUES (?, ?, ?, ?)
    """,
      (user_id, message_text, category, datetime.now().isoformat()),
  )
  conn.commit()
  conn.close()