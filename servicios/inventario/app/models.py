"""Modelo propio del servicio Inventario (esquema `inventario`)."""
import uuid
from datetime import datetime, timezone

from sqlalchemy import (
    CheckConstraint,
    DateTime,
    ForeignKey,
    Integer,
    JSON,
    String,
    Text,
)
from sqlalchemy.orm import Mapped, mapped_column

from .db import Base


def _ahora() -> datetime:
    return datetime.now(timezone.utc)


def nuevo_id() -> str:
    return str(uuid.uuid4())


class Existencia(Base):
    """Existencias por producto. Invariante: 0 <= reservada <= total (CHECK)."""

    __tablename__ = "existencia"
    __table_args__ = (
        CheckConstraint("reservada >= 0", name="ck_existencia_reservada_no_negativa"),
        CheckConstraint("total >= reservada", name="ck_existencia_total_no_menor"),
        {"schema": "inventario"},
    )

    producto_id: Mapped[str] = mapped_column(String(36), primary_key=True)
    total: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    reservada: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    actualizado_en: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=_ahora, onupdate=_ahora
    )


class Reserva(Base):
    __tablename__ = "reserva"
    __table_args__ = (
        CheckConstraint("cantidad > 0", name="ck_reserva_cantidad_positiva"),
        {"schema": "inventario"},
    )
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=nuevo_id)
    prestamo_id: Mapped[str] = mapped_column(String(36), nullable=False, index=True)
    producto_id: Mapped[str] = mapped_column(String(36), nullable=False, index=True)
    cantidad: Mapped[int] = mapped_column(Integer, nullable=False)
    # RESERVADA | ENTREGADA | LIBERADA | VENCIDA (los estados no-RESERVADA son finales)
    estado: Mapped[str] = mapped_column(String(20), nullable=False, default="RESERVADA")
    vence_en: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    creada_en: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False,
                                                default=_ahora)
    actualizada_en: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False,
                                                     default=_ahora, onupdate=_ahora)


class Movimiento(Base):
    __tablename__ = "movimiento"
    __table_args__ = {"schema": "inventario"}

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=nuevo_id)
    # ENTRADA | SALIDA | RESERVA | LIBERACION | VENCIMIENTO
    tipo: Mapped[str] = mapped_column(String(20), nullable=False)
    producto_id: Mapped[str] = mapped_column(String(36), nullable=False, index=True)
    cantidad: Mapped[int] = mapped_column(Integer, nullable=False)
    referencia: Mapped[str | None] = mapped_column(String(36), nullable=True)
    detalle: Mapped[str | None] = mapped_column(Text, nullable=True)
    creado_en: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False,
                                                default=_ahora)


class EventoProcesado(Base):
    """Deduplicación durable por `event_id` (§5.3, P2-REQ-038)."""

    __tablename__ = "evento_procesado"
    __table_args__ = {"schema": "inventario"}

    event_id: Mapped[str] = mapped_column(String(36), primary_key=True)
    tipo: Mapped[str] = mapped_column(String(80), nullable=False)
    prestamo_id: Mapped[str | None] = mapped_column(String(36), nullable=True)
    procesado_en: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False,
                                                   default=_ahora)


class Outbox(Base):
    """Outbox transaccional (P2-REQ-039): se escribe en la MISMA transacción del efecto."""

    __tablename__ = "outbox"
    __table_args__ = {"schema": "inventario"}

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=nuevo_id)
    routing_key: Mapped[str] = mapped_column(String(120), nullable=False)
    mensaje: Mapped[dict] = mapped_column(JSON, nullable=False)
    creado_en: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False,
                                                default=_ahora)
    publicado_en: Mapped[datetime | None] = mapped_column(DateTime(timezone=True),
                                                          nullable=True)
