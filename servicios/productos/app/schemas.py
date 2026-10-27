"""Esquemas Pydantic de entrada/salida del servicio Productos."""
from datetime import datetime
from decimal import Decimal

from pydantic import BaseModel, ConfigDict, Field


class ProductoCreacion(BaseModel):
    sku: str = Field(min_length=1, max_length=40)
    nombre: str = Field(min_length=1, max_length=200)
    categoria: str = Field(min_length=1, max_length=80)
    descripcion: str | None = Field(default=None, max_length=2000)
    precio_cop: Decimal = Field(gt=0, max_digits=14, decimal_places=2)


class ProductoActualizacion(BaseModel):
    nombre: str | None = Field(default=None, min_length=1, max_length=200)
    categoria: str | None = Field(default=None, min_length=1, max_length=80)
    descripcion: str | None = Field(default=None, max_length=2000)
    precio_cop: Decimal | None = Field(default=None, gt=0, max_digits=14, decimal_places=2)


class ProductoLectura(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    sku: str
    nombre: str
    categoria: str
    descripcion: str | None
    precio_cop: Decimal
    activo: bool
    version: int
    creado_en: datetime
    actualizado_en: datetime


class ProductoLista(BaseModel):
    total: int
    pagina: int
    tamano: int
    items: list[ProductoLectura]


class Cotizacion(BaseModel):
    """Fuente de verdad para Préstamos: leída de BD, nunca de la caché (§6)."""

    producto_id: str
    precio_cop: Decimal
    version: int
    vigente_desde: datetime
