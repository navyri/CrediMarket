"""Esquemas Pydantic del servicio Clientes."""
from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field, field_validator

CLAVE_CLIENTES = r"[^@\s]+@[^@\s]+\.[^@\s]+$"


class ClienteCreacion(BaseModel):
    documento_identidad: str = Field(min_length=1, max_length=30)
    nombre: str = Field(min_length=1, max_length=160)
    email: str = Field(max_length=160, pattern=CLAVE_CLIENTES)
    telefono: str | None = Field(default=None, max_length=30)
    ciudad: str | None = Field(default=None, max_length=80)
    activo: bool = True


class ClienteActualizacion(BaseModel):
    nombre: str | None = Field(default=None, min_length=1, max_length=160)
    email: str | None = Field(default=None, max_length=160, pattern=CLAVE_CLIENTES)
    telefono: str | None = Field(default=None, max_length=30)
    ciudad: str | None = Field(default=None, max_length=80)
    activo: bool | None = None


class ClienteLectura(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    documento_identidad: str
    nombre: str
    email: str
    telefono: str | None
    ciudad: str | None
    activo: bool
    creado_en: datetime
    actualizado_en: datetime


class ClienteLista(BaseModel):
    total: int
    items: list[ClienteLectura]


class Registro(BaseModel):
    email: str = Field(max_length=160, pattern=CLAVE_CLIENTES)
    password: str = Field(min_length=8, max_length=72)   # bcrypt admite hasta 72 bytes
    documento_identidad: str = Field(min_length=1, max_length=30)
    nombre: str = Field(min_length=1, max_length=160)
    telefono: str | None = Field(default=None, max_length=30)
    ciudad: str | None = Field(default=None, max_length=80)


class Login(BaseModel):
    email: str = Field(max_length=160, pattern=CLAVE_CLIENTES)
    password: str = Field(max_length=72)


class Token(BaseModel):
    access_token: str
    token_type: str = "bearer"
    rol: str
    cliente_id: str | None
    exp: int


class ErrorImportacion(BaseModel):
    fila: int
    motivo: str


class ResultadoImportacion(BaseModel):
    archivo: str
    procesadas: int
    insertados: int
    actualizados: int
    sin_cambios: int
    rechazadas: int
    errores: list[ErrorImportacion]


class CredencialesUsuario(BaseModel):
    """Validación interna de credenciales (uso del token de servicio de Préstamos)."""

    model_config = ConfigDict(from_attributes=True)

    id: str
    email: str
    rol: str
    cliente_id: str | None = None

    @field_validator("email")
    @classmethod
    def _no_vacio(cls, v: str) -> str:
        if not v:
            raise ValueError("email vacío")
        return v
