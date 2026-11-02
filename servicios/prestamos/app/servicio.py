"""Lógica de negocio del servicio Préstamos: decisión, máquina de estados y outbox.

Máquina de estados (docs/arquitectura/maquina-estados.md, §4):
- T1  POST /prestamos desfavorable → RECHAZADA (201, sin inventario)
- T2  POST /prestamos favorable   → PENDIENTE_INVENTARIO (202) + outbox
- T3  `inventario.reserva.reservada`      → APROBADA
- T4  `inventario.reserva.insuficiente`   → CANCELADA_SIN_STOCK
- T5  cancelación desde PENDIENTE_INVENTARIO → CANCELADA (vía `liberada`)
- T6  `inventario.salida.confirmada`      → COMPLETADA
- T7  cancelación desde APROBADA → espera `inventario.reserva.liberada` → CANCELADA
- T8  `inventario.reserva.vencida`        → CANCELADA_VENCIDA
- T9  evento tardío en estado final → sin cambio (log `evento_tardio_ignorado`)
"""
import hashlib
import logging
from datetime import datetime, timezone

import httpx
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from .broker import construir_evento
from .config import ajustes
from .models import EventoProcesado, Outbox, Prestamo, SolicitudIdempotente
from .security import token_de_servicio

logger = logging.getLogger("prestamos.servicio")

ESTADOS_FINALES = {"RECHAZADA", "CANCELADA_SIN_STOCK", "CANCELADA",
                   "CANCELADA_VENCIDA", "COMPLETADA"}
ESTADOS_CANCELABLES = {"PENDIENTE_INVENTARIO", "APROBADA"}


# --------------------------------------------------------------- decisiones
def variables_del_prestamo(monto_total: float, plazo_meses: int) -> dict:
    """Vector de variables del modelo calculado por el SERVICIO (§4).

    El cliente solo envía producto, cantidad y plazo; ingresos y obligaciones
    se toman del perfil del cliente en el servicio Clientes. Aquí se completa
    `cuota_estimada_cop` con la tasa oficial (el cliente no la elige).
    """
    tasa = ajustes.tasa_mensual_oficial
    # Cuota de amortización francés: cuota = P·i / (1 − (1+i)^−n)
    if tasa > 0 and plazo_meses > 0:
        cuota = monto_total * tasa / (1 - (1 + tasa) ** (-plazo_meses))
    else:
        cuota = monto_total / plazo_meses
    # `cuota_estimada_cop` es el nombre de la columna del histórico (§9) y la
    # variable del modelo; `tasa_mensual` es extra (no entra al pipeline).
    return {"monto_solicitado_cop": monto_total, "plazo_meses": plazo_meses,
            "tasa_mensual": tasa, "cuota_estimada_cop": round(cuota, 2)}


def decidir_riesgo(variables: dict) -> tuple[bool, float, str, dict]:
    """Devuelve (favorable, probabilidad, motivo, ficha_decisión).

    Regla previa al modelo (documentada en `ratio_deuda_ingreso_max`): si las
    obligaciones alcanzan los ingresos, se rechaza por regla sin invocar el
    modelo. En caso contrario se infiere con el modelo ACTIVO y se compara la
    probabilidad con su umbral.
    """
    from . import modelo

    ingresos = float(variables.get("ingresos_mensuales_cop") or 0)
    obligaciones = float(variables.get("obligaciones_mensuales_cop") or 0)
    if ingresos > 0 and obligaciones / ingresos >= ajustes.ratio_deuda_ingreso_max:
        ficha = modelo.ficha_activa() or {}
        return (False, 1.0,
                "regla de control: obligaciones alcanzan o superan los ingresos",
                {"modelo_version": ficha.get("modelo_version", "sin-modelo"),
                 "umbral": ficha.get("umbral"), "run_id": ficha.get("run_id")})

    probabilidad = modelo.predecir(variables)
    ficha = modelo.ficha_activa() or {}
    umbral = float(ficha["umbral"])
    favorable = probabilidad < umbral
    motivo = ("probabilidad por debajo del umbral" if favorable else
              "probabilidad igual o superior al umbral")
    return favorable, probabilidad, motivo, {
        "modelo_version": ficha["modelo_version"], "umbral": umbral,
        "run_id": ficha.get("run_id")}


# --------------------------------------------------------- consultas vecinas
def verificar_cliente(cliente_id: str) -> dict:
    """Consulta interna a Clientes (§9): existe y está activo. Lanza si falla."""
    respuesta = httpx.get(
        f"{ajustes.url_clientes}/clientes/{cliente_id}/credenciales",
        headers={"Authorization": f"Bearer {token_de_servicio()}"}, timeout=10)
    if respuesta.status_code == 404:
        raise LookupError(f"cliente {cliente_id} no existe")
    if respuesta.status_code == 403:
        raise PermissionError("el token de servicio fue rechazado")
    respuesta.raise_for_status()
    return respuesta.json()


