"""Esquemas Pydantic del servicio Clientes.

Incluye el perfil financiero del cliente (P2-7): el histórico de Préstamos
tiene `cliente_id` único por fila, así que el perfil pertenece al cliente y
este servicio es su dueño. Préstamos lo consume por API para armar el vector
de variables del modelo de riesgo (§4).
"""
from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field, field_validator

CLAVE_CLIENTES = r"[^@\s]+@[^@\s]+\.[^@\s]+$"

# Columnas del perfil financiero (compartidas por creación, actualización,
# importación CSV y lectura).
PERFIL_FINANCIERO: dict[str, type] = {
    "ingresos_mensuales_cop": float,
    "obligaciones_mensuales_cop": float,
    "tipo_empleo": str,
    "antiguedad_laboral_meses": float,
    "meses_historial_crediticio": float,
    "creditos_previos": int,
    "atrasos_previos_30d": int,
    "porcentaje_pago_puntual": float,
}


class ClienteCreacion(BaseModel):
    documento_identidad: str = Field(min_length=1, max_length=30)
    nombre: str = Field(min_length=1, max_length=160)
    email: str = Field(max_length=160, pattern=CLAVE_CLIENTES)
    telefono: str | None = Field(default=None, max_length=30)
    ciudad: str | None = Field(default=None, max_length=80)
    activo: bool = True

    ingresos_mensuales_cop: float | None = Field(default=None, gt=0)
    obligaciones_mensuales_cop: float | None = Field(default=None, ge=0)
    tipo_empleo: str | None = Field(default=None, max_length=40)
    antiguedad_laboral_meses: float | None = Field(default=None, ge=0)
    meses_historial_crediticio: float | None = Field(default=None, ge=0)
    creditos_previos: int | None = Field(default=None, ge=0)
    atrasos_previos_30d: int | None = Field(default=None, ge=0)
    porcentaje_pago_puntual: float | None = Field(default=None, ge=0, le=100)


class ClienteActualizacion(BaseModel):
    nombre: str | None = Field(default=None, min_length=1, max_length=160)
    email: str | None = Field(default=None, max_length=160, pattern=CLAVE_CLIENTES)
    telefono: str | None = Field(default=None, max_length=30)
    ciudad: str | None = Field(default=None, max_length=80)
    activo: bool | None = None

    ingresos_mensuales_cop: float | None = Field(default=None, gt=0)
    obligaciones_mensuales_cop: float | None = Field(default=None, ge=0)
    tipo_empleo: str | None = Field(default=None, max_length=40)
    antiguedad_laboral_meses: float | None = Field(default=None, ge=0)
    meses_historial_crediticio: float | None = Field(default=None, ge=0)
    creditos_previos: int | None = Field(default=None, ge=0)
    atrasos_previos_30d: int | None = Field(default=None, ge=0)
    porcentaje_pago_puntual: float | None = Field(default=None, ge=0, le=100)


class ClienteLectura(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    documento_identidad: str
    nombre: str
    email: str
    telefono: str | None
    ciudad: str | None
    activo: bool

    ingresos_mensuales_cop: float | None = None
    obligaciones_mensuales_cop: float | None = None
    tipo_empleo: str | None = None
    antiguedad_laboral_meses: float | None = None
    meses_historial_crediticio: float | None = None
    creditos_previos: int | None = None
    atrasos_previos_30d: int | None = None
    porcentaje_pago_puntual: float | None = None

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
