"""Pruebas UNITARIAS del servicio Productos.

Todos los dobles en este archivo son MOCKS declarados (redis y JWT simulados con
`unittest.mock`): no sustituyen las pruebas de integración, que corren contra
PostgreSQL y Redis reales de docker-compose (ver tests/integracion/).
"""
import sys
from pathlib import Path
from unittest.mock import MagicMock, patch

import jwt
import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app import cache, security                      # noqa: E402
from app.config import ajustes                      # noqa: E402
from app.schemas import ProductoCreacion            # noqa: E402


# ---------------------------------------------------------------- clave y TTL
def test_clave_cache_sigue_el_prefijo_acordado_unit():
    """Contrato de clave `productos:v1:{id}` (§6, P2-TEST-009)."""
    assert cache.clave_producto("abc-123") == "productos:v1:abc-123"


def test_lectura_con_mock_de_redis_miss_unit():
    """Un miss (GET → None) devuelve None para que la ruta lea la BD."""
    cliente = MagicMock()
    cliente.get.return_value = None
    with patch.object(cache, "obtener_cliente", return_value=cliente):
        assert cache.leer("prod-1") is None
    cliente.get.assert_called_once_with("productos:v1:prod-1")


def test_lectura_con_mock_de_redis_hit_unit():
    cliente = MagicMock()
    cliente.get.return_value = '{"id": "prod-1", "precio_cop": "1500.00", "version": 3}'
    with patch.object(cache, "obtener_cliente", return_value=cliente):
        datos = cache.leer("prod-1")
    assert datos["precio_cop"] == "1500.00" and datos["version"] == 3


def test_escritura_usa_ttl_configurado_unit():
    """El pueble tras un miss usa SET con EX = cache_ttl_seg (§6)."""
    cliente = MagicMock()
    with patch.object(cache, "obtener_cliente", return_value=cliente):
        cache.escribir("prod-2", {"id": "prod-2", "version": 1})
    cliente.set.assert_called_once()
    args, kwargs = cliente.set.call_args
    assert args[0] == "productos:v1:prod-2"
    assert kwargs.get("ex") == ajustes.cache_ttl_seg


def test_invalidacion_borra_la_clave_unit():
    """Invalidación tras commit: DEL sobre la clave exacta."""
    cliente = MagicMock()
    with patch.object(cache, "obtener_cliente", return_value=cliente):
        cache.invalidar("prod-3")
    cliente.delete.assert_called_once_with("productos:v1:prod-3")


def test_invalidacion_sigue_existiendo_si_redis_cae_unit():
    """Redis caído no interrumpe el flujo: la invalidación queda registrada en el fallback."""
    cliente = MagicMock()
    cliente.delete.side_effect = cache.redis.RedisError("conexion rechazada")
    cliente.ping.side_effect = cache.redis.RedisError("conexion rechazada")
    with patch.object(cache, "obtener_cliente", return_value=cliente):
        cache.invalidar("prod-4")            # no debe lanzar excepción
        assert cache.redis_esta_disponible() is False


# ------------------------------------------------------- fallback con Redis caído
def test_fallback_local_lee_y_escribe_con_redis_caido_unit():
    """P2-TEST-008: con Redis fuera, la lectura sigue funcionando (fallback acotado)."""
    security.memoria_vacia()
    cliente = MagicMock()
    cliente.get.side_effect = cache.redis.RedisError("redis no disponible")
    cliente.set.side_effect = cache.redis.RedisError("redis no disponible")
    with patch.object(cache, "obtener_cliente", return_value=cliente):
        assert cache.leer("prod-5") is None            # 1.ª lectura: miss
        cache.escribir("prod-5", {"id": "prod-5", "version": 2})
        datos = cache.leer("prod-5")                   # 2.ª lectura: fallback local
    assert datos is not None and datos["version"] == 2
    security.memoria_vacia()


def test_fallback_local_respeta_el_ttl_unit():
    security.memoria_vacia()
    security.memoria_puesta("k", '{"v": 1}', ttl=0)
    assert security.memoria_leida("k") is None            # expira de inmediato
    security.memoria_vacia()


def test_valores_corruptos_se_tratan_como_miss_unit():
    """Un JSON inválido en Redis invalida la clave en lugar de romper la lectura."""
    cliente = MagicMock()
    cliente.get.return_value = "{esto no es json"
    with patch.object(cache, "obtener_cliente", return_value=cliente):
        assert cache.leer("prod-6") is None
    cliente.delete.assert_called_once_with("productos:v1:prod-6")


# --------------------------------------------------------- JWT (mock de secretos)
def _token(rol: str, exp_en: int = 300) -> str:
    import time
    return jwt.encode({"sub": "u1", "cliente_id": "c1", "rol": rol,
                       "exp": int(time.time()) + exp_en},
                      ajustes.jwt_secret, algorithm=ajustes.jwt_algorithm)


def test_token_valido_con_rol_administrador_unit():
    datos = security.decodificar_token(_token("administrador"))
    assert datos["rol"] == "administrador" and datos["cliente_id"] == "c1"


def test_token_expirado_se_rechaza_unit():
    import time
    token = jwt.encode({"sub": "u1", "rol": "administrador", "exp": int(time.time()) - 1},
                       ajustes.jwt_secret, algorithm=ajustes.jwt_algorithm)
    with pytest.raises(jwt.ExpiredSignatureError):
        security.decodificar_token(token)


def test_token_con_otro_secreto_se_rechaza_unit():
    token = jwt.encode({"sub": "u1", "rol": "administrador", "exp": 9999999999},
                       "otro-secreto-distinto", algorithm="HS256")
    with pytest.raises(jwt.InvalidTokenError):
        security.decodificar_token(token)


# ------------------------------------------------------------- esquemas/validación
def test_producto_creacion_rechaza_precio_no_positivo_unit():
    with pytest.raises(ValueError):
        ProductoCreacion(sku="S1", nombre="Teclado", categoria="perifericos",
                         precio_cop=0)


def test_producto_creacion_acepta_precio_positivo_unit():
    p = ProductoCreacion(sku="S1", nombre="Teclado", categoria="perifericos",
                         precio_cop="150000")
    assert p.precio_cop == 150000


def test_respuesta_de_error_sigue_rfc9457_unit():
    """El helper `problema` emite problem+json con los campos obligatorios."""
    respuesta = security.problema(404, "Recurso no encontrado", "no existe",
                                  "/productos/x")
    cuerpo = respuesta.body.decode()
    assert respuesta.status_code == 404
    assert '"title":"Recurso no encontrado"' in cuerpo
    assert '"status":404' in cuerpo and '"instance":"/productos/x"' in cuerpo
