"""Topología y mensajería RabbitMQ del servicio Inventario (§5.2).

- exchange `credimarket.topic` (topic, durable) + `credimarket.dlx` (dead letter);
- colas: `inventario.comandos` (bind `prestamo.#`), `inventario.retry` (TTL de
  reintento) e `inventario.dlq` (tras agotar intentos);
- publicación con **publisher confirm** y mensajes persistentes;
- **ack manual después del commit** (P2-REQ-038) y reintentos acotados a 3.
"""
import asyncio
import json
import logging
import uuid
from datetime import datetime, timezone
from typing import Callable

import aio_pika
from aio_pika import DeliveryMode, ExchangeType, Message

from .config import ajustes

logger = logging.getLogger("inventario.broker")

_conexion: aio_pika.RobustConnection | None = None
_canal: aio_pika.abc.AbstractChannel | None = None
_exchange = None          # credimarket.topic (topic, durable)
_dlx = None               # credimarket.dlx (dead letter)
_bucle: asyncio.AbstractEventLoop | None = None   # bucle dueño de la conexión
_tarea_consumidor: asyncio.Task | None = None
_tarea_outbox: asyncio.Task | None = None


def _sello() -> str:
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


def construir_evento(tipo: str, correlation_id: str, prestamo_id: str | None,
                     payload: dict, productor: str = "inventario") -> dict:
    """Envelope obligatorio (§5.2): los 7 campos del contrato de mensajes."""
    return {
        "event_id": str(uuid.uuid4()),
        "type": tipo,
        "schema_version": 1,
        "occurred_at": _sello(),
        "correlation_id": correlation_id,
        "prestamo_id": prestamo_id,
        "producer": productor,
        "payload": payload,
    }


async def conectar() -> aio_pika.RobustConnection:
    global _conexion, _canal, _bucle
    if _conexion is None or _conexion.is_closed:
        _conexion = await aio_pika.connect_robust(ajustes.broker_url,
                                                  timeout=10)
        _canal = await _conexion.channel(publisher_confirms=True)
        await _canal.set_qos(prefetch_count=ajustes.prefetch)
        await declarar_topologia(_canal)
        _bucle = asyncio.get_running_loop()
    return _conexion


async def declarar_topologia(canal: aio_pika.abc.AbstractChannel) -> None:
    global _exchange, _dlx
    exchange = await canal.declare_exchange(ajustes.exchange, ExchangeType.TOPIC,
                                            durable=True)
    dlx = await canal.declare_exchange(ajustes.exchange_muerto, ExchangeType.DIRECT,
                                       durable=True)
    _exchange, _dlx = exchange, dlx

    cola = await canal.declare_queue(
        ajustes.cola_comandos,
        durable=True,
        arguments={
            "x-dead-letter-exchange": ajustes.exchange_muerto,
            "x-dead-letter-routing-key": ajustes.cola_comandos,
        },
    )
    await cola.bind(exchange, routing_key="prestamo.#")
    # Retorno desde la cola de reintento: el dead-letter reenvía con routing key
    # = nombre de la cola, así que también se enlaza esa clave al mismo exchange.
    await cola.bind(exchange, routing_key=ajustes.cola_comandos)

    # Cola de reintento: el TTL devuelve el mensaje a la cola de comandos.
    retry = await canal.declare_queue(
        ajustes.cola_reintento,
        durable=True,
        arguments={
            "x-message-ttl": ajustes.ttl_reintento_ms,
            "x-dead-letter-exchange": ajustes.exchange,
            "x-dead-letter-routing-key": ajustes.cola_comandos,
        },
    )
    await retry.bind(exchange, routing_key=ajustes.cola_reintento)

    dlq = await canal.declare_queue(ajustes.cola_dlq, durable=True)
    await dlq.bind(dlx, routing_key=ajustes.cola_dlq)
    logger.info("topología declarada: %s, %s, %s", ajustes.cola_comandos,
                ajustes.cola_reintento, ajustes.cola_dlq)


async def publicar(routing_key: str, evento: dict) -> None:
    """Publicación con confirm y mensaje persistente sobre `credimarket.topic`.

    Si se invoca desde un bucle distinto al del servicio (por ejemplo desde un
    proceso de prueba), usa una conexión temporal: las conexiones AMQP son
    propiedad de un único bucle de eventos.
    """
    mensaje = Message(
        body=json.dumps(evento, ensure_ascii=False).encode("utf-8"),
        delivery_mode=DeliveryMode.PERSISTENT,
        content_type="application/json",
        message_id=evento.get("event_id"),
        correlation_id=evento.get("correlation_id"),
        timestamp=datetime.now(timezone.utc),
    )
    en_bucle_propio = (_conexion is not None and not _conexion.is_closed
                       and _bucle is asyncio.get_running_loop())
    if en_bucle_propio:
        await _exchange.publish(mensaje, routing_key=routing_key, mandatory=True)
        logger.info("publicado %s (%s)", routing_key, evento.get("event_id"))
        return

    conn = await aio_pika.connect_robust(ajustes.broker_url, timeout=10)
    try:
        canal = await conn.channel(publisher_confirms=True)
        exchange = await canal.declare_exchange(ajustes.exchange, ExchangeType.TOPIC,
                                                durable=True)
        await exchange.publish(mensaje, routing_key=routing_key, mandatory=True)
        logger.info("publicado (conexión temporal) %s (%s)", routing_key,
                    evento.get("event_id"))
    finally:
        await conn.close()


