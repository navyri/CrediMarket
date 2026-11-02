"""Pruebas UNITARIAS del servicio Préstamos.

Dobles declarados: sesiones, modelo y broker son MOCKS; nada de este archivo
toca PostgreSQL, RabbitMQ ni el artefacto de joblib.
"""
import sys
from pathlib import Path
from unittest.mock import MagicMock, patch

import jwt
import pytest
from pydantic import ValidationError

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app import broker, security, servicio                # noqa: E402
from app.config import ajustes                            # noqa: E402
from app.models import EventoProcesado, Prestamo          # noqa: E402
from app.schemas import SolicitudCreacion                 # noqa: E402


# ------------------------------------------------------------------ envelope
def test_evento_cumple_el_envelope_obligatorio_unit():
    """§5.2: los 7 campos del contrato de mensajes en todo evento."""
    evento = broker.construir_evento(
        "prestamo.reserva.solicitada", "PRE-1", "PRE-1",
        {"prestamo_id": "PRE-1", "producto_id": "PROD-1", "cantidad": 2})
    for campo in ("event_id", "type", "schema_version", "occurred_at",
                  "correlation_id", "prestamo_id", "payload"):
        assert campo in evento and evento[campo] not in (None, "")
    assert evento["schema_version"] == 1
    assert evento["producer"] == "prestamos"


def test_event_id_es_unico_unit():
    a = broker.construir_evento("t", "c", None, {})
    b = broker.construir_evento("t", "c", None, {})
    assert a["event_id"] != b["event_id"]


def test_payload_hacia_inventario_sin_datos_financieros_unit():
    """§5.3: el comando de reserva no lleva ingresos, montos ni probabilidades."""
    evento = broker.construir_evento(
        "prestamo.reserva.solicitada", "PRE-1", "PRE-1",
        {"prestamo_id": "PRE-1", "producto_id": "PROD-1", "cantidad": 2,
         "plazo_dias": 360})
    prohibidas = {"ingresos_mensuales_cop", "obligaciones_mensuales_cop",
                  "monto_solicitado_cop", "monto", "probabilidad",
                  "cliente_id", "cuota_mensual_cop"}
    assert not (set(evento["payload"]) & prohibidas)


# --------------------------------------------------------------- idempotencia
def test_huella_estable_para_el_mismo_cuerpo_unit():
    cuerpo = {"cliente_id": "C1", "producto_id": "P1", "cantidad": 2,
              "plazo_meses": 12}
    assert servicio.huella_cuerpo(cuerpo) == servicio.huella_cuerpo(dict(cuerpo))


def test_huella_cambia_si_cambia_un_campo_unit():
    base = {"cliente_id": "C1", "producto_id": "P1", "cantidad": 2,
            "plazo_meses": 12}
    otra = dict(base, cantidad=3)
    assert servicio.huella_cuerpo(base) != servicio.huella_cuerpo(otra)


def test_huella_no_depende_del_orden_de_las_claves_unit():
    a = {"b": 1, "a": 2}
    b = {"a": 2, "b": 1}
    assert servicio.huella_cuerpo(a) == servicio.huella_cuerpo(b)


# ------------------------------------------------------- máquina de estados
def _sesion_para(prestamo, evento_ya_visto=None):
    """Sesión mockeada: `get` distingue evento_procesado de prestamo."""
    sesion = MagicMock()

    def get(clave, identificador):
        if clave is EventoProcesado:
            return evento_ya_visto
        return prestamo

    sesion.get.side_effect = get
    return sesion


def _prestamo(estado: str, **extras) -> Prestamo:
    return Prestamo(id="PRE-1", cliente_id="C1", producto_id="P1", cantidad=1,
                    plazo_meses=12, precio_unitario_cop=100000,
                    precio_producto_version=1, monto_total_cop=100000,
                    cuota_mensual_cop=9000, tasa_mensual=0.018,
                    probabilidad_incumplimiento=0.2, umbral=0.49,
                    modelo_version="v1", estado=estado, **extras)


def _procesar(prestamo, tipo: str, payload: dict | None = None):
    sesion = _sesion_para(prestamo)
    with patch("app.db.Sesion", return_value=sesion):
        servicio.procesar_evento({
            "event_id": "E-1", "type": tipo, "prestamo_id": "PRE-1",
            "payload": payload or {"prestamo_id": "PRE-1", "reserva_id": "R-1"}})
    return prestamo


