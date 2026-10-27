"""Sesión y motor de PostgreSQL (esquema `inventario`, credencial restringida)."""
from collections.abc import Generator

from sqlalchemy import create_engine
from sqlalchemy.orm import DeclarativeBase, Session, sessionmaker

from .config import ajustes


class Base(DeclarativeBase):
    pass


engine = create_engine(ajustes.database_url, pool_pre_ping=True, pool_size=5, max_overflow=5)

Sesion = sessionmaker(bind=engine, autoflush=False, expire_on_commit=False)


def obtener_sesion() -> Generator[Session, None, None]:
    sesion = Sesion()
    try:
        yield sesion
    finally:
        sesion.close()
