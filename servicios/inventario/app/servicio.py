"""Lógica de negocio del servicio Inventario (efectos locales + outbox)."""
import json
import logging
import uuid
from datetime import datetime, timedelta, timezone

from sqlalchemy import select, text, update
from sqlalchemy.orm import Session

from .broker import construir_evento
from .config import ajustes
from .models import EventoProcesado, Existencia, Movimiento, Outbox, Reserva

logger = logging.getLogger("inventario.servicio")


class EntregaYaConfirmada(Exception):
    """La entrega ya había sido confirmada (carrera de repetición, §4)."""


def _utc(vence: datetime) -> datetime:
    return vence if vence.tzinfo else vence.replace(tzinfo=timezone.utc)


def crear_existencia(sesion: Session, producto_id: str, total: int) -> Existencia:
    existencia = Existencia(producto_id=producto_id, total=total, reservada=0)
    sesion.add(existencia)
    sesion.commit()
    return existencia


def entrada(sesion: Session, producto_id: str, cantidad: int,
            referencia: str | None = None) -> Existencia:
    existencia = sesion.get(Existencia, producto_id)
    if existencia is None:
        existencia = Existencia(producto_id=producto_id, total=0, reservada=0)
        sesion.add(existencia)
    existencia.total += cantidad
    sesion.add(Movimiento(tipo="ENTRADA", producto_id=producto_id, cantidad=cantidad,
                          referencia=referencia, detalle="entrada de stock"))
    sesion.commit()
    return existencia


def disponible(sesion: Session, producto_id: str) -> int:
    fila = sesion.execute(
        text("SELECT total - reservada AS d FROM inventario.existencia "
             "WHERE producto_id = :p").bindparams(p=producto_id)
    ).first()
    return fila[0] if fila else 0


# ------------------------------------------------- consumidor de comandos
def procesar_comando(evento: dict) -> None:
    """Efecto local + outbox en UNA transacción; lanza si debe reintentarse.

    Este bloque es el que se ejecuta con `asyncio.to_thread` desde el
    consumidor; el ack del broker ocurre únicamente tras su commit.
    """
    tipo = evento.get("type")
    if tipo == "prestamo.reserva.solicitada":
        _reservar(evento)
    elif tipo == "prestamo.reserva.cancelada":
        _liberar_por_cancelacion(evento)
    else:
        logger.warning("tipo de mensaje no soportado: %s (a DLQ)", tipo)
        raise ValueError(f"tipo no soportado: {tipo}")


def _registrar_evento(sesion: Session, evento: dict) -> bool:
    """Deduplicación durable: `event_id` ya visto → True (sin repetir efecto)."""
    if sesion.get(EventoProcesado, evento.get("event_id")) is not None:
        return True
    sesion.add(EventoProcesado(event_id=evento["event_id"], tipo=evento.get("type", ""),
                               prestamo_id=evento.get("prestamo_id")))
    return False


