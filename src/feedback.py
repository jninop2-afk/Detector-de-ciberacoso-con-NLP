"""Reentrenamiento con el feedback de los administradores.

El feedback vive en la tabla SQLite 'admin_feedback' (y en el CSV heredado
data/raw/feedback_admin.csv). src/data.py lo incorpora en memoria al
construir los datasets, así que los CSV crudos nunca se modifican y el
feedback no se duplica entre reentrenamientos.
"""

from src.database import count_feedback, init_db
from src.train import train_classic


def retrain_from_feedback() -> dict:
  init_db()
  print(f'--> Reentrenando con {count_feedback()} correcciones de administradores...')
  metrics = train_classic()
  print(' Modelos reentrenados exitosamente con el nuevo feedback.')
  return metrics
