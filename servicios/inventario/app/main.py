"""Servicio Inventario — reservas atómicas y mensajería confiable (§4, §5)."""
import asyncio
import logging
from contextlib import asynccontextmanager
from pathlib import Path

from alembic import command as alembic_command
from alembic.config import Config as AlembicConfig
from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from sqlalchemy import text

from . import broker, servicio
from .config import ajustes
from .db import Sesion, engine

logging.basicConfig(level=logging.INFO)

_RAIZ_SERVICIO = Path(__file__).resolve().parents[1]


def _aplicar_migraciones() -> None:
    cfg = AlembicConfig(str(_RAIZ_SERVICIO / "alembic.ini"))
    cfg.set_main_option("script_location", str(_RAIZ_SERVICIO / "alembic"))
    cfg.set_main_option("sqlalchemy.url", ajustes.database_url.replace("%", "%%"))
    alembic_command.upgrade(cfg, "head")
    logging.info("migraciones de inventario aplicadas")


def _consultar_outbox() -> list[dict]:
    sesion = Sesion()
    try:
        return servicio.outbox_pendiente(sesion)
    finally:
        sesion.close()


def _marcar_outbox(outbox_id: str) -> None:
    sesion = Sesion()
    try:
        servicio.outbox_marcar(sesion, outbox_id)
    finally:
        sesion.close()


def _procesar(evento: dict) -> None:
    servicio.procesar_comando(evento)


async def _bucle_vencimientos() -> None:
    """Tarea periódica de vencimiento (§4): libera y publica `reserva.vencida`."""
    while True:
        try:
            await asyncio.sleep(ajustes.intervalo_vencimiento_seg)
            def _expirar() -> int:
                sesion = Sesion()
                try:
                    return len(servicio.expirar_reservas(sesion))
                finally:
                    sesion.close()
            await asyncio.to_thread(_expirar)
        except asyncio.CancelledError:
            raise
        except Exception as exc:                      # noqa: BLE001
            logging.warning("bucle de vencimiento: %s", exc)


@asynccontextmanager
async def arrancar(aplicacion: FastAPI):
    _aplicar_migraciones()
    try:
        await broker.arrancar_consumidor(_procesar)
        await broker.arrancar_relay_outbox(_consultar_outbox, _marcar_outbox)
        tarea_vencimiento = asyncio.create_task(_bucle_vencimientos())
    except Exception as exc:                          # noqa: BLE001
        # Sin broker el servicio sigue respondiendo (su /ready lo refleja).
        logging.warning("broker no disponible al arrancar: %s", exc)
        tarea_vencimiento = asyncio.create_task(_bucle_vencimientos())
    try:
        yield
    finally:
        tarea_vencimiento.cancel()
        await broker.cerrar()


app = FastAPI(
    title="CrediMarket · Inventario",
    version="1.0.0",
    description="Reservas atómicas, vencimientos y eventos confiables sobre RabbitMQ (§4, §5).",
    lifespan=arrancar,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=[o.strip() for o in ajustes.cors_origins.split(",") if o.strip()],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

from .routes import router    # noqa: E402  (evita importación circular)

app.include_router(router)


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
    estado = {"servicio": ajustes.servicio_nombre, "bd": False, "broker": False}
    try:
        with engine.connect() as conn:
            conn.execute(text("SELECT 1"))
        estado["bd"] = True
    except Exception:                                 # noqa: BLE001
        estado["detalle"] = "base de datos no disponible"
        return JSONResponse(status_code=503, content=estado)
    try:
        estado["broker"] = broker._conexion is not None and not broker._conexion.is_closed
    except Exception:                                 # noqa: BLE001
        estado["broker"] = False
    if not estado["broker"]:
        estado["detalle"] = "broker no conectado (el outbox conserva los mensajes)"
        return JSONResponse(status_code=503, content=estado)
    estado["detalle"] = "listo"
    return estado
