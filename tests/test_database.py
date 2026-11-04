"""Pruebas de src/database.py con una base SQLite temporal."""

from datetime import datetime, timedelta

GUILD, USER = 1, 42


def test_usuario_nuevo_tiene_estado_inicial(db_temporal):
  s = db_temporal.get_user_status(GUILD, USER)
  assert s == {'alerts_count': 0, 'consecutive_alerts': 0,
               'is_blocked': False, 'blocked_until': None}


def test_registrar_alertas_incrementa_total_y_consecutivas(db_temporal):
  assert db_temporal.register_user_alert(GUILD, USER) == (1, 1)
  assert db_temporal.register_user_alert(GUILD, USER) == (2, 2)


def test_mensaje_limpio_reinicia_solo_las_consecutivas(db_temporal):
  db_temporal.register_user_alert(GUILD, USER)
  db_temporal.register_user_alert(GUILD, USER)
  db_temporal.reset_consecutive(GUILD, USER)
  assert db_temporal.register_user_alert(GUILD, USER) == (3, 1)


def test_alertas_son_independientes_por_servidor(db_temporal):
  db_temporal.register_user_alert(GUILD, USER)
  assert db_temporal.register_user_alert(GUILD + 1, USER) == (1, 1)


def test_bloqueo_indefinido_no_vence(db_temporal):
  db_temporal.register_user_alert(GUILD, USER)
  db_temporal.set_user_blocked(GUILD, USER, duration_hours=None)
  s = db_temporal.get_user_status(GUILD, USER)
  assert s['is_blocked'] is True and s['blocked_until'] is None


def test_bloqueo_temporal_vencido_se_levanta_al_consultar(db_temporal):
  db_temporal.register_user_alert(GUILD, USER)
  pasado = (datetime.now() - timedelta(minutes=1)).isoformat()
  with db_temporal._connect() as conn:
    conn.execute('UPDATE user_status SET is_blocked = 1, blocked_until = ?'
                 ' WHERE guild_id = ? AND user_id = ?', (pasado, GUILD, USER))
  assert db_temporal.get_user_status(GUILD, USER)['is_blocked'] is False


def test_desbloquear_reinicia_alertas(db_temporal):
  db_temporal.register_user_alert(GUILD, USER)
  db_temporal.set_user_blocked(GUILD, USER)
  db_temporal.unblock_user(GUILD, USER)
  s = db_temporal.get_user_status(GUILD, USER)
  assert s['is_blocked'] is False and s['alerts_count'] == 0


def test_resolver_revision_guarda_feedback_una_sola_vez(db_temporal):
  rid = db_temporal.create_review(GUILD, 10, 20, USER, 'eres un idiota', 2, 0.6, 'clasico')
  assert db_temporal.resolve_review(rid, 2, reviewed_by=7) is True
  # Un segundo moderador ya no puede resolverla
  assert db_temporal.resolve_review(rid, 0, reviewed_by=8) is False
  assert db_temporal.count_feedback() == 1
  assert db_temporal.get_review(rid)['final_category'] == 2


def test_get_review_inexistente_devuelve_none(db_temporal):
  assert db_temporal.get_review(999) is None
