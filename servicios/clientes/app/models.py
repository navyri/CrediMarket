"""Modelo propio del servicio Clientes (esquema `clientes`): cliente y usuario."""
import uuid
from datetime import datetime, timezone

from sqlalchemy import Boolean, DateTime, ForeignKey, String, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column, relationship

from .db import Base


def _ahora() -> datetime:
    return datetime.now(timezone.utc)


def nuevo_id() -> str:
    return str(uuid.uuid4())


class Cliente(Base):
    __tablename__ = "cliente"
    __table_args__ = (
        # Clave externa única (P2-SUP-006): es la que usa la importación CSV.
        UniqueConstraint("documento_identidad", name="uq_cliente_documento"),
        {"schema": "clientes"},
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=nuevo_id)
    documento_identidad: Mapped[str] = mapped_column(String(30), nullable=False, index=True)
    nombre: Mapped[str] = mapped_column(String(160), nullable=False)
    email: Mapped[str] = mapped_column(String(160), nullable=False, unique=True)
    telefono: Mapped[str | None] = mapped_column(String(30), nullable=True)
    ciudad: Mapped[str | None] = mapped_column(String(80), nullable=True)
    activo: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    creado_en: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False,
                                                default=_ahora)
    actualizado_en: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False,
                                                     default=_ahora, onupdate=_ahora)

    usuarios: Mapped[list["Usuario"]] = relationship(back_populates="cliente")


class Usuario(Base):
    __tablename__ = "usuario"
    __table_args__ = {"schema": "clientes"}

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=nuevo_id)
    email: Mapped[str] = mapped_column(String(160), nullable=False, unique=True)
    password_hash: Mapped[str] = mapped_column(String(200), nullable=False)
    rol: Mapped[str] = mapped_column(String(20), nullable=False, default="cliente")
    cliente_id: Mapped[str | None] = mapped_column(
        String(36), ForeignKey("clientes.cliente.id", ondelete="CASCADE"), nullable=True
    )
    creado_en: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False,
                                                default=_ahora)

    cliente: Mapped[Cliente | None] = relationship(back_populates="usuarios")