async def cerrar() -> None:
    global _conexion, _canal, _tarea_consumidor, _tarea_outbox, _exchange, _dlx, _bucle
    for tarea in (_tarea_consumidor, _tarea_outbox):
        if tarea is not None and not tarea.done():
            tarea.cancel()
            try:
                await tarea
            except (asyncio.CancelledError, Exception):      # noqa: B014
                pass
    _tarea_consumidor = _tarea_outbox = None
    if _conexion is not None and not _conexion.is_closed:
        await _conexion.close()
    _conexion = _canal = _exchange = _dlx = _bucle = None


# ------------------------------------------------------------------ consumidor
async def arrancar_consumidor(procesar: Callable[[dict], None]) -> None:
    """Suscribe `inventario.comandos` con ack manual tras el commit.

    `procesar` ejecuta el efecto local (commit incluido) y lanza si debe
    reintentarse. Tras `max_intentos` fallos el mensaje va a la DLQ.
    """
    global _tarea_consumidor
    await conectar()

    async def _manejador(mensaje: aio_pika.abc.AbstractIncomingMessage) -> None:
        intentos = int((mensaje.headers or {}).get("x-intentos", 0))
        async with mensaje.process(requeue=False):
            try:
                evento = json.loads(mensaje.body.decode("utf-8"))
            except (ValueError, UnicodeDecodeError):
                logger.error("cuerpo no JSON; a la DLQ")
                await _a_dlq(mensaje)
                return
            try:
                await asyncio.to_thread(procesar, evento)
            except Exception as exc:                      # noqa: BLE001
                if intentos + 1 < ajustes.max_intentos:
                    logger.warning("fallo en %s (intento %d): %s; a reintento",
                                   evento.get("type"), intentos + 1, exc)
                    await _a_reintento(mensaje, intentos + 1)
                else:
                    logger.error("agotados los intentos para %s: %s; a DLQ",
                                 evento.get("type"), exc)
                    await _a_dlq(mensaje)
                return
            logger.info("procesado y confirmado %s", evento.get("event_id"))

    tarea = asyncio.create_task(_consumir(_manejador))
    tarea.add_done_callback(_reportar_fallo)
    _tarea_consumidor = tarea
    logger.info("consumidor de inventario arrancado")


def _reportar_fallo(tarea: asyncio.Task) -> None:
    """Un fallo del consumidor no debe morir en silencio."""
    if tarea.cancelled():
        return
    exc = tarea.exception()
    if exc is not None:
        logger.error("el consumidor terminó con error: %r", exc)


async def _consumir(manejador) -> None:
    cola = await _canal.declare_queue(
        ajustes.cola_comandos,
        durable=True,
        arguments={
            "x-dead-letter-exchange": ajustes.exchange_muerto,
            "x-dead-letter-routing-key": ajustes.cola_comandos,
        },
    )
    await cola.bind(_exchange, routing_key=ajustes.cola_comandos)
    async with cola.iterator(no_ack=False) as flujos:
        async for mensaje in flujos:
            asyncio.create_task(manejador(mensaje))


async def _a_reintento(mensaje: aio_pika.abc.AbstractIncomingMessage,
                       intentos: int) -> None:
    """Reenvía a la cola de reintento conservando el cuerpo y marcando intentos."""
    await conectar()
    nuevo = Message(
        body=mensaje.body,
        delivery_mode=DeliveryMode.PERSISTENT,
        content_type="application/json",
        message_id=mensaje.message_id,
        correlation_id=mensaje.correlation_id,
        headers={**(mensaje.headers or {}), "x-intentos": intentos},
    )
    await _exchange.publish(nuevo, routing_key=ajustes.cola_reintento,
                            mandatory=True)


async def _a_dlq(mensaje: aio_pika.abc.AbstractIncomingMessage) -> None:
    await conectar()
    dlq_msg = Message(
        body=mensaje.body,
        delivery_mode=DeliveryMode.PERSISTENT,
        content_type="application/json",
        message_id=mensaje.message_id,
        headers={**(mensaje.headers or {}),
                 "x-motivo": "procesamiento-fallido-o-cuerpo-invalido"},
    )
    await _dlx.publish(dlq_msg, routing_key=ajustes.cola_dlq, mandatory=True)


# ---------------------------------------------------------------- outbox relay
async def arrancar_relay_outbox(consultar: Callable[[], list[dict]],
                                marcar: Callable[[str], None]) -> None:
    """Relay del outbox (P2-REQ-039): publica filas pendientes con confirm.

    Vive en el propio servicio (no es un quinto microservicio).
    """
    global _tarea_outbox

    async def _bucle() -> None:
        while True:
            try:
                pendientes = await asyncio.to_thread(consultar)
                for fila in pendientes:
                    await publicar(fila["routing_key"], fila["mensaje"])
                    await asyncio.to_thread(marcar, fila["id"])
            except asyncio.CancelledError:
                raise
            except Exception as exc:                      # noqa: BLE001
                logger.warning("relay outbox: %s (se reintenta)", exc)
            await asyncio.sleep(ajustes.intervalo_outbox_seg)

    _tarea_outbox = asyncio.create_task(_bucle())
    logger.info("relay de outbox arrancado")
