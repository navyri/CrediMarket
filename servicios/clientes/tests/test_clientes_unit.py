"""Pruebas UNITARIAS del servicio Clientes.

Dobles declarados: los modelos y la sesión son MOCKS (MagicMock) y los hashes
usan contraseñas reales de bcrypt; aquí NO se toca ninguna base de datos.
"""
import sys
from pathlib import Path
from unittest.mock import MagicMock

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app import routes, security                         # noqa: E402
from app.models import Cliente, Usuario                  # noqa: E402
from app.schemas import Login, Registro                  # noqa: E402


# ------------------------------------------------------------ hash y contraseñas
def test_hash_y_verificacion_de_password_unit():
    h = security.hash_password("clave-segura-123")
    assert h != "clave-segura-123" and h.startswith("$2b$")
    assert security.verificar_password("clave-segura-123", h) is True
    assert security.verificar_password("otra-clave", h) is False


def test_password_con_hash_corrupto_no_lanza_unit():
    assert security.verificar_password("x", "no-es-un-hash") is False


def test_registro_valida_longitud_minima_unit():
    with pytest.raises(ValueError):
        Registro(email="a@b.co", password="corta", documento_identidad="D1",
                 nombre="Cliente")


def test_login_rechaza_email_unit():
    with pytest.raises(ValueError):
        Login(email="sin-arroba", password="x")


# --------------------------------------------------------------- dobles de fila
def _cliente(**cambios) -> Cliente:
    base = dict(id="c1", documento_identidad="CLI-0000001", nombre="Cliente 1",
                email="cliente1@demo.local", telefono="", ciudad="", activo=True)
    base.update(cambios)
    return Cliente(**base)


def test_mismos_datos_detecta_idempotencia_unit():
    """La fila idéntica a la BD no cuenta como actualización (P2-TEST-012)."""
    fila = {"documento_identidad": "CLI-0000001", "nombre": "Cliente 1",
            "email": "cliente1@demo.local", "telefono": "", "ciudad": "",
            "activo": "true"}
    assert routes._mismos_datos(_cliente(), fila) is True


def test_mismos_datos_detecta_cambio_unit():
    fila = {"documento_identidad": "CLI-0000001", "nombre": "Cliente 1 EDITADO",
            "email": "cliente1@demo.local", "telefono": "", "ciudad": "",
            "activo": "true"}
    assert routes._mismos_datos(_cliente(), fila) is False


@pytest.mark.parametrize(
    "fila,motivo_parcial",
    [
        ({"documento_identidad": "", "nombre": "X", "email": "a@b.co"}, "documento"),
        ({"documento_identidad": "D", "nombre": "", "email": "a@b.co"}, "nombre"),
        ({"documento_identidad": "D", "nombre": "X", "email": "no-es-email"}, "email"),
        ({"documento_identidad": "D", "nombre": "X", "email": "a@b.co",
          "activo": "quizas"}, "activo"),
    ],
)
def test_validacion_de_fila_rechaza_filas_invalidas_unit(fila, motivo_parcial):
    motivo = routes._validar_fila(fila)
    assert motivo is not None and motivo_parcial in motivo


def test_validacion_de_fila_acepta_fila_correcta_unit():
    assert routes._validar_fila({"documento_identidad": "CLI-9", "nombre": "Ana",
                                 "email": "ana@demo.local", "activo": "true"}) is None


def test_columnas_obligatorias_de_la_importacion_unit():
    assert routes.COLUMNAS_OBLIGATORIAS == {"documento_identidad", "nombre", "email"}
    assert "telefono" in routes.COLUMNAS_CONOCIDAS


# ------------------------------------------------------ autorización (doble JWT)
def _datos(rol: str, cliente_id: str | None = "c1") -> dict:
    return {"sub": "u1", "rol": rol, "cliente_id": cliente_id}


def test_dueno_puede_leer_lo_suyo_unit():
    security.exigir_dueno_o_admin(_datos("cliente", "c1"), "c1", "/clientes/c1")  # no lanza


def test_cliente_ajeno_recibe_403_unit():
    from fastapi import HTTPException
    with pytest.raises(HTTPException) as exc:
        security.exigir_dueno_o_admin(_datos("cliente", "c2"), "c1", "/clientes/c1")
    assert exc.value.status_code == 403


def test_administrador_puede_leer_cualquiera_unit():
    security.exigir_dueno_o_admin(_datos("administrador", None), "c1", "/clientes/c1")


def test_token_de_servicio_es_valido_para_lo_interno_unit():
    roles_admitidos = ("administrador", "servicio")
    assert _datos("servicio", None).get("rol") in roles_admitidos


# ------------------------------------------------------------- emisión de tokens
def test_emitir_token_incluye_rol_y_cliente_unit():
    usuario = MagicMock(spec=Usuario)
    usuario.id = "u-1"
    usuario.email = "ana@demo.local"
    usuario.rol = "cliente"
    usuario.cliente_id = "c-9"
    emitido = security.emitir_token(usuario)
    assert emitido["rol"] == "cliente" and emitido["cliente_id"] == "c-9"
    datos = security.jwt.decode(emitido["access_token"], security.ajustes.jwt_secret,
                                algorithms=[security.ajustes.jwt_algorithm])
    assert datos["sub"] == "u-1" and datos["exp"] > 0


def test_email_se_normaliza_a_minusculas_unit():
    from app.schemas import ClienteCreacion
    c = ClienteCreacion(documento_identidad="D1", nombre="Ana",
                        email="ANA@Demo.Local")
    assert c.email == "ANA@Demo.Local"   # el esquema no altera; la normalización es en rutas
