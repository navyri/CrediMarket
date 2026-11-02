"""Modelo propio del servicio Préstamos (esquema `prestamos`).

El préstamo guarda la decisión completa (§4): probabilidad, umbral,
`modelo_version`, precio y versión de cotización usados. `solicitud_idempotente`
hace efectiva la cabecera `Idempotency-Key` (§9).
"""
import uuid
from datetime import datetime, timezone

from sqlalchemy import DateTime, Float, Integer, JSON, Numeric, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from .db import Base


def _ahora() -> datetime:
    return datetime.now(timezone.utc)


def nuevo_id() -> str:
    return str(uuid.uuid4())


class Prestamo(Base):
    __tablename__ = "prestamo"
    __table_args__ = {"schema": "prestamos"}

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=nuevo_id)
    cliente_id: Mapped[str] = mapped_column(String(36), nullable=False, index=True)
    producto_id: Mapped[str] = mapped_column(String(36), nullable=False)
    cantidad: Mapped[int] = mapped_column(Integer, nullable=False)
    plazo_meses: Mapped[int] = mapped_column(Integer, nullable=False)

    # Fuente de verdad: precio leído de Productos (BD), nunca del cliente (§4).
    precio_unitario_cop: Mapped[float] = mapped_column(Numeric(14, 2), nullable=False)
    precio_producto_version: Mapped[int] = mapped_column(Integer, nullable=False)
    monto_total_cop: Mapped[float] = mapped_column(Numeric(14, 2), nullable=False)
    cuota_mensual_cop: Mapped[float] = mapped_column(Numeric(14, 2), nullable=False)
    tasa_mensual: Mapped[float] = mapped_column(Float, nullable=False)

    # Decisión del modelo (§8.B): la probabilidad es de incumplimiento_90d.
    probabilidad_incumplimiento: Mapped[float] = mapped_column(Float, nullable=False)
    umbral: Mapped[float] = mapped_column(Float, nullable=False)
    modelo_version: Mapped[str] = mapped_column(String(20), nullable=False)
    run_id: Mapped[str | None] = mapped_column(String(40), nullable=True)

    # PENDIENTE_INVENTARIO | RECHAZADA | APROBADA | CANCELADA_SIN_STOCK |
    # CANCELADA | CANCELADA_VENCIDA | COMPLETADA  (máquina de estados §4).
    estado: Mapped[str] = mapped_column(String(30), nullable=False, index=True)
    motivo: Mapped[str | None] = mapped_column(Text, nullable=True)
    reserva_id: Mapped[str | None] = mapped_column(String(36), nullable=True)
    # Marca de cancelación en vuelo: T7 solo termina al recibir `liberada`.
    cancelacion_solicitada_en: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True)

    creado_en: Mapped[datetime] = mapped_column(DateTime(timezone=True),
                                                nullable=False, default=_ahora)
    actualizado_en: Mapped[datetime] = mapped_column(DateTime(timezone=True),
                                                     nullable=False, default=_ahora,
                                                     onupdate=_ahora)
    decidido_en: Mapped[datetime] = mapped_column(DateTime(timezone=True),
                                                  nullable=False, default=_ahora)


class SolicitudIdempotente(Base):
    """§9: misma `Idempotency-Key` + mismo cuerpo → misma respuesta; distinta → 409."""

    __tablename__ = "solicitud_idempotente"
    __table_args__ = {"schema": "prestamos"}

    idempotency_key: Mapped[str] = mapped_column(String(80), primary_key=True)
    huella_cuerpo: Mapped[str] = mapped_column(String(64), nullable=False)
    prestamo_id: Mapped[str | None] = mapped_column(String(36), nullable=True)
    respuesta: Mapped[dict] = mapped_column(JSON, nullable=False)
    status_code: Mapped[int] = mapped_column(Integer, nullable=False)
    creada_en: Mapped[datetime] = mapped_column(DateTime(timezone=True),
                                                nullable=False, default=_ahora)


class EventoProcesado(Base):
    """Deduplicación durable por `event_id` (§5.3)."""

    __tablename__ = "evento_procesado"
    __table_args__ = {"schema": "prestamos"}

    event_id: Mapped[str] = mapped_column(String(36), primary_key=True)
    tipo: Mapped[str] = mapped_column(String(80), nullable=False)
    prestamo_id: Mapped[str | None] = mapped_column(String(36), nullable=True)
    procesado_en: Mapped[datetime] = mapped_column(DateTime(timezone=True),
                                                   nullable=False, default=_ahora)


class Outbox(Base):
    """Outbox transaccional (P2-REQ-039): mismo commit que el efecto local."""

    __tablename__ = "outbox"
    __table_args__ = {"schema": "prestamos"}

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=nuevo_id)
    routing_key: Mapped[str] = mapped_column(String(120), nullable=False)
    mensaje: Mapped[dict] = mapped_column(JSON, nullable=False)
    creado_en: Mapped[datetime] = mapped_column(DateTime(timezone=True),
                                                nullable=False, default=_ahora)
    publicado_en: Mapped[datetime | None] = mapped_column(DateTime(timezone=True),
                                                          nullable=True)
