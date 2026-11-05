# language: es
Característica: Moderación automática en Discord
  Como moderador de un servidor de Discord
  quiero que el bot detecte y sancione el ciberacoso de forma automática y privada
  para proteger a los miembros sin exponer públicamente a nadie

  Antecedentes:
    Dado un servidor de Discord con el bot configurado y un canal privado de moderación

  Escenario: HU-01 Un insulto se elimina y se informa en privado
    Cuando un usuario escribe "eres un hijueputa inútil"
    Entonces el mensaje se elimina
    Y el usuario recibe una advertencia por mensaje privado
    Y los moderadores reciben el reporte en el canal privado
    Y no se publica ningún aviso en el canal público

  Escenario: HU-02 Las conversaciones normales no se interrumpen
    Cuando un usuario escribe "buenos días a todos, feliz semana"
    Entonces el mensaje no se elimina
    Y los moderadores no reciben ningún reporte

  Escenario: HU-03 Quien reincide 4 veces seguidas queda bloqueado
    Cuando un usuario escribe 4 mensajes ofensivos seguidos
    Entonces el usuario queda silenciado en Discord
    Y sus siguientes mensajes se eliminan aunque sean normales

  Escenario: HU-04 Un humano decide los casos dudosos
    Cuando un usuario escribe un mensaje que el detector considera dudoso
    Entonces el mensaje no se elimina
    Y los moderadores reciben una solicitud de revisión con un botón por categoría
    Cuando un moderador lo clasifica como "Insultos y ofensas personales"
    Entonces su decisión queda guardada para reentrenar el modelo
