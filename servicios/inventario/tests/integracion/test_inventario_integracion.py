"""Pruebas de INTEGRACIÓN del servicio Inventario: RabbitMQ y PostgreSQL reales.

Sin mocks: el consumidor, el relay de outbox y el bucle de vencimientos corren
dentro de la aplicación (lifespan) contra los contenedores de `docker compose up -d`.
"""
import asyncio
import json
import os
import sys
import time
import uuid
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

os.environ.setdefault(
    "DATABASE_URL",
    "postgresql+psycopg://svc_inventario:CAMBIAR_inv_local@localhost:5434/credimarket",
)
os.environ.setdefault("BROKER_URL",
                      "amqp://credimarket:CAMBIAR_rabbit_local@localhost:5672/%2Fcredimarket")
os.environ.setdefault("JWT_SECRET", "CAMBIAR_jwt_local_largo_32+")
os.environ.setdefault("INTERVALO_VENCIMIENTO_SEG", "2")
os.environ.setdefault("INTERVALO_OUTBOX_SEG", "1")

import aio_pika                                        # noqa: E402
import jwt                                             # noqa: E402
import requests                                         # noqa: E402
from fastapi.testclient import TestClient              # noqa: E402

from app.broker import construir_evento                # noqa: E402
from app.config import ajustes                         # noqa: E402
from app.main import app                               # noqa: E402

ADMIN = {"Authorization": f"Bearer {jwt.encode({'sub': 'a', 'rol': 'administrador', 'exp': int(time.time()) + 3600}, ajustes.jwt_secret, algorithm='HS256')}"}
SERVICIO = {"Authorization": f"Bearer {jwt.encode({'sub': 's', 'rol': 'servicio', 'exp': int(time.time()) + 3600}, ajustes.jwt_secret, algorithm='HS256')}"}


# ----------------------------------------------------------------- utilidades
def publicar(routing_key: str, evento: dict) -> None:
    """Publicador independiente (proceso de prueba) con publisher confirm."""

    async def _enviar():
        conn = await aio_pika.connect_robust(ajustes.broker_url, timeout=10)
        try:
            canal = await conn.channel(publisher_confirms=True)
            exchange = await canal.declare_exchange(
                ajustes.exchange, aio_pika.ExchangeType.TOPIC, durable=True)
            mensaje = aio_pika.Message(
                body=json.dumps(evento).encode("utf-8"),
                delivery_mode=aio_pika.DeliveryMode.PERSISTENT,
                message_id=evento["event_id"],
            )
            await exchange.publish(mensaje, routing_key=routing_key, mandatory=True)
        finally:
            await conn.close()

    asyncio.run(_enviar())


class Capturador:
    """Cola propia ligada a `inventario.#` para observar lo que publica el relay."""

    def __init__(self):
        # Bucle propio: la conexión y sus futuros deben compartir el mismo loop.
        self._loop = asyncio.new_event_loop()
        self._conn, self._cola = self._loop.run_until_complete(self._preparar())

    async def _preparar(self):
        conn = await aio_pika.connect_robust(ajustes.broker_url, timeout=10)
        canal = await conn.channel()
        exchange = await canal.declare_exchange(
            ajustes.exchange, aio_pika.ExchangeType.TOPIC, durable=True)
        cola = await canal.declare_queue(f"test-captura-{uuid.uuid4().hex[:6]}",
                                         auto_delete=True, exclusive=True)
        await cola.bind(exchange, routing_key="inventario.#")
        return conn, cola

    def _siguiente(self) -> dict | None:
        envio = self._loop.run_until_complete(
            self._cola.get(no_ack=True, fail=False, timeout=1))
        if envio is None:
            return None
        return json.loads(envio.body.decode("utf-8"))

    def esperar(self, tipo: str, prestamo_id: str, timeout: float = 25) -> dict | None:
        limite = time.time() + timeout
        while time.time() < limite:
            evento = self._siguiente()
            if evento is None:
                continue
            if evento.get("type") == tipo and \
                    evento.get("payload", {}).get("prestamo_id") == prestamo_id:
                return evento
        return None

    def cerrar(self):
        try:
            self._loop.run_until_complete(self._conn.close())
        finally:
            self._loop.close()


