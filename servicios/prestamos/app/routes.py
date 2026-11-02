"""Rutas REST del servicio Préstamos (contrato en docs/arquitectura/contratos-rest.md).

El cliente NUNCA envía precio, monto ni tasa (§4): el precio sale de la
cotización interna de Productos (fuente de verdad, BD) y la cuota se calcula
aquí con la tasa oficial del programa. El modelo de riesgo es de este
servicio (§8) y decide con su umbral; un resultado favorable NO es una
aprobación: la aprobación la da Inventario con la reserva confirmada (§4).
"""
from fastapi import APIRouter, Depends, Header, Request
from fastapi.responses import JSONResponse
from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from . import modelo, servicio
from .config import ajustes
from .db import obtener_sesion
from .models import Prestamo, SolicitudIdempotente
from .schemas import (
    ModeloInfo,
    PrestamoLectura,
    PrestamoLista,
    PromocionResultado,
    PromocionSolicitud,
    RiesgoDecision,
    RiesgoSolicitud,
    SolicitudCreacion,
)
from .security import (
    exigir_dueno_o_admin,
    rol_administrador,
    rol_cliente_o_admin,
    rol_interno,
)

router = APIRouter()


def _problema(status: int, titulo: str, detalle: str, instance: str, errores=None):
    cuerpo = {"type": "about:blank", "title": titulo, "status": status,
              "detail": detalle, "instance": instance}
    if errores:
        cuerpo["errors"] = errores
    return JSONResponse(status_code=status, content=cuerpo,
                        media_type="application/problem+json")


def _respuesta_prestamo(prestamo: Prestamo) -> dict:
    """Cuerpo de `POST /prestamos` (§4): incluye decisión completa."""
    return {
        "prestamo_id": prestamo.id,
        "estado": prestamo.estado,
        "motivo": prestamo.motivo,
        "cliente_id": prestamo.cliente_id,
        "producto_id": prestamo.producto_id,
        "cantidad": prestamo.cantidad,
        "plazo_meses": prestamo.plazo_meses,
        "precio_unitario_cop": float(prestamo.precio_unitario_cop),
        "precio_producto_version": prestamo.precio_producto_version,
        "monto_total_cop": float(prestamo.monto_total_cop),
        "cuota_mensual_cop": float(prestamo.cuota_mensual_cop),
        "tasa_mensual": prestamo.tasa_mensual,
        "probabilidad_incumplimiento": prestamo.probabilidad_incumplimiento,
        "umbral": prestamo.umbral,
        "modelo_version": prestamo.modelo_version,
        "creado_en": prestamo.creado_en.isoformat(),
    }