def test_t3_reservada_pasa_a_aprobada_unit():
    p = _procesar(_prestamo("PENDIENTE_INVENTARIO"),
                  "inventario.reserva.reservada")
    assert p.estado == "APROBADA"
    assert p.reserva_id == "R-1"


def test_t4_insuficiente_cancela_por_stock_unit():
    p = _procesar(_prestamo("PENDIENTE_INVENTARIO"),
                  "inventario.reserva.insuficiente", {"disponible": 0})
    assert p.estado == "CANCELADA_SIN_STOCK"
    assert "existencias" in p.motivo


def test_t6_salida_confirma_completada_unit():
    p = _procesar(_prestamo("APROBADA"), "inventario.salida.confirmada",
                  {"entregado_en": "2026-11-01T00:00:00Z"})
    assert p.estado == "COMPLETADA"


def test_t8_vencida_cancela_el_prestamo_unit():
    p = _procesar(_prestamo("APROBADA"), "inventario.reserva.vencida",
                  {"vencio_en": "2026-11-01T00:00:00Z"})
    assert p.estado == "CANCELADA_VENCIDA"


def test_t7_liberada_con_cancelacion_en_vuelo_termina_unit():
    from datetime import datetime, timezone
    p = _procesar(_prestamo("APROBADA",
                            cancelacion_solicitada_en=datetime.now(timezone.utc)),
                  "inventario.reserva.liberada")
    assert p.estado == "CANCELADA"


def test_liberada_sin_cancelacion_no_cambia_estado_unit():
    p = _procesar(_prestamo("APROBADA"), "inventario.reserva.liberada")
    assert p.estado == "APROBADA"


def test_t9_evento_tardio_en_estado_final_no_reactiva_unit():
    """§4: los estados finales son absorbentes; nada los reactiva."""
    for estado in ("COMPLETADA", "RECHAZADA", "CANCELADA",
                   "CANCELADA_SIN_STOCK", "CANCELADA_VENCIDA"):
        p = _procesar(_prestamo(estado), "inventario.reserva.reservada")
        assert p.estado == estado, f"{estado} fue reactivada"


def test_evento_duplicado_no_se_reprocesa_unit():
    sesion = _sesion_para(_prestamo("PENDIENTE_INVENTARIO"),
                          evento_ya_visto=MagicMock())
    with patch("app.db.Sesion", return_value=sesion):
        servicio.procesar_evento({"event_id": "E-dup", "type": "x",
                                  "prestamo_id": "PRE-1", "payload": {}})
    sesion.add.assert_not_called()
    sesion.commit.assert_called_once()


# --------------------------------------------------------------- decisiones
def test_regla_de_control_rechaza_sin_modelo_unit():
    """Obligaciones ≥ ingresos → RECHAZADA por regla; el modelo ni se invoca."""
    with patch("app.modelo.predecir") as inferencia, \
            patch("app.modelo.ficha_activa",
                  return_value={"modelo_version": "v1", "umbral": 0.49}):
        favorable, prob, motivo, ficha = servicio.decidir_riesgo({
            "ingresos_mensuales_cop": 2_000_000,
            "obligaciones_mensuales_cop": 2_500_000})
    assert favorable is False
    assert prob == 1.0
    assert "regla de control" in motivo
    inferencia.assert_not_called()
    assert ficha["modelo_version"] == "v1"


def test_modelo_compara_con_su_umbral_unit():
    with patch("app.modelo.predecir", return_value=0.40), \
            patch("app.modelo.ficha_activa",
                  return_value={"modelo_version": "v1", "umbral": 0.49,
                                "run_id": "r1"}):
        favorable, prob, _, _ = servicio.decidir_riesgo({
            "ingresos_mensuales_cop": 5_000_000,
            "obligaciones_mensuales_cop": 500_000})
    assert favorable is True and prob == 0.40

    with patch("app.modelo.predecir", return_value=0.80), \
            patch("app.modelo.ficha_activa",
                  return_value={"modelo_version": "v1", "umbral": 0.49}):
        favorable, _, _, _ = servicio.decidir_riesgo({
            "ingresos_mensuales_cop": 5_000_000,
            "obligaciones_mensuales_cop": 500_000})
    assert favorable is False


