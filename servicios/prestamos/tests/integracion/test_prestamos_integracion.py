"""Pruebas de INTEGRACIÓN del servicio Préstamos: RabbitMQ y PostgreSQL reales.

Sin mocks de broker ni de BD: el consumidor y el relay de outbox corren dentro
de la aplicación (lifespan) contra los contenedores de `docker compose up -d`.
Los vecinos (Clientes/Productos) se sustituyen por sus respuestas reales ya
verificadas en sus propias suites: aquí el doble declarado es SOLO su HTTP.
"""
import asyncio
import json
import os
import sys
import time
import uuid
from pathlib import Path
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

os.environ.setdefault(
    "DATABASE_URL",
    "postgresql+psycopg://svc_prestamos:CAMBIAR_pre_local@localhost:5434/credimarket",
)
os.environ.setdefault("BROKER_URL",
                      "amqp://credimarket:CAMBIAR_rabbit_local@localhost:5672/%2Fcredimarket")
os.environ.setdefault("JWT_SECRET", "CAMBIAR_jwt_local_largo_32+")
os.environ.setdefault("INTERVALO_OUTBOX_SEG", "1")
os.environ.setdefault("INTERVALO_RECHARGA_MODELO_SEG", "2")
# El artefacto promovido vive en el repo (volumen que Compose monta en /modelos).
# parents: [0]=integracion, [1]=tests, [2]=prestamos, [3]=servicios, [4]=raíz.
os.environ.setdefault("MODELO_DIR",
                      str(Path(__file__).resolve().parents[4] / "ml" / "modelos"))

import aio_pika                                        # noqa: E402
import jwt                                             # noqa: E402
from fastapi.testclient import TestClient              # noqa: E402

from app.config import ajustes                         # noqa: E402
from app.main import app                               # noqa: E402

PRODUCTO = "PROD-INTEG-1"
COTIZACION = {"producto_id": PRODUCTO, "precio_cop": 250000.0, "version": 3,
              "vigente_desde": "2026-11-01T00:00:00Z"}
PERFIL_BUENO = {"cliente_id": None, "activo": True,
                "ingresos_mensuales_cop": 6_000_000, "obligaciones_mensuales_cop": 700_000,
                "tipo_empleo": "dependiente", "antiguedad_laboral_meses": 60,
                "meses_historial_crediticio": 72, "creditos_previos": 1,
                "atrasos_previos_30d": 0, "porcentaje_pago_puntual": 98}
PERFIL_MALO = {"cliente_id": None, "activo": True,
               "ingresos_mensuales_cop": 2_000_000, "obligaciones_mensuales_cop": 2_400_000,
               "tipo_empleo": "independiente", "antiguedad_laboral_meses": 6,
               "meses_historial_crediticio": 12, "creditos_previos": 3,
               "atrasos_previos_30d": 2, "porcentaje_pago_puntual": 65}


def _cliente(perfil: dict):
    """Sustituto declarado de la llamada HTTP a Clientes (vecino real)."""
    return dict(perfil, cliente_id=perfil.get("cliente_id"))


def _token(rol: str, cliente_id: str | None = None) -> dict:
    token = jwt.encode({"sub": "u", "rol": rol, "cliente_id": cliente_id,
                        "exp": int(time.time()) + 3600},
                       ajustes.jwt_secret, algorithm=ajustes.jwt_algorithm)
    return {"Authorization": f"Bearer {token}"}


def _clave() -> str:
    return f"k-{uuid.uuid4().hex[:10]}"


def _solicitud(cliente_id: str, cantidad: int = 2, plazo: int = 12) -> dict:
    return {"cliente_id": cliente_id, "producto_id": PRODUCTO,
            "cantidad": cantidad, "plazo_meses": plazo}


def _publicar(routing_key: str, evento: dict) -> None:
    async def _enviar():
        conn = await aio_pika.connect_robust(ajustes.broker_url, timeout=10)
        try:
            canal = await conn.channel(publisher_confirms=True)
            exchange = await canal.declare_exchange(
                ajustes.exchange, aio_pika.ExchangeType.TOPIC, durable=True)
            mensaje = aio_pika.Message(
                body=json.dumps(evento).encode("utf-8"),
                delivery_mode=aio_pika.DeliveryMode.PERSISTENT,
                message_id=evento["event_id"])
            await exchange.publish(mensaje, routing_key=routing_key, mandatory=True)
        finally:
            await conn.close()

    asyncio.run(_enviar())