def _reservar(evento: dict) -> None:
    from .db import Sesion
    sesion = Sesion()
    try:
        payload = evento["payload"]
        producto_id, cantidad = payload["producto_id"], int(payload["cantidad"])
        prestamo_id = payload["prestamo_id"]

        if _registrar_evento(sesion, evento):
            sesion.commit()      # duplicado: ya procesado, se confirma sin repetir
            logger.info("evento duplicado %s ignorado", evento["event_id"])
            return

        # Reserva ATÓMICA: una sola sentencia con la condición de disponibilidad
        # (pruebas #3 y #4: nunca existencias negativas, exactamente una gana).
        resultado = sesion.execute(
            update(Existencia)
            .where(Existencia.producto_id == producto_id,
                   text("total - reservada >= :cantidad").bindparams(cantidad=cantidad))
            .values(reservada=Existencia.reservada + cantidad)
        )
        filas = resultado.rowcount

        vence_en = _utc(datetime.now(timezone.utc)) + timedelta(
            seconds=ajustes.reserva_vencimiento_seg)
        if payload.get("vence_en"):
            vence_en = _utc(datetime.fromisoformat(
                payload["vence_en"].replace("Z", "+00:00")))

        if filas == 1:
            reserva = Reserva(prestamo_id=prestamo_id, producto_id=producto_id,
                              cantidad=cantidad, estado="RESERVADA", vence_en=vence_en)
            sesion.add(reserva)
            sesion.flush()
            sesion.add(Movimiento(tipo="RESERVA", producto_id=producto_id,
                                  cantidad=cantidad, referencia=reserva.id,
                                  detalle=f"préstamo {prestamo_id}"))
            sesion.add(Outbox(
                routing_key="inventario.reserva.reservada",
                mensaje=construir_evento(
                    "inventario.reserva.reservada", prestamo_id, prestamo_id,
                    {"prestamo_id": prestamo_id, "reserva_id": reserva.id,
                     "producto_id": producto_id, "cantidad": cantidad,
                     "vence_en": vence_en.isoformat()}),
            ))
            sesion.commit()
            logger.info("reserva creada %s para %s", reserva.id, prestamo_id)
        else:
            existencia = sesion.get(Existencia, producto_id)
            libres = (existencia.total - existencia.reservada) if existencia else 0
            sesion.add(Outbox(
                routing_key="inventario.reserva.insuficiente",
                mensaje=construir_evento(
                    "inventario.reserva.insuficiente", prestamo_id, prestamo_id,
                    {"prestamo_id": prestamo_id, "producto_id": producto_id,
                     "solicitado": cantidad, "disponible": libres}),
            ))
            sesion.commit()
            logger.info("stock insuficiente para %s (disponible %s)", prestamo_id, libres)
    finally:
        sesion.close()


def _liberar_por_cancelacion(evento: dict) -> None:
    from .db import Sesion
    sesion = Sesion()
    try:
        payload = evento["payload"]
        prestamo_id = payload["prestamo_id"]
        if _registrar_evento(sesion, evento):
            sesion.commit()
            return
        liberada = _liberar_reserva(sesion, prestamo_id, origen="cancelacion")
        if liberada is None:
            # No hay reserva viva: se responde igual para que Préstamos cierre
            # su transición (la carrera está resuelta en §4 del diseño).
            sesion.add(Outbox(
                routing_key="inventario.reserva.liberada",
                mensaje=construir_evento(
                    "inventario.reserva.liberada", prestamo_id, prestamo_id,
                    {"prestamo_id": prestamo_id, "reserva_id": None,
                     "origen": "cancelacion", "nota": "sin reserva viva"}),
            ))
            sesion.commit()
            logger.info("cancelación sin reserva viva para %s", prestamo_id)
            return
        sesion.add(Outbox(
            routing_key="inventario.reserva.liberada",
            mensaje=construir_evento(
                "inventario.reserva.liberada", prestamo_id, prestamo_id,
                {"prestamo_id": prestamo_id, "reserva_id": liberada,
                 "origen": "cancelacion"}),
        ))
        sesion.commit()
        logger.info("reserva %s liberada para %s", liberada, prestamo_id)
    finally:
        sesion.close()


def _liberar_reserva(sesion: Session, prestamo_id: str, origen: str) -> str | None:
    """Liberación atómica de la reserva viva de un préstamo."""
    reserva = sesion.scalar(
        select(Reserva).where(Reserva.prestamo_id == prestamo_id,
                              Reserva.estado == "RESERVADA")
    )
    if reserva is None:
        return None
    resultado = sesion.execute(
        update(Existencia)
        .where(Existencia.producto_id == reserva.producto_id,
               text("reservada >= :cantidad").bindparams(cantidad=reserva.cantidad))
        .values(reservada=Existencia.reservada - reserva.cantidad)
    )
    if resultado.rowcount != 1:
        # Invariante violada: no se publica nada y se propaga el error (reintento).
        raise RuntimeError(f"no se pudo liberar la reserva {reserva.id}")
    reserva.estado = "LIBERADA"
    sesion.add(Movimiento(tipo="LIBERACION", producto_id=reserva.producto_id,
                          cantidad=reserva.cantidad, referencia=reserva.id,
                          detalle=origen))
    return reserva.id