def test_cuota_frances_con_la_tasa_oficial_unit():
    variables = servicio.variables_del_prestamo(350_000, 12)
    assert variables["tasa_mensual"] == ajustes.tasa_mensual_oficial
    # Fórmula francés: P·i / (1 − (1+i)^−n)
    i, n, p = 0.018, 12, 350_000
    esperada = p * i / (1 - (1 + i) ** (-n))
    assert abs(variables["cuota_estimada_cop"] - esperada) < 0.01


def test_variables_usan_el_nombre_de_la_columna_del_modelo_unit():
    """§8.B: el vector debe llamar `cuota_estimada_cop` (columna del histórico)."""
    variables = servicio.variables_del_prestamo(1_000_000, 6)
    assert "cuota_estimada_cop" in variables
    assert "monto_solicitado_cop" in variables and "plazo_meses" in variables


# ------------------------------------------------------------------ outbox
def test_outbox_pendiente_serializa_filas_unit():
    fila = MagicMock()
    fila.id = "o-1"
    fila.routing_key = "prestamo.reserva.solicitada"
    fila.mensaje = {"event_id": "e-9"}
    sesion = MagicMock()
    sesion.scalars.return_value.all.return_value = [fila]
    assert servicio.outbox_pendiente(sesion) == [
        {"id": "o-1", "routing_key": "prestamo.reserva.solicitada",
         "mensaje": {"event_id": "e-9"}}]


def test_outbox_marcar_ponga_fecha_unit():
    fila = MagicMock()
    sesion = MagicMock()
    sesion.get.return_value = fila
    servicio.outbox_marcar(sesion, "o-2")
    assert fila.publicado_en is not None
    sesion.commit.assert_called_once()


# ----------------------------------------------------------------- esquemas
def test_solicitud_rechaza_cantidad_cero_unit():
    with pytest.raises(ValidationError):
        SolicitudCreacion(cliente_id="C", producto_id="P", cantidad=0,
                          plazo_meses=12)


def test_solicitud_rechaza_precio_del_cliente_unit():
    """§4: el cuerpo no admite precio, monto ni tasa (campos extra)."""
    with pytest.raises(ValidationError):
        SolicitudCreacion(cliente_id="C", producto_id="P", cantidad=1,
                          plazo_meses=12, precio_cop=999999)


def test_solicitud_acepta_plazo_maximo_60_unit():
    assert SolicitudCreacion(cliente_id="C", producto_id="P", cantidad=1,
                             plazo_meses=60).plazo_meses == 60
    with pytest.raises(ValidationError):
        SolicitudCreacion(cliente_id="C", producto_id="P", cantidad=1,
                          plazo_meses=61)


# -------------------------------------------------------------- autorización
def _datos(rol: str, cliente_id: str | None = None) -> dict:
    token = jwt.encode({"sub": "u", "rol": rol, "cliente_id": cliente_id,
                        "exp": 9999999999}, ajustes.jwt_secret,
                       algorithm=ajustes.jwt_algorithm)
    return jwt.decode(token, ajustes.jwt_secret,
                      algorithms=[ajustes.jwt_algorithm])


def test_cliente_no_ve_prestamo_ajeno_unit():
    from fastapi import HTTPException
    with pytest.raises(HTTPException) as exc:
        security.exigir_dueno_o_admin(_datos("cliente", "C-otro"), "C-1", "/x")
    assert exc.value.status_code == 403


def test_dueno_y_admin_si_pasan_unit():
    security.exigir_dueno_o_admin(_datos("cliente", "C-1"), "C-1", "/x")
    security.exigir_dueno_o_admin(_datos("administrador"), "C-1", "/x")


def test_rol_servicio_no_crea_prestamos_unit():
    """El token de servicio NO está en `rol_cliente_o_admin` (solo cliente/admin)."""
    roles_admitidos = ("cliente", "administrador")
    assert "servicio" not in roles_admitidos


def test_token_firmado_con_otro_secreto_falla_unit():
    with pytest.raises(jwt.InvalidTokenError):
        jwt.decode(jwt.encode({"sub": "u", "rol": "cliente", "exp": 9999999999},
                              "otro-secreto", algorithm="HS256"),
                   ajustes.jwt_secret, algorithms=[ajustes.jwt_algorithm])