def _esperar(condicion, timeout: float = 20, mensaje: str = ""):
    limite = time.time() + timeout
    while time.time() < limite:
        if condicion():
            return True
        time.sleep(0.5)
    raise AssertionError(f"timeout esperando: {mensaje}")


def _comando(prestamo_id: str, producto_id: str, cantidad: int,
             vence_en: str | None = None) -> dict:
    payload = {"prestamo_id": prestamo_id, "producto_id": producto_id,
               "cantidad": cantidad, "plazo_dias": 180}
    if vence_en:
        payload["vence_en"] = vence_en
    return construir_evento("prestamo.reserva.solicitada", prestamo_id, prestamo_id,
                            payload, productor="prestamos")


def _clave() -> str:
    return f"PRE-{uuid.uuid4().hex[:8].upper()}"


# ---------------------------------------------------------------------- pruebas
def test_reserva_atomica_y_evento_reservada():
    """§12.3/#4: reserva atómica, outbox confirmado y `inventario.reserva.reservada`."""
    captura = Capturador()
    try:
        with TestClient(app) as cliente:
            producto = f"PROD-{uuid.uuid4().hex[:6]}"
            entrada = cliente.post("/entradas", headers=ADMIN,
                                   json={"producto_id": producto, "cantidad": 5})
            assert entrada.status_code == 201, entrada.text
            assert entrada.json()["disponible"] == 5

            prestamo = _clave()
            publicar("prestamo.reserva.solicitada", _comando(prestamo, producto, 2))

            evento = captura.esperar("inventario.reserva.reservada", prestamo)
            assert evento is not None, "no llegó inventario.reserva.reservada"
            assert evento["payload"]["producto_id"] == producto
            for campo in ("event_id", "type", "schema_version", "occurred_at",
                          "correlation_id", "prestamo_id", "producer"):
                assert campo in evento

            # el efecto está en BD: reservada=2 y disponible=3
            existencia = cliente.get(f"/existencias/{producto}", headers=ADMIN).json()
            assert existencia["reservada"] == 2 and existencia["disponible"] == 3

            # la reserva quedó registrada y el outbox fue confirmado (publicado_en)
            reservas = cliente.get("/reservas", headers=SERVICIO).json()
            mia = [r for r in reservas if r["prestamo_id"] == prestamo]
            assert len(mia) == 1 and mia[0]["estado"] == "RESERVADA"
            pendientes = cliente.get("/outbox/pendiente", headers=SERVICIO).json()
            assert pendientes == []          # relay publicó todo con confirm

            movimientos = cliente.get("/movimientos", headers=ADMIN).json()
            assert any(m["tipo"] == "RESERVA" and m["producto_id"] == producto
                       for m in movimientos)
    finally:
        captura.cerrar()


def test_evento_duplicado_no_repite_el_efecto():
    """§12.5 / prueba #5: mismo `event_id` reprocesado → un solo efecto."""
    captura = Capturador()
    try:
        with TestClient(app) as cliente:
            producto = f"PROD-{uuid.uuid4().hex[:6]}"
            cliente.post("/entradas", headers=ADMIN,
                         json={"producto_id": producto, "cantidad": 4})
            prestamo = _clave()
            evento = _comando(prestamo, producto, 3)

            publicar("prestamo.reserva.solicitada", evento)
            assert captura.esperar("inventario.reserva.reservada", prestamo) is not None

            publicar("prestamo.reserva.solicitada", evento)     # duplicado exacto
            time.sleep(3)                                       # margen de reproceso

            reservas = [r for r in cliente.get("/reservas", headers=SERVICIO).json()
                        if r["prestamo_id"] == prestamo]
            assert len(reservas) == 1, "el duplicado creó una segunda reserva"
            existencia = cliente.get(f"/existencias/{producto}", headers=ADMIN).json()
            assert existencia["reservada"] == 3      # no se reservó dos veces
    finally:
        captura.cerrar()


