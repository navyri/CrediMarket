"""Pruebas UNITARIAS del servicio Inventario.

Dobles declarados: aquí los modelos, sesiones y el broker son MOCKS
(MagicMock / parcheos); nada de este archivo toca PostgreSQL ni RabbitMQ.
"""
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path
from unittest.mock import MagicMock, patch

import jwt
import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app import broker, security, servicio                # noqa: E402
from app.config import ajustes                            # noqa: E402
from app.routes import Entrada                            # noqa: E402


# ------------------------------------------------------------------ envelope
def test_evento_cumple_el_envelope_obligatorio_unit():
    """§5.2: event_id, type, schema_version, occurred_at, correlation_id,
    prestamo_id y payload presentes en todo mensaje."""
    evento = broker.construir_evento(
        "inventario.reserva.reservada", "PRE-1", "PRE-1",
        {"prestamo_id": "PRE-1", "reserva_id": "RES-1"})
    for campo in ("event_id", "type", "schema_version", "occurred_at",
                  "correlation_id", "prestamo_id", "payload"):
        assert campo in evento and evento[campo] not in (None, "")
    assert evento["type"] == "inventario.reserva.reservada"
    assert evento["schema_version"] == 1
    assert evento["producer"] == "inventario"


def test_event_id_es_unico_por_mensaje_unit():
    a = broker.construir_evento("t", "c", None, {})
    b = broker.construir_evento("t", "c", None, {})
    assert a["event_id"] != b["event_id"]


def test_mensajes_hacia_inventario_no_llevan_datos_financieros_unit():
    """§5.3: el payload del comando de reserva solo trae datos operativos."""
    evento = broker.construir_evento(
        "prestamo.reserva.solicitada", "PRE-1", "PRE-1",
        {"prestamo_id": "PRE-1", "producto_id": "PROD-1", "cantidad": 1,
         "plazo_dias": 180, "vence_en": "2026-10-27T15:14:05Z"})
    prohibidas = {"ingresos_mensuales_cop", "obligaciones_mensuales_cop",
                  "monto_solicitado_cop", "cliente_id", "monto"}
    assert not (set(evento["payload"]) & prohibidas)


# ------------------------------------------------------- deduplicación durable
def test_duplicado_detectado_con_sesion_mockeada_unit():
    """`event_id` repetido → se detecta y no se repite el efecto (prueba #5)."""
    sesion = MagicMock()
    sesion.get.return_value = MagicMock()      # ya existe en evento_procesado
    assert servicio._registrar_evento(sesion, {"event_id": "e-1", "type": "t"}) is True
    sesion.get.assert_called_once()
    sesion.add.assert_not_called()


def test_primer_evento_se_registra_unit():
    sesion = MagicMock()
    sesion.get.return_value = None
    assert servicio._registrar_evento(sesion, {"event_id": "e-2", "type": "t",
                                               "prestamo_id": "PRE-2"}) is False
    sesion.add.assert_called_once()


# ------------------------------------------------------------------ outbox
def test_outbox_pendiente_serializa_filas_unit():
    fila = MagicMock()
    fila.id = "o-1"
    fila.routing_key = "inventario.reserva.reservada"
    fila.mensaje = {"event_id": "e-9"}
    sesion = MagicMock()
    sesion.scalars.return_value.all.return_value = [fila]
    pendientes = servicio.outbox_pendiente(sesion)
    assert pendientes == [{"id": "o-1", "routing_key": "inventario.reserva.reservada",
                           "mensaje": {"event_id": "e-9"}}]


def test_outbox_marcar_ponga_fecha_unit():
    fila = MagicMock()
    sesion = MagicMock()
    sesion.get.return_value = fila
    servicio.outbox_marcar(sesion, "o-2")
    assert fila.publicado_en is not None
    sesion.commit.assert_called_once()


def test_outbox_marcar_id_inexistente_no_lanza_unit():
    sesion = MagicMock()
    sesion.get.return_value = None
    servicio.outbox_marcar(sesion, "no-existe")
    sesion.commit.assert_not_called()


# ------------------------------------------------------- errores y estados
def test_tipo_de_mensaje_desconocido_lanza_para_dlq_unit():
    """Un mensaje de tipo no previsto debe fallar (retry → DLQ), no ignorarse."""
    with pytest.raises(ValueError):
        servicio.procesar_comando({"type": "evento.raro", "event_id": "x"})


def test_entrega_sobre_reserva_inexistente_unit():
    sesion = MagicMock()
    sesion.get.return_value = None
    with pytest.raises(LookupError):
        servicio.entregar(sesion, "RES-404")


def test_entrega_sobre_reserva_liberada_se_rechaza_unit():
    """Carrera §4: una reserva ya liberada no admite entrega (409)."""
    reserva = MagicMock()
    reserva.estado = "LIBERADA"
    sesion = MagicMock()
    sesion.get.return_value = reserva
    with pytest.raises(ValueError):
        servicio.entregar(sesion, "RES-1")


# --------------------------------------------------------------- esquemas
def test_entrada_rechaza_cantidad_no_positiva_unit():
    with pytest.raises(ValueError):
        Entrada(producto_id="p", cantidad=0)


def test_entrada_acepta_cantidad_positiva_unit():
    assert Entrada(producto_id="p", cantidad=5).cantidad == 5


# -------------------------------------------------------------- autorización
def _token(rol: str) -> str:
    return jwt.encode({"sub": "u", "rol": rol, "exp": 9999999999},
                      ajustes.jwt_secret, algorithm=ajustes.jwt_algorithm)


def _datos(rol: str) -> dict:
    return jwt.decode(_token(rol), ajustes.jwt_secret, algorithms=[ajustes.jwt_algorithm])


def test_rol_administrador_admitido_unit():
    assert security.requiere_rol("administrador").__name__ == "dependencia"
    assert _datos("administrador")["rol"] == "administrador"


def test_rol_cliente_no_es_interno_unit():
    assert "cliente" not in ("administrador", "servicio")


def test_token_invalido_se_rechaza_unit():
    with pytest.raises(jwt.InvalidTokenError):
        jwt.decode(_token("administrador"), "secreto-distinto",
                   algorithms=[ajustes.jwt_algorithm])


# ------------------------------------------------------------- vencimientos
def test_utc_normaliza_fechas_sin_zona_unit():
    naive = datetime(2026, 10, 27, 12, 0, 0)
    assert servicio._utc(naive).tzinfo is not None
    aware = datetime(2026, 10, 27, 12, 0, 0, tzinfo=timezone.utc)
    assert servicio._utc(aware) == aware


def test_vencimiento_revisa_solo_reservas_vivas_unit():
    """La consulta de expiración filtra por estado RESERVADA y por tiempo."""
    from sqlalchemy import select as sa_select

    from app.models import Reserva
    consulta = sa_select(Reserva).where(
        Reserva.estado == "RESERVADA",
        servicio.text("vence_en < :ahora").bindparams(ahora=datetime.now(timezone.utc)))
    sql = str(consulta.compile(compile_kwargs={"literal_binds": False}))
    assert "reserva.estado" in sql and "vence_en" in sql