def _evento(tipo: str, prestamo_id: str, payload: dict) -> dict:
    return {"event_id": str(uuid.uuid4()), "type": tipo, "schema_version": 1,
            "occurred_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
            "correlation_id": prestamo_id, "prestamo_id": prestamo_id,
            "producer": "inventario", "payload": payload}


def _esperar(consulta, timeout: float = 25, mensaje: str = ""):
    limite = time.time() + timeout
    while time.time() < limite:
        resultado = consulta()
        if resultado:
            return resultado
        time.sleep(0.5)
    raise AssertionError(f"timeout esperando: {mensaje}")


def _vecinos(perfil: dict):
    """Parchea las dos consultas vecinas (Clientes y Productos) a la vez."""
    return (patch("app.servicio.perfil_cliente", return_value=_cliente(perfil)),
            patch("app.servicio.cotizar_producto", return_value=COTIZACION))


# ---------------------------------------------------------------------- pruebas
def test_flujo_completo_hasta_completada():
    """§12/#1: 202 → reserva confirmada (APROBADA) → entrega (COMPLETADA)."""
    cliente_id = str(uuid.uuid4())
    p_perfil, p_cotiza = _vecinos(PERFIL_BUENO)
    with p_perfil, p_cotiza, TestClient(app) as cliente:
        headers = {**_token("cliente", cliente_id), "Idempotency-Key": _clave()}
        creada = cliente.post("/prestamos", headers=headers,
                              json=_solicitud(cliente_id))
        assert creada.status_code == 202, creada.text
        cuerpo = creada.json()
        assert cuerpo["estado"] == "PENDIENTE_INVENTARIO"
        assert cuerpo["umbral"] > cuerpo["probabilidad_incumplimiento"]
        assert cuerpo["precio_unitario_cop"] == 250000.0     # precio de Productos
        prestamo_id = cuerpo["prestamo_id"]

        # Inventario confirma la reserva (T3)
        _publicar("inventario.reserva.reservada", _evento(
            "inventario.reserva.reservada", prestamo_id,
            {"prestamo_id": prestamo_id, "reserva_id": "R-1",
             "producto_id": PRODUCTO, "cantidad": 2}))
        _esperar(lambda: cliente.get(f"/prestamos/{prestamo_id}",
                                     headers=_token("cliente", cliente_id))
                 .json()["estado"] == "APROBADA", mensaje="APROBADA")

        # Inventario confirma la salida (T6)
        _publicar("inventario.salida.confirmada", _evento(
            "inventario.salida.confirmada", prestamo_id,
            {"prestamo_id": prestamo_id, "entregado_en": "2026-11-01T00:00:00Z"}))
        final = _esperar(
            lambda: cliente.get(f"/prestamos/{prestamo_id}",
                                headers=_token("cliente", cliente_id)).json()
            if cliente.get(f"/prestamos/{prestamo_id}",
                           headers=_token("cliente", cliente_id))
            .json()["estado"] == "COMPLETADA" else None,
            mensaje="COMPLETADA")
        assert "entrega confirmada" in final["motivo"]


def test_rechazo_por_regla_no_pide_inventario():
    """§4: obligaciones ≥ ingresos → 201 RECHAZADA por regla, sin reserva."""
    cliente_id = str(uuid.uuid4())
    p_perfil, p_cotiza = _vecinos(PERFIL_MALO)
    with p_perfil, p_cotiza, TestClient(app) as cliente:
        headers = {**_token("cliente", cliente_id), "Idempotency-Key": _clave()}
        r = cliente.post("/prestamos", headers=headers,
                         json=_solicitud(cliente_id))
        assert r.status_code == 201, r.text
        assert r.json()["estado"] == "RECHAZADA"
        assert "regla de control" in r.json()["motivo"]
        assert r.json()["probabilidad_incumplimiento"] == 1.0


def test_idempotencia_misma_clave_y_conflicto():
    """§9/#12: misma clave + mismo cuerpo → misma respuesta; distinto → 409."""
    cliente_id = str(uuid.uuid4())
    p_perfil, p_cotiza = _vecinos(PERFIL_BUENO)
    with p_perfil, p_cotiza, TestClient(app) as cliente:
        clave = _clave()
        headers = {**_token("cliente", cliente_id), "Idempotency-Key": clave}
        primera = cliente.post("/prestamos", headers=headers,
                               json=_solicitud(cliente_id))
        segunda = cliente.post("/prestamos", headers=headers,
                               json=_solicitud(cliente_id))
        assert primera.status_code == segunda.status_code
        assert primera.json()["prestamo_id"] == segunda.json()["prestamo_id"]

        # cuerpo distinto con la misma clave → 409
        conflicto = cliente.post("/prestamos", headers=headers,
                                 json=_solicitud(cliente_id, cantidad=5))
        assert conflicto.status_code == 409

        # sin cabecera → 400 con problem+json
        sin_clave = cliente.post("/prestamos",
                                 headers=_token("cliente", cliente_id),
                                 json=_solicitud(cliente_id))
        assert sin_clave.status_code == 400
        assert sin_clave.headers["content-type"].startswith("application/problem+json")


