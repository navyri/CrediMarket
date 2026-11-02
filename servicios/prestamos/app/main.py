"""Servicio Préstamos — decisión de riesgo, máquina de estados y modelo activo (§4, §8).

Este servicio DUEÑA el modelo de riesgo (§8): lo carga desde el artefacto
promovido explícitamente (`activo.json`), decide con su umbral y publica
`prestamo.reserva.solicitada`. Inventario es quien aprueba (reserva
confirmada); un resultado favorable del modelo NO es una aprobación (§4).
"""
import asyncio
import logging
import traceback
from contextlib import asynccontextmanager
from pathlib import Path

from alembic import command as alembic_command
from alembic.config import Config as AlembicConfig
from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from sqlalchemy import text

from . import broker, modelo, servicio
from .config import ajustes
from .db import Sesion, engine

logging.basicConfig(level=logging.INFO)

_RAIZ_SERVICIO = Path(__file__).resolve().parents[1]


def _aplicar_migraciones() -> None:
    cfg = AlembicConfig(str(_RAIZ_SERVICIO / "alembic.ini"))
    cfg.set_main_option("script_location", str(_RAIZ_SERVICIO / "alembic"))
    cfg.set_main_option("sqlalchemy.url", ajustes.database_url.replace("%", "%%"))
    alembic_command.upgrade(cfg, "head")
    logging.info("migraciones de prestamos aplicadas")


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
    servicio.procesar_evento(evento)


async def _bucle_recarga_modelo() -> None:
    """Recarga periódica del modelo activo (§8.D): una promoción o rollback
    fuera de banda (CLI) se refleja en el servicio sin reiniciar."""
    while True:
        try:
            await asyncio.sleep(ajustes.intervalo_recarga_modelo_seg)
            await asyncio.to_thread(modelo.recargar)
        except asyncio.CancelledError:
            raise
        except Exception as exc:                      # noqa: BLE001
            logging.warning("bucle de recarga de modelo: %s", exc)


@asynccontextmanager
async def arrancar(aplicacion: FastAPI):
    _aplicar_migraciones()
    await asyncio.to_thread(modelo.recargar)
    pendiente_broker = True

    async def _reintentar_broker() -> None:
        """Reconexión del consumidor si RabbitMQ no estaba listo al arrancar."""
        nonlocal pendiente_broker
        while pendiente_broker:
            try:
                await broker.arrancar_consumidor(_procesar)
                await broker.arrancar_relay_outbox(_consultar_outbox, _marcar_outbox)
                logging.info("broker conectado tras reconexión")
                return
            except Exception as exc:                  # noqa: BLE001
                logging.warning("broker aún no disponible: %s (reintento en 5s)", exc)
                await asyncio.sleep(5)

    try:
        await broker.arrancar_consumidor(_procesar)
        await broker.arrancar_relay_outbox(_consultar_outbox, _marcar_outbox)
        pendiente_broker = False
    except Exception as exc:                          # noqa: BLE001
        # Sin broker el servicio sigue respondiendo (su /ready lo refleja).
        logging.warning("broker no disponible al arrancar: %s", exc)
    tarea_broker = asyncio.create_task(_reintentar_broker())
    tarea_recarga = asyncio.create_task(_bucle_recarga_modelo())
    try:
        yield
    finally:
        pendiente_broker = False
        tarea_broker.cancel()
        tarea_recarga.cancel()
        await broker.cerrar()


app = FastAPI(
    title="CrediMarket · Préstamos",
    version="1.0.0",
    description="Decisión de riesgo con modelo activo, máquina de estados T1–T9 "
                "e idempotencia por Idempotency-Key (§4, §8, §9).",
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
    # format_exception con el propio exc: `logging.exception` pierde el
    # traceback si el handler se invoca fuera del bloque except.
    traza = "".join(traceback.format_exception(type(exc), exc, exc.__traceback__))
    logging.error("error no controlado en %s:\n%s", request.url.path, traza)
    return JSONResponse(
        status_code=500,
        content={"type": "about:blank", "title": "Error interno", "status": 500,
                 "detail": "fallo inesperado del servicio", "instance": str(request.url.path)},
        media_type="application/problem+json",
    )


@app.get("/health", tags=["operacion"])
def health():
    return {"servicio": ajustes.servicio_nombre, "estado": "ok",
            "modelo_activo": modelo.ficha_activa().get("modelo_version")
            if modelo.ficha_activa() else None}


@app.get("/ready", tags=["operacion"])
def ready():
    """§8.E: 503 si el modelo no cargó (sin modelo no se decide nada)."""
    estado = {"servicio": ajustes.servicio_nombre, "bd": False,
              "broker": False, "modelo": False}
    try:
        with engine.connect() as conn:
            conn.execute(text("SELECT 1"))
        estado["bd"] = True
    except Exception:                                 # noqa: BLE001
        estado["detalle"] = "base de datos no disponible"
        return JSONResponse(status_code=503, content=estado)
    if not modelo.disponible():
        estado["detalle"] = (f"sin modelo activo: "
                             f"{modelo.error_carga() or 'modelo no cargado'}")
        return JSONResponse(status_code=503, content=estado)
    estado["modelo"] = True
    try:
        estado["broker"] = broker._conexion is not None and not broker._conexion.is_closed
    except Exception:                                 # noqa: BLE001
        estado["broker"] = False
    if not estado["broker"]:
        estado["detalle"] = "broker no conectado (el outbox conserva los mensajes)"
        return JSONResponse(status_code=503, content=estado)
    estado["detalle"] = "listo"
    return estado