def test_reserva_insuficiente_no_deja_stock_negativo():
    """§12.3: sin existencias suficientes → `inventario.reserva.insuficiente`."""
    captura = Capturador()
    try:
        with TestClient(app) as cliente:
            producto = f"PROD-{uuid.uuid4().hex[:6]}"
            cliente.post("/entradas", headers=ADMIN,
                         json={"producto_id": producto, "cantidad": 1})
            prestamo = _clave()
            publicar("prestamo.reserva.solicitada", _comando(prestamo, producto, 9))

            evento = captura.esperar("inventario.reserva.insuficiente", prestamo)
            assert evento is not None, "no llegó inventario.reserva.insuficiente"
            assert evento["payload"]["disponible"] == 1
            assert evento["payload"]["solicitado"] == 9

            existencia = cliente.get(f"/existencias/{producto}", headers=ADMIN).json()
            assert existencia["reservada"] == 0 and existencia["disponible"] == 1
            reservas = [r for r in cliente.get("/reservas", headers=SERVICIO).json()
                        if r["prestamo_id"] == prestamo]
            assert reservas == []
    finally:
        captura.cerrar()


def test_dos_solicitudes_por_la_ultima_unidad():
    """§12.4: concurrencia sobre la última unidad → exactamente una reserva."""
    captura = Capturador()
    try:
        with TestClient(app) as cliente:
            producto = f"PROD-{uuid.uuid4().hex[:6]}"
            cliente.post("/entradas", headers=ADMIN,
                         json={"producto_id": producto, "cantidad": 1})
            p1, p2 = _clave(), _clave()
            publicar("prestamo.reserva.solicitada", _comando(p1, producto, 1))
            publicar("prestamo.reserva.solicitada", _comando(p2, producto, 1))

            _esperar(
                lambda: captura.esperar("inventario.reserva.reservada", p1, 1)
                is not None or captura.esperar("inventario.reserva.reservada", p2, 1)
                is not None, timeout=30, mensaje="reserva de alguna de las dos solicitudes")

            # deja margen a que la otra reciba la respuesta de insuficiencia
            time.sleep(4)
            existencia = cliente.get(f"/existencias/{producto}", headers=ADMIN).json()
            assert existencia["reservada"] == 1, "solo una de las dos pudo reservar"
            assert existencia["disponible"] == 0
            reservas = [r for r in cliente.get("/reservas", headers=SERVICIO).json()
                        if r["prestamo_id"] in (p1, p2)]
            assert len(reservas) == 1 and reservas[0]["estado"] == "RESERVADA"
    finally:
        captura.cerrar()


def test_cancelacion_libera_y_publica_liberada():
    """§4: la cancelación libera atómicamente y responde `inventario.reserva.liberada`."""
    captura = Capturador()
    try:
        with TestClient(app) as cliente:
            producto = f"PROD-{uuid.uuid4().hex[:6]}"
            cliente.post("/entradas", headers=ADMIN,
                         json={"producto_id": producto, "cantidad": 3})
            prestamo = _clave()
            publicar("prestamo.reserva.solicitada", _comando(prestamo, producto, 2))
            assert captura.esperar("inventario.reserva.reservada", prestamo) is not None

            publicar("prestamo.reserva.cancelada", construir_evento(
                "prestamo.reserva.cancelada", prestamo, prestamo,
                {"prestamo_id": prestamo, "motivo": "cancelacion_cliente"},
                productor="prestamos"))

            evento = captura.esperar("inventario.reserva.liberada", prestamo)
            assert evento is not None, "no llegó inventario.reserva.liberada"
            _esperar(lambda: cliente.get(f"/existencias/{producto}",
                                         headers=ADMIN).json()["reservada"] == 0,
                     mensaje="existencia liberada")
            existencia = cliente.get(f"/existencias/{producto}", headers=ADMIN).json()
            assert existencia["disponible"] == 3
    finally:
        captura.cerrar()