def test_cancelacion_desde_aprobada_termina_en_cancelada():
    """§4/T7: cancelar con reserva confirmada espera `liberada` para CANCELADA."""
    cliente_id = str(uuid.uuid4())
    p_perfil, p_cotiza = _vecinos(PERFIL_BUENO)
    with p_perfil, p_cotiza, TestClient(app) as cliente:
        headers = {**_token("cliente", cliente_id), "Idempotency-Key": _clave()}
        creada = cliente.post("/prestamos", headers=headers,
                              json=_solicitud(cliente_id)).json()
        prestamo_id = creada["prestamo_id"]

        _publicar("inventario.reserva.reservada", _evento(
            "inventario.reserva.reservada", prestamo_id,
            {"prestamo_id": prestamo_id, "reserva_id": "R-2"}))
        _esperar(lambda: cliente.get(f"/prestamos/{prestamo_id}",
                                     headers=_token("cliente", cliente_id))
                 .json()["estado"] == "APROBADA", mensaje="APROBADA")

        cancelada = cliente.post(f"/prestamos/{prestamo_id}/cancelar",
                                 headers=_token("cliente", cliente_id))
        assert cancelada.status_code == 202
        assert cancelada.json()["cancelacion_en_curso"] is True

        _publicar("inventario.reserva.liberada", _evento(
            "inventario.reserva.liberada", prestamo_id,
            {"prestamo_id": prestamo_id, "reserva_id": "R-2"}))
        final = _esperar(
            lambda: cliente.get(f"/prestamos/{prestamo_id}",
                                headers=_token("cliente", cliente_id)).json()
            if cliente.get(f"/prestamos/{prestamo_id}",
                           headers=_token("cliente", cliente_id))
            .json()["estado"] == "CANCELADA" else None,
            mensaje="CANCELADA tras liberada")
        assert "cancelación confirmada" in final["motivo"]


def test_evento_tardio_no_reactiva_un_prestamo_completado():
    """§4/T9: un `reservada` tardío sobre un préstamo COMPLETADA no cambia nada."""
    cliente_id = str(uuid.uuid4())
    p_perfil, p_cotiza = _vecinos(PERFIL_BUENO)
    with p_perfil, p_cotiza, TestClient(app) as cliente:
        headers = {**_token("cliente", cliente_id), "Idempotency-Key": _clave()}
        prestamo_id = cliente.post("/prestamos", headers=headers,
                                   json=_solicitud(cliente_id)).json()["prestamo_id"]

        _publicar("inventario.reserva.reservada", _evento(
            "inventario.reserva.reservada", prestamo_id, {"prestamo_id": prestamo_id}))
        _esperar(lambda: cliente.get(f"/prestamos/{prestamo_id}",
                                     headers=_token("cliente", cliente_id))
                 .json()["estado"] == "APROBADA", mensaje="APROBADA")
        _publicar("inventario.salida.confirmada", _evento(
            "inventario.salida.confirmada", prestamo_id,
            {"prestamo_id": prestamo_id, "entregado_en": "2026-11-01T00:00:00Z"}))
        _esperar(lambda: cliente.get(f"/prestamos/{prestamo_id}",
                                     headers=_token("cliente", cliente_id))
                 .json()["estado"] == "COMPLETADA", mensaje="COMPLETADA")

        # evento tardío (§4): no reactiva ni cambia el estado final
        _publicar("inventario.reserva.reservada", _evento(
            "inventario.reserva.reservada", prestamo_id, {"prestamo_id": prestamo_id}))
        time.sleep(5)
        assert cliente.get(f"/prestamos/{prestamo_id}",
                           headers=_token("cliente", cliente_id)
                           ).json()["estado"] == "COMPLETADA"


