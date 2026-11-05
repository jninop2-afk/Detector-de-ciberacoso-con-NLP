# language: es
Característica: Calidad de la detección
  Como responsable del proyecto
  quiero que el detector entienda el español colombiano de las redes sociales
  para que las sanciones sean justas y no se castigue a quien no lo merece

  Esquema del escenario: HU-09 Cada tipo de acoso se reconoce
    Cuando el detector analiza "<mensaje>"
    Entonces lo clasifica como "<categoria>"

    Ejemplos:
      | mensaje                                  | categoria                                |
      | te voy a matar cuando te vea             | Hostigamiento y amenazas directas        |
      | eres un hijueputa inútil                 | Insultos y ofensas personales            |
      | ojalá te mueras desgraciado              | Incitación al odio y muerte              |
      | el alcalde se robó la plata de los niños | Difamación, calumnia y ataques políticos |
      | buenos días a todos                      | Sin ciberacoso                           |

  Esquema del escenario: HU-10 Disfrazar el insulto no evita la detección
    Cuando el detector analiza "<mensaje>"
    Entonces lo detecta como ciberacoso

    Ejemplos:
      | mensaje             |
      | 3r3s un 1nut1l      |
      | hp mlp gonorrea     |
      | ERES UN ESTÚPIDO    |
      | eres un idiotaaaaaa |
      | @juan eres un imbécil |

  Escenario: HU-11 Se alcanza el acierto mínimo acordado
    Cuando el detector analiza el conjunto de aceptación
    Entonces acierta si es acoso o no en al menos el 90 % de los mensajes
    Y acierta la categoría en al menos el 85 % de los mensajes

  Escenario: HU-12 La respuesta es en tiempo real
    Cuando el detector analiza 500 mensajes seguidos
    Entonces el tiempo promedio por mensaje es menor a 100 ms