def cotizar_producto(producto_id: str) -> dict:
    """Fuente de verdad del precio (§4): lee Productos (BD, no caché)."""
    respuesta = httpx.get(
        f"{ajustes.url_productos}/productos/{producto_id}/cotizacion",
        headers={"Authorization": f"Bearer {token_de_servicio()}"}, timeout=10)
    if respuesta.status_code == 404:
        raise LookupError(f"producto {producto_id} no existe")
    respuesta.raise_for_status()
    return respuesta.json()


def perfil_cliente(cliente_id: str) -> dict:
    """Perfil financiero del cliente para el vector de variables (§4)."""
    respuesta = httpx.get(
        f"{ajustes.url_clientes}/clientes/{cliente_id}",
        headers={"Authorization": f"Bearer {token_de_servicio()}"}, timeout=10)
    if respuesta.status_code == 404:
        raise LookupError(f"cliente {cliente_id} no existe")
    respuesta.raise_for_status()
    return respuesta.json()


# ---------------------------------------------------------------- idempotencia
def huella_cuerpo(cuerpo: dict) -> str:
    canonico = "&".join(f"{k}={cuerpo[k]}" for k in sorted(cuerpo))
    return hashlib.sha256(canonico.encode("utf-8")).hexdigest()


def solicitud_previa(sesion: Session, clave: str) -> SolicitudIdempotente | None:
    return sesion.get(SolicitudIdempotente, clave)


# ------------------------------------------------------------------ outbox
def encolar(sesion: Session, routing_key: str, evento: dict) -> None:
    sesion.add(Outbox(routing_key=routing_key, mensaje=evento))


def outbox_pendiente(sesion: Session) -> list[dict]:
    filas = sesion.scalars(
        select(Outbox).where(Outbox.publicado_en.is_(None))
        .order_by(Outbox.creado_en)).all()
    return [{"id": f.id, "routing_key": f.routing_key, "mensaje": f.mensaje}
            for f in filas]


def outbox_marcar(sesion: Session, outbox_id: str) -> None:
    fila = sesion.get(Outbox, outbox_id)
    if fila is not None:
        fila.publicado_en = datetime.now(timezone.utc)
        sesion.commit()


# ------------------------------------------------------- creación de préstamo
def construir_prestamo(sesion: Session, datos: dict, cotizacion: dict,
                       perfil: dict) -> Prestamo:
    """T1/T2: decide y persiste el préstamo + su outbox en la MISMA transacción.

    No hace commit: la ruta añade el registro de idempotencia (§9) y confirma
    todo junto, de modo que la clave y el préstamo nacen o mueren a la vez.
    """
    monto_total = float(cotizacion["precio_cop"]) * datos["cantidad"]
    variables = variables_del_prestamo(monto_total, datos["plazo_meses"])
    variables.update({
        "ingresos_mensuales_cop": perfil.get("ingresos_mensuales_cop", 0),
        "obligaciones_mensuales_cop": perfil.get("obligaciones_mensuales_cop", 0),
        "tipo_empleo": perfil.get("tipo_empleo", "no_definido"),
        "antiguedad_laboral_meses": perfil.get("antiguedad_laboral_meses", 0),
        "meses_historial_crediticio": perfil.get("meses_historial_crediticio", 0),
        "creditos_previos": perfil.get("creditos_previos", 0),
        "atrasos_previos_30d": perfil.get("atrasos_previos_30d", 0),
        "porcentaje_pago_puntual": perfil.get("porcentaje_pago_puntual"),
    })

    favorable, probabilidad, motivo, ficha = decidir_riesgo(variables)

    prestamo = Prestamo(
        cliente_id=datos["cliente_id"], producto_id=datos["producto_id"],
        cantidad=datos["cantidad"], plazo_meses=datos["plazo_meses"],
        precio_unitario_cop=cotizacion["precio_cop"],
        precio_producto_version=cotizacion["version"],
        monto_total_cop=monto_total,
        cuota_mensual_cop=variables["cuota_estimada_cop"],
        tasa_mensual=variables["tasa_mensual"],
        probabilidad_incumplimiento=probabilidad,
        umbral=ficha.get("umbral") or 0.0,
        modelo_version=ficha.get("modelo_version", "sin-modelo"),
        run_id=ficha.get("run_id"),
        estado="PENDIENTE_INVENTARIO" if favorable else "RECHAZADA",
        motivo=motivo,
        decidido_en=datetime.now(timezone.utc),
    )
    sesion.add(prestamo)
    sesion.flush()          # obtiene el id antes del outbox

    if favorable:
        # §5.3: payload sin datos financieros hacia Inventario.
        encolar(sesion, "prestamo.reserva.solicitada", construir_evento(
            "prestamo.reserva.solicitada", prestamo.id, prestamo.id,
            {"prestamo_id": prestamo.id, "producto_id": prestamo.producto_id,
             "cantidad": prestamo.cantidad, "plazo_dias": prestamo.plazo_meses * 30},
            productor="prestamos"))
    # Sin commit: la ruta confirma préstamo + outbox + idempotencia juntos.
    return prestamo