def test_propiedad_del_recurso_y_modelo():
    """§12.13/#13: 403 si el préstamo es de otro cliente; admin ve todo."""
    cliente_id, otro = str(uuid.uuid4()), str(uuid.uuid4())
    p_perfil, p_cotiza = _vecinos(PERFIL_BUENO)
    with p_perfil, p_cotiza, TestClient(app) as cliente:
        headers = {**_token("cliente", cliente_id), "Idempotency-Key": _clave()}
        prestamo_id = cliente.post("/prestamos", headers=headers,
                                   json=_solicitud(cliente_id)).json()["prestamo_id"]

        assert cliente.get(f"/prestamos/{prestamo_id}",
                           headers=_token("cliente", otro)).status_code == 403
        assert cliente.get(f"/prestamos/{prestamo_id}",
                           headers=_token("administrador")).status_code == 200

        # el listado de un cliente solo trae lo suyo
        propios = cliente.get("/prestamos", headers=_token("cliente", cliente_id)).json()
        assert all(p["cliente_id"] == cliente_id for p in propios["items"])
        todos = cliente.get("/prestamos", headers=_token("administrador")).json()
        assert todos["total"] >= propios["total"]


def test_inferencia_aislada_no_crea_prestamo():
    """§8.E: /riesgo/predict decide sin reservar inventario ni crear préstamo."""
    p_perfil, p_cotiza = _vecinos(PERFIL_BUENO)
    with p_perfil, p_cotiza, TestClient(app) as cliente:
        antes = cliente.get("/prestamos", headers=_token("administrador")).json()["total"]
        r = cliente.post("/riesgo/predict", headers=_token("servicio"), json={
            "ingresos_mensuales_cop": 8_000_000, "obligaciones_mensuales_cop": 400_000,
            "monto_solicitado_cop": 1_500_000, "plazo_meses": 12,
            "tipo_empleo": "dependiente", "antiguedad_laboral_meses": 48,
            "meses_historial_crediticio": 60, "creditos_previos": 1,
            "atrasos_previos_30d": 0, "porcentaje_pago_puntual": 97})
        assert r.status_code == 200, r.text
        assert r.json()["decision"] in ("FAVORABLE", "DESFAVORABLE")
        assert 0.0 <= r.json()["probabilidad_incumplimiento"] <= 1.0
        despues = cliente.get("/prestamos", headers=_token("administrador")).json()["total"]
        assert despues == antes, "la inferencia creó un préstamo"


def test_promocion_y_rollback_del_modelo_activo():
    """§8.D: promoción explícita + rollback desde la API, con recarga."""
    with TestClient(app) as cliente:
        admin = _token("administrador")
        info = cliente.get("/modelo/info", headers=admin).json()
        original = info["modelo_version"]
        otro = "v2" if original == "v1" else "v1"

        promovida = cliente.post("/admin/modelo/promover", headers=admin,
                                 json={"modelo_version": otro,
                                       "motivo": "prueba de integración"})
        assert promovida.status_code == 200, promovida.text
        assert promovida.json()["modelo_version"] == otro
        assert promovida.json()["version_anterior"] == original

        _esperar(lambda: cliente.get("/modelo/info", headers=admin).json()
                 ["modelo_version"] == otro, mensaje="recarga del modelo promovido")

        revertida = cliente.post("/admin/modelo/rollback", headers=admin)
        assert revertida.status_code == 200
        assert revertida.json()["modelo_version"] == original
        _esperar(lambda: cliente.get("/modelo/info", headers=admin).json()
                 ["modelo_version"] == original, mensaje="rollback cargado")


def test_ready_reporta_503_sin_modelo():
    """§8.E: sin modelo activo el servicio no está listo (503)."""
    with TestClient(app) as cliente:
        assert cliente.get("/ready").status_code == 200
    # simula la ausencia del artefacto: el endpoint debe negar la listitud
    from app import modelo
    with TestClient(app) as cliente:
        with patch.object(modelo, "disponible", return_value=False), \
                patch.object(modelo, "error_carga", return_value="sin artefacto"):
            r = cliente.get("/ready")
            assert r.status_code == 503
            assert r.json()["modelo"] is False
            assert "sin modelo activo" in r.json()["detalle"]


def test_salud_publica():
    with TestClient(app) as cliente:
        assert cliente.get("/health").json()["estado"] == "ok"


