from pydantic import BaseModel, Field

class SolicitudPrediccion(BaseModel):
    texto: str = Field(..., example="No sirves para nada, lárgate")

class RespuestaPrediccion(BaseModel):
    texto_original: str
    texto_limpio: str
    categoria_detectada: str
    probabilidad: float