# ------------------------------------------------- consumidor de inventario
def procesar_evento(evento: dict) -> None:
    """Aplica T3/T4/T6/T7/T8/T9. El ack ocurre únicamente tras su commit."""
    from .db import Sesion
    tipo = evento.get("type")
    prestamo_id = (evento.get("payload") or {}).get("prestamo_id") or \
        evento.get("prestamo_id")
    sesion = Sesion()
    try:
        if sesion.get(EventoProcesado, evento.get("event_id")) is not None:
            sesion.commit()
            logger.info("evento duplicado %s ignorado", evento.get("event_id"))
            return
        sesion.add(EventoProcesado(event_id=evento["event_id"], tipo=tipo,
                                   prestamo_id=prestamo_id))

        prestamo = sesion.get(Prestamo, prestamo_id)
        if prestamo is None:
            # Préstamo desconocido: se registra y se confirma (no reintentable).
            logger.warning("evento %s para préstamo inexistente %s", tipo, prestamo_id)
            sesion.commit()
            return

        payload = evento.get("payload") or {}
        if prestamo.estado in ESTADOS_FINALES:
            # T9: los estados finales son absorbentes; nada reactiva.
            logger.info("evento_tardio_ignorado{prestamo_id=%s, type=%s, event_id=%s}",
                        prestamo_id, tipo, evento.get("event_id"))
            sesion.commit()
            return

        if tipo == "inventario.reserva.reservada" and \
                prestamo.estado == "PENDIENTE_INVENTARIO":
            prestamo.estado = "APROBADA"                       # T3
            prestamo.reserva_id = payload.get("reserva_id")
            prestamo.motivo = "reserva confirmada por inventario"
        elif tipo == "inventario.reserva.insuficiente" and \
                prestamo.estado == "PENDIENTE_INVENTARIO":
            prestamo.estado = "CANCELADA_SIN_STOCK"            # T4
            prestamo.motivo = (f"sin existencias suficientes "
                               f"(disponible {payload.get('disponible')})")
        elif tipo == "inventario.salida.confirmada" and \
                prestamo.estado == "APROBADA":
            prestamo.estado = "COMPLETADA"                     # T6
            prestamo.motivo = f"entrega confirmada {payload.get('entregado_en')}"
        elif tipo == "inventario.reserva.vencida" and \
                prestamo.estado in ("APROBADA", "PENDIENTE_INVENTARIO"):
            prestamo.estado = "CANCELADA_VENCIDA"              # T8
            prestamo.motivo = f"reserva vencida {payload.get('vencio_en')}"
        elif tipo == "inventario.reserva.liberada":
            if prestamo.cancelacion_solicitada_en is not None:
                # T5/T7: la cancelación SOLO termina tras confirmar `liberada`.
                prestamo.estado = "CANCELADA"
                prestamo.motivo = "cancelación confirmada; reserva resuelta"
            else:
                logger.info("liberada no solicitada para %s; sin cambio de estado",
                            prestamo_id)
        else:
            logger.info("evento %s sin transición aplicable para %s en estado %s",
                        tipo, prestamo_id, prestamo.estado)
        sesion.commit()
    finally:
        sesion.close()


# ------------------------------------------------------------- cancelación
def cancelar(sesion: Session, prestamo: Prestamo, motivo: str) -> None:
    """T5/T7: marca la cancelación en vuelo y publica `reserva.cancelada`.

    El estado final CANCELADA lo pone el consumidor al recibir `liberada`
    (§4: la cancelación final requiere resolver la reserva).
    """
    prestamo.cancelacion_solicitada_en = datetime.now(timezone.utc)
    prestamo.motivo = motivo
    encolar(sesion, "prestamo.reserva.cancelada", construir_evento(
        "prestamo.reserva.cancelada", prestamo.id, prestamo.id,
        {"prestamo_id": prestamo.id, "motivo": motivo}, productor="prestamos"))
    sesion.commit()


# --------------------------------------------------------------- consultas
def contar_prestamos(sesion: Session, cliente_id: str | None) -> int:
    consulta = select(func.count()).select_from(Prestamo)
    if cliente_id:
        consulta = consulta.where(Prestamo.cliente_id == cliente_id)
    return sesion.scalar(consulta) or 0
