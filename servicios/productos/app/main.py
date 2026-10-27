"""Servicio Productos — catálogo con caché Redis cache-aside (§6)."""
import logging
from pathlib import Path

from alembic import command as alembic_command
from alembic.config import Config as AlembicConfig
from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from sqlalchemy import text

from . import cache
from .config import ajustes
from .db import Base, engine
from .routes import router

logging.basicConfig(level=logging.INFO)

app = FastAPI(
    title="CrediMarket · Productos",
    version="1.0.0",
    description="Catálogo de productos con caché Redis cache-aside (§6).",
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=[o.strip() for o in ajustes.cors_origins.split(",") if o.strip()],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(router)

_RAIZ_SERVICIO = Path(__file__).resolve().parents[1]


def _aplicar_migraciones() -> None:
    """Migraciones Alembic al arrancar (sobre el esquema propio, §3)."""
    cfg = AlembicConfig(str(_RAIZ_SERVICIO / "alembic.ini"))
    cfg.set_main_option("script_location", str(_RAIZ_SERVICIO / "alembic"))
    cfg.set_main_option("sqlalchemy.url", ajustes.database_url.replace("%", "%%"))
    alembic_command.upgrade(cfg, "head")
    logging.info("migraciones de productos aplicadas")


@app.on_event("startup")
def arrancar() -> None:
    _aplicar_migraciones()


def _problem(status: int, titulo: str, detalle: str, instance: str) -> JSONResponse:
    return JSONResponse(
        status_code=status,
        content={"type": "about:blank", "title": titulo, "status": status,
                 "detail": detalle, "instance": instance},
        media_type="application/problem+json",
    )


@app.exception_handler(RequestValidationError)
def validacion(exc: RequestValidationError, request: Request):
    errores = [
        {"campo": ".".join(str(p) for p in e["loc"] if p != "body"), "mensaje": e["msg"]}
        for e in exc.errors()
    ]
    return JSONResponse(
        status_code=400,
        content={"type": "about:blank", "title": "Solicitud inválida", "status": 400,
                 "detail": "validación de entrada", "instance": str(request.url.path),
                 "errors": errores},
        media_type="application/problem+json",
    )


@app.exception_handler(Exception)
def error_interno(exc: Exception, request: Request):
    logging.exception("error no controlado en %s", request.url.path)
    return _problem(500, "Error interno", "fallo inesperado del servicio", str(request.url.path))


@app.get("/health", tags=["operacion"])
def health():
    """Proceso vivo: no depende de BD ni Redis."""
    return {"servicio": ajustes.servicio_nombre, "estado": "ok"}


@app.get("/ready", tags=["operacion"])
def ready(request: Request):
    """Listo: BD obligatoria; Redis reportado como degradado sin bloquear (§6 fallback)."""
    try:
        with engine.connect() as conn:
            conn.execute(text("SELECT 1"))
        bd = True
    except Exception:
        bd = False
    redis_ok = cache.redis_esta_disponible()
    if not bd:
        return JSONResponse(
            status_code=503,
            content={"servicio": ajustes.servicio_nombre, "bd": False, "redis": redis_ok,
                     "detalle": "base de datos no disponible"},
        )
    return {"servicio": ajustes.servicio_nombre, "bd": bd, "redis": redis_ok,
            "detalle": "listo" if redis_ok else "listo con caché degradada (fallback activo)"}