# --------------------------------------------------------------- entregas
def entregar(sesion: Session, reserva_id: str) -> tuple[Reserva, dict]:
    """Confirma la salida de stock y publica `inventario.salida.confirmada`."""
    reserva = sesion.get(Reserva, reserva_id)
    if reserva is None:
        raise LookupError("reserva inexistente")
    if reserva.estado == "ENTREGADA":
        raise EntregaYaConfirmada("la reserva ya fue entregada")
    if reserva.estado != "RESERVADA":
        raise ValueError(f"la reserva está en estado {reserva.estado}")

    # Salida: descuenta total y reservada en una sola transacción.
    resultado = sesion.execute(
        update(Existencia)
        .where(Existencia.producto_id == reserva.producto_id,
               text("total >= reservada AND reservada >= :cantidad").bindparams(cantidad=reserva.cantidad))
        .values(total=Existencia.total - reserva.cantidad,
                reservada=Existencia.reservada - reserva.cantidad)
    )
    if resultado.rowcount != 1:
        raise RuntimeError("existencias inconsistentes para la entrega")

    reserva.estado = "ENTREGADA"
    entregado = datetime.now(timezone.utc)
    sesion.add(Movimiento(tipo="SALIDA", producto_id=reserva.producto_id,
                          cantidad=reserva.cantidad, referencia=reserva.id,
                          detalle="entrega simulada"))
    evento = construir_evento(
        "inventario.salida.confirmada", reserva.prestamo_id, reserva.prestamo_id,
        {"prestamo_id": reserva.prestamo_id, "reserva_id": reserva.id,
         "entregado_en": entregado.isoformat().replace("+00:00", "Z")})
    sesion.add(Outbox(routing_key="inventario.salida.confirmada", mensaje=evento))
    sesion.commit()
    return reserva, evento


# ------------------------------------------------------------ vencimientos
def expirar_reservas(sesion: Session) -> list[dict]:
    """Pasa a VENCIDA las reservas vencidas y devuelve las unidades (§4).

    Cada vencimiento escribe su evento `inventario.reserva.vencida` en outbox
    dentro de la MISMA transacción.
    """
    ahora = datetime.now(timezone.utc)
    vencidas = sesion.scalars(
        select(Reserva).where(Reserva.estado == "RESERVADA",
                              text("vence_en < :ahora").bindparams(ahora=ahora))
    ).all()
    eventos: list[dict] = []
    for reserva in vencidas:
        sesion.execute(
            update(Existencia)
            .where(Existencia.producto_id == reserva.producto_id,
                   text("reservada >= :cantidad").bindparams(cantidad=reserva.cantidad))
            .values(reservada=Existencia.reservada - reserva.cantidad)
        )
        reserva.estado = "VENCIDA"
        sesion.add(Movimiento(tipo="VENCIMIENTO", producto_id=reserva.producto_id,
                              cantidad=reserva.cantidad, referencia=reserva.id,
                              detalle="reserva vencida"))
        evento = construir_evento(
            "inventario.reserva.vencida", reserva.prestamo_id, reserva.prestamo_id,
            {"prestamo_id": reserva.prestamo_id, "reserva_id": reserva.id,
             "origen": "vencimiento",
             "vencio_en": reserva.vence_en.isoformat()})
        sesion.add(Outbox(routing_key="inventario.reserva.vencida", mensaje=evento))
        eventos.append(evento)
    if eventos:
        sesion.commit()
        logger.info("%d reservas vencidas", len(eventos))
    return eventos


# --------------------------------------------------------------- outbox
def outbox_pendiente(sesion: Session) -> list[dict]:
    filas = sesion.scalars(
        select(Outbox).where(Outbox.publicado_en.is_(None))
        .order_by(Outbox.creado_en)
    ).all()
    return [{"id": f.id, "routing_key": f.routing_key, "mensaje": f.mensaje}
            for f in filas]


def outbox_marcar(sesion: Session, outbox_id: str) -> None:
    fila = sesion.get(Outbox, outbox_id)
    if fila is not None:
        fila.publicado_en = datetime.now(timezone.utc)
        sesion.commit()
