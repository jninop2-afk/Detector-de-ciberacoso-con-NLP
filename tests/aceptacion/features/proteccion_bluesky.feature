# language: es
Característica: Protección contra el ciberacoso en Bluesky
  Como usuario de Bluesky que recibe acoso
  quiero que el bot analice mensajes y revise las respuestas a mis publicaciones
  para enterarme del acoso sin tener que leerlo todo yo

  Escenario: HU-05 Consultar si un mensaje es acoso
    Cuando menciono al bot con "eres un inútil, nadie te quiere"
    Entonces el bot me responde que detectó posible ciberacoso
    Y la respuesta indica la categoría y la confianza
    Y la respuesta cabe en un post de Bluesky

  Escenario: HU-06 Activar la vigilancia de mi cuenta
    Cuando menciono al bot con "vigilar"
    Y alguien responde "ojalá te mueras basura" a una de mis publicaciones
    Entonces el bot registra esa respuesta como ciberacoso
    Y el bot no publica nada en esa conversación

  Escenario: HU-07 Desactivar la vigilancia
    Dado que pedí la vigilancia de mi cuenta
    Cuando menciono al bot con "dejar de vigilar"
    Y alguien responde "ojalá te mueras basura" a una de mis publicaciones
    Entonces el bot no registra nada

  Escenario: HU-08 Reportar sin enviar reportes reales mientras se prueba
    Cuando menciono al bot con "reportar te voy a matar cuando te vea"
    Entonces el bot confirma que lo habría reportado
    Y no se envía ningún reporte real a Bluesky
