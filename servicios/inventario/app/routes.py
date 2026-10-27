"""Rutas REST del servicio Inventario (contrato en docs/arquitectura/contratos-rest.md)."""
from datetime import datetime, timezone

from fastapi import APIRouter, Depends, Request
from pydantic import BaseModel, Field
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from .config import ajustes
from .db import obtener_sesion
from .models import Existencia, Movimiento, Reserva
from .security import rol_administrador, rol_interno
from . import servicio

router = APIRouter()


def _problema(status: int, titulo: str, detalle: str, instance: str):
    from fastapi.responses import JSONResponse
    return JSONResponse(
        status_code=status,
        content={"type": "about:blank", "title": titulo, "status": status,
                 "detail": detalle, "instance": instance},
        media_type="application/problem+json",
    )


class Entrada(BaseModel):
    producto_id: str = Field(min_length=1, max_length=36)
    cantidad: int = Field(gt=0, le=100000)
    referencia: str | None = Field(default=None, max_length=36)


class ExistenciaLectura(BaseModel):
    producto_id: str
    total: int
    reservada: int
    disponible: int
    actualizado_en: datetime


class ReservaLectura(BaseModel):
    model_config = {"from_attributes": True}

    id: str
    prestamo_id: str
    producto_id: str
    cantidad: int
    estado: str
    vence_en: datetime
    creada_en: datetime


class MovimientoLectura(BaseModel):
    model_config = {"from_attributes": True}

    id: str
    tipo: str
    producto_id: str
    cantidad: int
    referencia: str | None
    detalle: str | None
    creado_en: datetime


def _a_lectura(e: Existencia) -> ExistenciaLectura:
    return ExistenciaLectura(producto_id=e.producto_id, total=e.total,
                             reservada=e.reservada, disponible=e.total - e.reservada,
                             actualizado_en=e.actualizado_en)


@router.get("/existencias", response_model=list[ExistenciaLectura])
def listar_existencias(sesion: Session = Depends(obtener_sesion),
                       _auth: dict = Depends(rol_administrador)):
    filas = sesion.scalars(select(Existencia).order_by(Existencia.producto_id)).all()
    return [_a_lectura(f) for f in filas]


@router.get("/existencias/{producto_id}", response_model=ExistenciaLectura)
def obtener_existencia(producto_id: str, request: Request,
                       sesion: Session = Depends(obtener_sesion),
                       _auth: dict = Depends(rol_administrador)):
    existencia = sesion.get(Existencia, producto_id)
    if existencia is None:
        return _problema(404, "Recurso no encontrado",
                         f"no hay existencias registradas para {producto_id}",
                         str(request.url.path))
    return _a_lectura(existencia)


@router.post("/entradas", response_model=ExistenciaLectura, status_code=201)
def registrar_entrada(cuerpo: Entrada, request: Request,
                      sesion: Session = Depends(obtener_sesion),
                      _auth: dict = Depends(rol_administrador)):
    existencia = servicio.entrada(sesion, cuerpo.producto_id, cuerpo.cantidad,
                                  cuerpo.referencia)
    return _a_lectura(existencia)


@router.get("/reservas", response_model=list[ReservaLectura])
def listar_reservas(estado: str | None = None, limite: int = 100,
                    sesion: Session = Depends(obtener_sesion),
                    _auth: dict = Depends(rol_interno)):
    consulta = select(Reserva).order_by(Reserva.creada_en.desc()).limit(limite)
    if estado:
        consulta = consulta.where(Reserva.estado == estado)
    return [ReservaLectura.model_validate(r)
            for r in sesion.scalars(consulta).all()]


@router.get("/reservas/{reserva_id}", response_model=ReservaLectura)
def obtener_reserva(reserva_id: str, request: Request,
                    sesion: Session = Depends(obtener_sesion),
                    _auth: dict = Depends(rol_interno)):
    reserva = sesion.get(Reserva, reserva_id)
    if reserva is None:
        return _problema(404, "Recurso no encontrado", "reserva inexistente",
                         str(request.url.path))
    return ReservaLectura.model_validate(reserva)