# ------------------------------------------------------------ creación (§4, §9)
@router.post("/prestamos")
def crear_prestamo(cuerpo: SolicitudCreacion, request: Request,
                   idempotency_key: str | None = Header(default=None,
                                                        alias="Idempotency-Key"),
                   sesion: Session = Depends(obtener_sesion),
                   datos: dict = Depends(rol_cliente_o_admin)):
    """Crea una solicitud de préstamo (T1/T2).

    Requiere `Idempotency-Key` (§9): misma clave + mismo cuerpo → misma
    respuesta; misma clave + cuerpo distinto → 409. La aprobación solo llega
    cuando Inventario confirma la reserva (T3).
    """
    instancia = str(request.url.path)
    clave = (idempotency_key or "").strip()
    if not clave:
        return _problema(400, "Solicitud inválida",
                         "falta la cabecera Idempotency-Key", instancia,
                         [{"campo": "Idempotency-Key", "mensaje": "obligatoria"}])
    if len(clave) > 80:
        return _problema(400, "Solicitud inválida",
                         "Idempotency-Key excede 80 caracteres", instancia)

    exigir_dueno_o_admin(datos, cuerpo.cliente_id, instancia)
    huella = servicio.huella_cuerpo(cuerpo.model_dump())

    previa = servicio.solicitud_previa(sesion, clave)
    if previa is not None:
        if previa.huella_cuerpo != huella:
            return _problema(409, "Conflicto",
                             "la Idempotency-Key ya se usó con otro cuerpo",
                             instancia)
        return JSONResponse(status_code=previa.status_code, content=previa.respuesta)

    # Fuente de verdad: cliente en Clientes, precio en Productos (§4).
    try:
        perfil = servicio.perfil_cliente(cuerpo.cliente_id)
    except LookupError:
        return _problema(404, "Recurso no encontrado",
                         f"cliente {cuerpo.cliente_id} no existe", instancia)
    except Exception as exc:                          # noqa: BLE001
        return _problema(503, "Servicio no disponible",
                         f"no se pudo consultar el cliente: {exc}", instancia)
    if not perfil.get("activo", True):
        return _problema(403, "Prohibido", "cliente inactivo", instancia)

    try:
        cotizacion = servicio.cotizar_producto(cuerpo.producto_id)
    except LookupError:
        return _problema(404, "Recurso no encontrado",
                         f"producto {cuerpo.producto_id} no existe", instancia)
    except Exception as exc:                          # noqa: BLE001
        return _problema(503, "Servicio no disponible",
                         f"no se pudo cotizar el producto: {exc}", instancia)

    try:
        prestamo = servicio.construir_prestamo(
            sesion,
            {"cliente_id": cuerpo.cliente_id, "producto_id": cuerpo.producto_id,
             "cantidad": cuerpo.cantidad, "plazo_meses": cuerpo.plazo_meses},
            cotizacion, perfil)
        cuerpo_respuesta = _respuesta_prestamo(prestamo)
        status = 202 if prestamo.estado == "PENDIENTE_INVENTARIO" else 201
        sesion.add(SolicitudIdempotente(
            idempotency_key=clave, huella_cuerpo=huella,
            prestamo_id=prestamo.id, respuesta=cuerpo_respuesta,
            status_code=status))
        sesion.commit()
    except IntegrityError:
        # Carrera: otra petición con la misma clave ganó la transacción.
        sesion.rollback()
        previa = servicio.solicitud_previa(sesion, clave)
        if previa is not None and previa.huella_cuerpo == huella:
            return JSONResponse(status_code=previa.status_code,
                                content=previa.respuesta)
        return _problema(409, "Conflicto",
                         "la Idempotency-Key ya se usó con otro cuerpo",
                         instancia)
    return JSONResponse(status_code=status, content=cuerpo_respuesta)


# --------------------------------------------------------------- consultas (§4)
@router.get("/prestamos/{prestamo_id}", response_model=PrestamoLectura)
def obtener_prestamo(prestamo_id: str, request: Request,
                     sesion: Session = Depends(obtener_sesion),
                     datos: dict = Depends(rol_cliente_o_admin)):
    prestamo = sesion.get(Prestamo, prestamo_id)
    if prestamo is None:
        return _problema(404, "Recurso no encontrado",
                         f"préstamo {prestamo_id} no existe",
                         str(request.url.path))
    exigir_dueno_o_admin(datos, prestamo.cliente_id, str(request.url.path))
    return PrestamoLectura.model_validate(prestamo)


@router.get("/prestamos", response_model=PrestamoLista)
def listar_prestamos(pagina: int = 1, tamano: int = 20,
                     sesion: Session = Depends(obtener_sesion),
                     datos: dict = Depends(rol_cliente_o_admin)):
    consulta = select(func.count()).select_from(Prestamo)
    filas = select(Prestamo).order_by(Prestamo.creado_en.desc())
    # §10: un cliente solo lista los suyos; un administrador, todos.
    if datos.get("rol") != "administrador":
        consulta = consulta.where(Prestamo.cliente_id == datos.get("cliente_id"))
        filas = filas.where(Prestamo.cliente_id == datos.get("cliente_id"))
    total = sesion.scalar(consulta) or 0
    items = sesion.scalars(filas.offset((pagina - 1) * tamano)
                           .limit(tamano)).all()
    return PrestamoLista(total=total, pagina=pagina, tamano=tamano,
                         items=[PrestamoLectura.model_validate(i) for i in items])


# -------------------------------------------------------------- cancelación (§4)
@router.post("/prestamos/{prestamo_id}/cancelar")
def cancelar_prestamo(prestamo_id: str, request: Request,
                      sesion: Session = Depends(obtener_sesion),
                      datos: dict = Depends(rol_cliente_o_admin)):
    """Cancela desde `PENDIENTE_INVENTARIO` o `APROBADA` (T5/T7).

    Publica `prestamo.reserva.cancelada`; el estado final `CANCELADA` lo pone
    el consumidor al recibir `inventario.reserva.liberada` (§4: la cancelación
    final requiere resolver la reserva).
    """
    instancia = str(request.url.path)
    prestamo = sesion.get(Prestamo, prestamo_id)
    if prestamo is None:
        return _problema(404, "Recurso no encontrado",
                         f"préstamo {prestamo_id} no existe", instancia)
    exigir_dueno_o_admin(datos, prestamo.cliente_id, instancia)
    if prestamo.estado not in servicio.ESTADOS_CANCELABLES:
        return _problema(409, "Conflicto",
                         f"no se puede cancelar un préstamo en estado "
                         f"{prestamo.estado}", instancia)
    if prestamo.cancelacion_solicitada_en is not None:
        return _problema(409, "Conflicto",
                         "ya hay una cancelación en curso para este préstamo",
                         instancia)
    servicio.cancelar(sesion, prestamo, motivo="cancelación solicitada por el usuario")
    return JSONResponse(status_code=202, content={
        "prestamo_id": prestamo.id,
        "estado": prestamo.estado,
        "cancelacion_en_curso": True,
        "motivo": prestamo.motivo,
        "detalle": "la confirmación final llega cuando inventario libera la reserva",
    })