# ------------------------------------------------------ monitoreo (P2-9, §15.2)
def test_monitoreo_registra_la_decision_y_reporta_estado():
    """P2-TEST-020: toda decisión deja métrica (misma transacción) y
    `GET /monitoreo/estado` resume latencias, tasas y deriva."""
    cliente_id = str(uuid.uuid4())
    p_perfil, p_cotiza = _vecinos(PERFIL_BUENO)
    with p_perfil, p_cotiza, TestClient(app) as cliente:
        admin = _token("administrador")
        antes = cliente.get("/monitoreo/estado", headers=admin).json()

        headers = {**_token("cliente", cliente_id), "Idempotency-Key": _clave()}
        creada = cliente.post("/prestamos", headers=headers,
                              json=_solicitud(cliente_id))
        assert creada.status_code == 202, creada.text

        # la inferencia aislada también deja su métrica (origen "inferencia")
        cliente.post("/riesgo/predict", headers=_token("servicio"), json={
            "ingresos_mensuales_cop": 7_000_000, "obligaciones_mensuales_cop": 600_000,
            "monto_solicitado_cop": 900_000, "plazo_meses": 9,
            "tipo_empleo": "dependiente", "antiguedad_laboral_meses": 30,
            "meses_historial_crediticio": 40, "creditos_previos": 1,
            "atrasos_previos_30d": 0, "porcentaje_pago_puntual": 96})

        estado = cliente.get("/monitoreo/estado", headers=admin).json()
        assert estado["total_inferencias"] >= antes["total_inferencias"] + 2
        assert estado["latencia_ms"]["p50"] is not None
        assert estado["latencia_ms"]["p95"] >= estado["latencia_ms"]["p50"]
        assert estado["probabilidad_media"] is not None
        assert estado["linea_base"]["fuente"].endswith("entrenamiento.csv")
        assert estado["deriva"]["estado"] in (
            "estable", "revisar", "alerta", "insuficiente")
        # solo administrador (§10)
        assert cliente.get("/monitoreo/estado",
                           headers=_token("cliente", cliente_id)).status_code == 403


def test_evaluar_lote_psi_contra_la_linea_base():
    """P2-9.4: evalúa un lote (200 filas reales) sin crear nada (§8.E)."""
    import csv as _csv
    lote_csv = Path(__file__).resolve().parents[4] / "ml" / "datos" / "entrenamiento.csv"
    with TestClient(app) as cliente:
        admin = _token("administrador")
        def _numero(fila: dict, clave: str, convertidor=float):
            """Los vacíos del histórico son faltantes legítimos (None)."""
            crudo = (fila.get(clave) or "").strip()
            return convertidor(crudo) if crudo else None

        with lote_csv.open(encoding="utf-8-sig", newline="") as archivo:
            filas = []
            for fila in _csv.DictReader(archivo):
                filas.append({
                    "ingresos_mensuales_cop": _numero(fila, "ingresos_mensuales_cop"),
                    "obligaciones_mensuales_cop":
                        _numero(fila, "obligaciones_mensuales_cop"),
                    "tipo_empleo": fila["tipo_empleo"],
                    "antiguedad_laboral_meses":
                        _numero(fila, "antiguedad_laboral_meses"),
                    "meses_historial_crediticio":
                        _numero(fila, "meses_historial_crediticio"),
                    "creditos_previos": _numero(fila, "creditos_previos", int),
                    "atrasos_previos_30d": _numero(fila, "atrasos_previos_30d", int),
                    "porcentaje_pago_puntual": _numero(fila, "porcentaje_pago_puntual"),
                    "monto_solicitado_cop": _numero(fila, "monto_solicitado_cop"),
                    "plazo_meses": _numero(fila, "plazo_meses", int),
                    "cuota_estimada_cop": _numero(fila, "cuota_estimada_cop"),
                })
                if len(filas) == 200:
                    break

        antes = cliente.get("/prestamos", headers=_token("administrador")).json()["total"]
        r = cliente.post("/monitoreo/evaluar-lote", headers=admin,
                         json={"origen": "prueba_integracion", "filas": filas})
        assert r.status_code == 200, r.text
        cuerpo = r.json()        # un lote de la MISMA distribución base no puede acusar alerta de deriva
        assert cuerpo["estado"] in ("estable", "revisar"), cuerpo
        assert cuerpo["psi_maximo"] < 0.25
        assert len(cuerpo["por_variable"]) == 11
        assert cuerpo["linea_base"]["filas"] > 0
        # evaluar un lote no crea ni toca préstamos (§8.E)
        despues = cliente.get("/prestamos", headers=_token("administrador")).json()["total"]
        assert despues == antes

        # validaciones: lote vacío y campos extra → 400 problem+json
        vacio = cliente.post("/monitoreo/evaluar-lote", headers=admin,
                             json={"filas": []})
        assert vacio.status_code == 400
        assert vacio.headers["content-type"].startswith("application/problem+json")
        extra = cliente.post("/monitoreo/evaluar-lote", headers=admin,
                             json={"filas": filas[:1], "incluir_secreto": True})
        assert extra.status_code == 400