@router.post("/reservas/{reserva_id}/entrega", response_model=ReservaLectura)
def confirmar_entrega(reserva_id: str, request: Request,
                      sesion: Session = Depends(obtener_sesion),
                      _auth: dict = Depends(rol_administrador)):
    """Entrega simulada: descuenta stock y encola `inventario.salida.confirmada`."""
    try:
        reserva, _evento = servicio.entregar(sesion, reserva_id)
    except LookupError:
        return _problema(404, "Recurso no encontrado", "reserva inexistente",
                         str(request.url.path))
    except servicio.EntregaYaConfirmada as exc:
        return _problema(409, "Conflicto", str(exc), str(request.url.path))
    except ValueError as exc:
        # Carrera: una reserva ya liberada no admite entrega (§4).
        return _problema(409, "Conflicto", str(exc), str(request.url.path))
    except RuntimeError as exc:
        return _problema(409, "Conflicto", str(exc), str(request.url.path))
    return ReservaLectura.model_validate(reserva)


@router.post("/reservas/{reserva_id}/liberar", response_model=ReservaLectura)
def liberar_reserva_manual(reserva_id: str, request: Request,
                           sesion: Session = Depends(obtener_sesion),
                           _auth: dict = Depends(rol_administrador)):
    reserva = sesion.get(Reserva, reserva_id)
    if reserva is None:
        return _problema(404, "Recurso no encontrado", "reserva inexistente",
                         str(request.url.path))
    if reserva.estado != "RESERVADA":
        return _problema(409, "Conflicto",
                         f"la reserva está en estado {reserva.estado}",
                         str(request.url.path))
    liberada = servicio._liberar_reserva(sesion, reserva.prestamo_id,
                                         origen="liberacion_manual")
    from .broker import construir_evento
    from .models import Outbox
    sesion.add(Outbox(
        routing_key="inventario.reserva.liberada",
        mensaje=construir_evento(
            "inventario.reserva.liberada", reserva.prestamo_id, reserva.prestamo_id,
            {"prestamo_id": reserva.prestamo_id, "reserva_id": liberada,
             "origen": "liberacion_manual"}),
    ))
    sesion.commit()
    sesion.refresh(reserva)
    return ReservaLectura.model_validate(reserva)


@router.get("/movimientos", response_model=list[MovimientoLectura])
def listar_movimientos(limite: int = 100, sesion: Session = Depends(obtener_sesion),
                       _auth: dict = Depends(rol_administrador)):
    filas = sesion.scalars(select(Movimiento).order_by(Movimiento.creado_en.desc())
                           .limit(limite)).all()
    return [MovimientoLectura.model_validate(f) for f in filas]


@router.get("/eventos/procesados")
def eventos_procesados(limite: int = 50, sesion: Session = Depends(obtener_sesion),
                       _auth: dict = Depends(rol_interno)):
    from .models import EventoProcesado
    filas = sesion.scalars(select(EventoProcesado)
                           .order_by(EventoProcesado.procesado_en.desc())
                           .limit(limite)).all()
    return [{"event_id": f.event_id, "tipo": f.tipo, "prestamo_id": f.prestamo_id,
             "procesado_en": f.procesado_en.isoformat()} for f in filas]


@router.get("/outbox/pendiente")
def outbox_pendiente(limite: int = 50, sesion: Session = Depends(obtener_sesion),
                     _auth: dict = Depends(rol_interno)):
    from .models import Outbox
    filas = sesion.scalars(select(Outbox).where(Outbox.publicado_en.is_(None))
                           .order_by(Outbox.creado_en).limit(limite)).all()
    return [{"id": f.id, "routing_key": f.routing_key,
             "creado_en": f.creado_en.isoformat()} for f in filas]
