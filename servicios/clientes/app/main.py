"""Servicio Clientes — datos de clientes, importación CSV e identidad (JWT)."""
import logging
from pathlib import Path

from alembic import command as alembic_command
from alembic.config import Config as AlembicConfig
from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from sqlalchemy import text

from .config import ajustes
from .db import Base, Sesion, engine
from .routes import router

logging.basicConfig(level=logging.INFO)

app = FastAPI(
    title="CrediMarket · Clientes",
    version="1.0.0",
    description="Datos de clientes, importación CSV idempotente e identidad del sistema (§9).",
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
    """Migraciones Alembic al arrancar (solo sobre el esquema `clientes`, §3)."""
    cfg = AlembicConfig(str(_RAIZ_SERVICIO / "alembic.ini"))
    cfg.set_main_option("script_location", str(_RAIZ_SERVICIO / "alembic"))
    cfg.set_main_option("sqlalchemy.url", ajustes.database_url.replace("%", "%%"))
    alembic_command.upgrade(cfg, "head")
    logging.info("migraciones de clientes aplicadas")


@app.on_event("startup")
def arrancar() -> None:
    _aplicar_migraciones()
    _sembrar_administrador()


def _sembrar_administrador() -> None:
    """Cuenta de demostración (§9: tokens de prueba de forma controlada).

    Solo crea la cuenta si no existe; la contraseña sale de la variable de
    entorno ADMIN_PASSWORD (gitignored), nunca del código ni del repo.
    """
    from .models import Usuario
    from .security import hash_password, usuario_por_email

    sesion = None
    try:
        sesion = Sesion()
        if usuario_por_email(sesion, ajustes.admin_email) is None:
            sesion.add(Usuario(email=ajustes.admin_email.strip().lower(),
                               rol="administrador",
                               password_hash=hash_password(ajustes.admin_password),
                               cliente_id=None))
            sesion.commit()
            logging.info("cuenta administradora de demo creada: %s", ajustes.admin_email)
        else:
            logging.info("cuenta administradora ya presente: %s", ajustes.admin_email)
    finally:
        if sesion is not None:
            sesion.close()


@app.exception_handler(RequestValidationError)
def validacion(request: Request, exc: RequestValidationError):
    errores = [{"campo": ".".join(str(p) for p in e["loc"] if p != "body"),
                "mensaje": e["msg"]} for e in exc.errors()]
    return JSONResponse(
        status_code=400,
        content={"type": "about:blank", "title": "Solicitud inválida", "status": 400,
                 "detail": "validación de entrada", "instance": str(request.url.path),
                 "errors": errores},
        media_type="application/problem+json",
    )


@app.exception_handler(Exception)
def error_interno(request: Request, exc: Exception):
    logging.exception("error no controlado en %s", request.url.path)
    return JSONResponse(
        status_code=500,
        content={"type": "about:blank", "title": "Error interno", "status": 500,
                 "detail": "fallo inesperado del servicio", "instance": str(request.url.path)},
        media_type="application/problem+json",
    )


@app.get("/health", tags=["operacion"])
def health():
    return {"servicio": ajustes.servicio_nombre, "estado": "ok"}


@app.get("/ready", tags=["operacion"])
def ready():
    try:
        with engine.connect() as conn:
            conn.execute(text("SELECT 1"))
        return {"servicio": ajustes.servicio_nombre, "bd": True}
    except Exception:
        return JSONResponse(status_code=503,
                            content={"servicio": ajustes.servicio_nombre, "bd": False,
                                     "detalle": "base de datos no disponible"})
