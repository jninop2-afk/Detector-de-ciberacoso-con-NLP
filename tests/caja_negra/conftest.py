"""Configuración de las pruebas de caja negra.

Las pruebas de caja negra se diseñan a partir de la ESPECIFICACIÓN (README:
categorías 0-4, reglas de sanción, comandos de los bots), sin mirar cómo está
implementado el código. Sólo se usan las entradas y salidas públicas.
"""

import pytest


def pytest_configure(config):
  config.addinivalue_line(
      'markers', 'caja_negra: pruebas de caja negra derivadas de la especificación'
  )


def pytest_collection_modifyitems(items):
  for item in items:
    if '/caja_negra/' in str(item.fspath).replace('\\', '/'):
      item.add_marker(pytest.mark.caja_negra)