def test_entrega_confirmada_y_no_repetible():
    """§4: la entrega descuenta stock y publica `inventario.salida.confirmada`."""
    captura = Capturador()
    try:
        with TestClient(app) as cliente:
            producto = f"PROD-{uuid.uuid4().hex[:6]}"
            cliente.post("/entradas", headers=ADMIN,
                         json={"producto_id": producto, "cantidad": 2})
            prestamo = _clave()
            publicar("prestamo.reserva.solicitada", _comando(prestamo, producto, 2))
            assert captura.esperar("inventario.reserva.reservada", prestamo) is not None

            reservas = [r for r in cliente.get("/reservas", headers=SERVICIO).json()
                        if r["prestamo_id"] == prestamo]
            rid = reservas[0]["id"]

            entrega = cliente.post(f"/reservas/{rid}/entrega", headers=ADMIN)
            assert entrega.status_code == 200, entrega.text
            assert entrega.json()["estado"] == "ENTREGADA"
            assert captura.esperar("inventario.salida.confirmada", prestamo) is not None

            existencia = cliente.get(f"/existencias/{producto}", headers=ADMIN).json()
            assert existencia["total"] == 0 and existencia["reservada"] == 0

            # repetir la entrega → 409 (idempotencia/estado inválido)
            repetida = cliente.post(f"/reservas/{rid}/entrega", headers=ADMIN)
            assert repetida.status_code == 409
    finally:
        captura.cerrar()


def test_vencimiento_de_reserva_libera_y_notifica():
    """§4: la tarea periódica vence reservas y publica `inventario.reserva.vencida`."""
    captura = Capturador()
    try:
        with TestClient(app) as cliente:
            producto = f"PROD-{uuid.uuid4().hex[:6]}"
            cliente.post("/entradas", headers=ADMIN,
                         json={"producto_id": producto, "cantidad": 6})
            prestamo = _clave()
            vencido = (time.strftime("%Y-%m-%dT%H:%M:%SZ",
                                     time.gmtime(time.time() - 5)))
            publicar("prestamo.reserva.solicitada",
                     _comando(prestamo, producto, 4, vence_en=vencido))
            assert captura.esperar("inventario.reserva.reservada", prestamo) is not None

            # el bucle de vencimientos corre cada 2 s (INTERVALO_VENCIMIENTO_SEG)
            evento = captura.esperar("inventario.reserva.vencida", prestamo, timeout=30)
            assert evento is not None, "no llegó inventario.reserva.vencida"
            assert evento["payload"]["origen"] == "vencimiento"

            reservas = [r for r in cliente.get("/reservas", headers=SERVICIO).json()
                        if r["prestamo_id"] == prestamo]
            assert reservas[0]["estado"] == "VENCIDA"
            existencia = cliente.get(f"/existencias/{producto}", headers=ADMIN).json()
            assert existencia["reservada"] == 0 and existencia["disponible"] == 6
    finally:
        captura.cerrar()


def test_mensaje_invalido_termina_en_dead_letter():
    """Prueba extra P2-TEST-018: tras fallar el procesamiento → DLQ visible."""
    with TestClient(app) as cliente:
        producto = f"PROD-{uuid.uuid4().hex[:6]}"
        cliente.post("/entradas", headers=ADMIN,
                     json={"producto_id": producto, "cantidad": 1})
        prestamo = _clave()
        # payload incompleto: KeyError dentro del consumidor → 3 intentos → DLQ
        malo = construir_evento("prestamo.reserva.solicitada", prestamo, prestamo,
                                {"prestamo_id": prestamo}, productor="prestamos")
        publicar("prestamo.reserva.solicitada", malo)

        dlq = None
        for _ in range(20):
            respuesta = requests.get(
                "http://localhost:15672/api/queues/%2Fcredimarket/inventario.dlq",
                auth=("credimarket", "CAMBIAR_rabbit_local"), timeout=5)
            if respuesta.status_code == 200:
                dlq = respuesta.json().get("messages", 0)
                if dlq and dlq >= 1:
                    break
            time.sleep(2)
        assert dlq and dlq >= 1, f"la DLQ no recibió el mensaje (valor: {dlq})"


def test_salud_y_listo():
    with TestClient(app) as cliente:
        assert cliente.get("/health").json()["estado"] == "ok"
        listo = cliente.get("/ready")
        assert listo.status_code == 200
        assert listo.json()["bd"] is True and listo.json()["broker"] is True