# ------------------------------------------------------- inferencia aislada (§8.E)
@router.post("/riesgo/predict", response_model=RiesgoDecision)
def predecir_riesgo(cuerpo: RiesgoSolicitud, request: Request,
                    datos: dict = Depends(rol_interno)):
    """Inferencia aislada: NO reserva inventario ni crea préstamo (§8.E)."""
    if not modelo.disponible():
        return _problema(503, "Servicio no disponible",
                         f"sin modelo activo: {modelo.error_carga()}",
                         str(request.url.path))
    variables = dict(cuerpo.model_dump())
    monto = float(cuerpo.monto_solicitado_cop)
    variables.update(servicio.variables_del_prestamo(monto, cuerpo.plazo_meses))
    favorable, probabilidad, motivo, ficha = servicio.decidir_riesgo(variables)
    return RiesgoDecision(
        probabilidad_incumplimiento=probabilidad,
        umbral=ficha.get("umbral") or 0.0,
        decision="FAVORABLE" if favorable else "DESFAVORABLE",
        modelo_version=ficha.get("modelo_version", "sin-modelo"),
        run_id=ficha.get("run_id"),
        regla_aplicada=motivo if probabilidad == 1.0 and not favorable else None,
    )


# ----------------------------------------------------- modelo activo (§8.D–§8.E)
@router.get("/modelo/info", response_model=ModeloInfo)
def info_modelo(request: Request, _auth: dict = Depends(rol_administrador)):
    info = modelo.info()
    if info is None:
        return _problema(503, "Servicio no disponible",
                         f"sin modelo activo: {modelo.error_carga()}",
                         str(request.url.path))
    return ModeloInfo(**info)


@router.post("/admin/modelo/promover", response_model=PromocionResultado)
def promover_modelo(cuerpo: PromocionSolicitud, request: Request,
                    _auth: dict = Depends(rol_administrador)):
    """Promoción EXPLÍCITA del modelo activo (§8.D, P2-DEC-002).

    El rollback es una promoción explícita de la versión anterior: el servicio
    NUNCA cambia de modelo por sí solo. Verifica que el artefacto carga y
    predice antes de activarlo.
    """
    instancia = str(request.url.path)
    if cuerpo.modelo_version not in modelo.versiones_exportadas():
        return _problema(404, "Recurso no encontrado",
                         f"no hay artefacto exportado para {cuerpo.modelo_version}",
                         instancia)
    try:
        activo = modelo.promover(cuerpo.modelo_version, cuerpo.motivo)
    except (ValueError, OSError) as exc:
        return _problema(409, "Conflicto",
                         f"no se pudo promover: {exc}", instancia)
    return PromocionResultado(
        modelo_version=activo["modelo_version"],
        umbral=activo["umbral"],
        run_id=activo.get("run_id"),
        activo_desde=activo["promovido_en"],
        version_anterior=activo.get("version_anterior"),
        motivo=activo["motivo"],
    )


@router.post("/admin/modelo/rollback", response_model=PromocionResultado)
def rollback_modelo(request: Request, _auth: dict = Depends(rol_administrador)):
    """Rollback explícito: reactiva la última promoción anterior (§8.D)."""
    try:
        activo = modelo.rollback(motivo="rollback explícito")
    except ValueError as exc:
        return _problema(409, "Conflicto", str(exc), str(request.url.path))
    return PromocionResultado(
        modelo_version=activo["modelo_version"],
        umbral=activo["umbral"],
        run_id=activo.get("run_id"),
        activo_desde=activo["promovido_en"],
        version_anterior=activo.get("version_anterior"),
        motivo=activo["motivo"],
    )
