"""Persistencia SQLite del bot: estado de usuarios, revisiones y feedback."""

from contextlib import contextmanager
from datetime import datetime, timedelta
import sqlite3

from src import config


@contextmanager
def _connect():
  conn = sqlite3.connect(config.DB_PATH)
  conn.row_factory = sqlite3.Row
  try:
    yield conn
    conn.commit()
  finally:
    conn.close()


def init_db():
  config.DB_PATH.parent.mkdir(parents=True, exist_ok=True)
  with _connect() as conn:
    conn.executescript("""
        CREATE TABLE IF NOT EXISTS user_status (
            guild_id INTEGER NOT NULL,
            user_id INTEGER NOT NULL,
            alerts_count INTEGER DEFAULT 0,
            consecutive_alerts INTEGER DEFAULT 0,
            is_blocked INTEGER DEFAULT 0,
            blocked_until TEXT,
            PRIMARY KEY (guild_id, user_id)
        );

        -- Mensajes dudosos enviados al canal de moderación
        CREATE TABLE IF NOT EXISTS pending_reviews (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            guild_id INTEGER,
            channel_id INTEGER,
            message_id INTEGER,
            user_id INTEGER,
            message_text TEXT,
            predicted_category INTEGER,
            confidence REAL,
            engine TEXT,
            status TEXT DEFAULT 'pendiente',
            final_category INTEGER,
            reviewed_by INTEGER,
            created_at TEXT,
            reviewed_at TEXT
        );

        -- Etiquetas confirmadas por administradores (fuente de reentrenamiento)
        CREATE TABLE IF NOT EXISTS admin_feedback (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER,
            message_text TEXT,
            category INTEGER,
            reviewed_by INTEGER,
            timestamp TEXT
        );
    """)
    _migrate_legacy(conn)


def _migrate_legacy(conn):
  """Copia la tabla 'users' antigua (clave sólo user_id) al nuevo esquema."""
  legacy = conn.execute(
      "SELECT 1 FROM sqlite_master WHERE type='table' AND name='users'"
  ).fetchone()
  if not legacy:
    return
  conn.execute("""
      INSERT OR IGNORE INTO user_status
          (guild_id, user_id, alerts_count, consecutive_alerts, is_blocked, blocked_until)
      SELECT COALESCE(guild_id, 0), user_id, alerts_count, consecutive_alerts,
             is_blocked, blocked_until
      FROM users
  """)
  conn.execute('ALTER TABLE users RENAME TO users_legacy')


def get_user_status(guild_id: int, user_id: int) -> dict:
  """Devuelve el estado del usuario, levantando bloqueos ya vencidos."""
  with _connect() as conn:
    row = conn.execute(
        'SELECT * FROM user_status WHERE guild_id = ? AND user_id = ?',
        (guild_id, user_id),
    ).fetchone()
    if not row:
      return {
          'alerts_count': 0,
          'consecutive_alerts': 0,
          'is_blocked': False,
          'blocked_until': None,
      }
    status = dict(row)
    status['is_blocked'] = bool(status['is_blocked'])
    if status['is_blocked'] and status['blocked_until']:
      if datetime.fromisoformat(status['blocked_until']) <= datetime.now():
        conn.execute(
            'UPDATE user_status SET is_blocked = 0, blocked_until = NULL'
            ' WHERE guild_id = ? AND user_id = ?',
            (guild_id, user_id),
        )
        status['is_blocked'] = False
        status['blocked_until'] = None
    return status


def register_user_alert(guild_id: int, user_id: int) -> tuple[int, int]:
  """Suma una alerta y devuelve (total, consecutivas)."""
  with _connect() as conn:
    conn.execute(
        """
        INSERT INTO user_status (guild_id, user_id, alerts_count, consecutive_alerts)
        VALUES (?, ?, 1, 1)
        ON CONFLICT(guild_id, user_id) DO UPDATE SET
            alerts_count = alerts_count + 1,
            consecutive_alerts = consecutive_alerts + 1
        """,
        (guild_id, user_id),
    )
    row = conn.execute(
        'SELECT alerts_count, consecutive_alerts FROM user_status'
        ' WHERE guild_id = ? AND user_id = ?',
        (guild_id, user_id),
    ).fetchone()
  return row['alerts_count'], row['consecutive_alerts']


def reset_consecutive(guild_id: int, user_id: int):
  """Un mensaje limpio rompe la racha de alertas consecutivas."""
  with _connect() as conn:
    conn.execute(
        'UPDATE user_status SET consecutive_alerts = 0'
        ' WHERE guild_id = ? AND user_id = ? AND consecutive_alerts > 0',
        (guild_id, user_id),
    )


def set_user_blocked(guild_id: int, user_id: int, duration_hours: float | None = None):
  """Bloqueo temporal (horas) o indefinido (None)."""
  until = None
  if duration_hours:
    until = (datetime.now() + timedelta(hours=duration_hours)).isoformat()
  with _connect() as conn:
    conn.execute(
        'UPDATE user_status SET is_blocked = 1, blocked_until = ?'
        ' WHERE guild_id = ? AND user_id = ?',
        (until, guild_id, user_id),
    )


def unblock_user(guild_id: int, user_id: int):
  with _connect() as conn:
    conn.execute(
        'UPDATE user_status SET is_blocked = 0, blocked_until = NULL,'
        ' alerts_count = 0, consecutive_alerts = 0'
        ' WHERE guild_id = ? AND user_id = ?',
        (guild_id, user_id),
    )


def create_review(
    guild_id: int, channel_id: int, message_id: int, user_id: int,
    text: str, category: int, confidence: float, engine: str,
) -> int:
  with _connect() as conn:
    cur = conn.execute(
        """
        INSERT INTO pending_reviews (guild_id, channel_id, message_id, user_id,
            message_text, predicted_category, confidence, engine, created_at)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (guild_id, channel_id, message_id, user_id, text, category,
         confidence, engine, datetime.now().isoformat()),
    )
    return cur.lastrowid


def get_review(review_id: int) -> dict | None:
  with _connect() as conn:
    row = conn.execute(
        'SELECT * FROM pending_reviews WHERE id = ?', (review_id,)
    ).fetchone()
  return dict(row) if row else None


def resolve_review(review_id: int, category: int, reviewed_by: int) -> bool:
  """Marca la revisión como resuelta y guarda el feedback.

  Devuelve False si otro admin ya la había resuelto.
  """
  with _connect() as conn:
    cur = conn.execute(
        """
        UPDATE pending_reviews
        SET status = 'resuelta', final_category = ?, reviewed_by = ?, reviewed_at = ?
        WHERE id = ? AND status = 'pendiente'
        """,
        (category, reviewed_by, datetime.now().isoformat(), review_id),
    )
    if cur.rowcount == 0:
      return False
    review = conn.execute(
        'SELECT user_id, message_text FROM pending_reviews WHERE id = ?',
        (review_id,),
    ).fetchone()
    conn.execute(
        'INSERT INTO admin_feedback (user_id, message_text, category, reviewed_by, timestamp)'
        ' VALUES (?, ?, ?, ?, ?)',
        (review['user_id'], review['message_text'], category, reviewed_by,
         datetime.now().isoformat()),
    )
  return True


def count_feedback() -> int:
  with _connect() as conn:
    return conn.execute('SELECT COUNT(*) FROM admin_feedback').fetchone()[0]
