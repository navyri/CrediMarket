"""Cache-aside con Redis para el servicio Productos (§6 del enunciado).

Patrón implementado:
- lectura: clave `productos:v1:{id}` → miss → BD → `SET` con TTL;
- escritura: commit → invalidación (`DEL`) de la clave y del fallback local;
- indisponibilidad: fallback acotado en memoria con TTL corto; la caché nunca
  bloquea una lectura ni oculta la fuente de verdad (§6: la deduplicación y la
  cotización oficial viven en BD, jamás en Redis).
"""
import json
import logging

import redis

from .config import ajustes
from .security import memoria_borrada, memoria_leida, memoria_puesta

logger = logging.getLogger("productos.cache")

_cliente_redis: redis.Redis | None = None
_redis_disponible = True


def clave_producto(producto_id: str) -> str:
    return f"{ajustes.cache_prefijo}:{ajustes.cache_version}:{producto_id}"


def obtener_cliente() -> redis.Redis:
    global _cliente_redis
    if _cliente_redis is None:
        _cliente_redis = redis.Redis.from_url(
            ajustes.redis_url,
            password=ajustes.redis_password,
            socket_connect_timeout=1,
            socket_timeout=1,
            decode_responses=True,
        )
    return _cliente_redis


def _marcar(estado: bool) -> None:
    global _redis_disponible
    if _redis_disponible != estado:
        logger.warning("redis disponible=%s", estado)
    _redis_disponible = estado


def redis_esta_disponible() -> bool:
    try:
        obtener_cliente().ping()
        _marcar(True)
        return True
    except redis.RedisError:
        _marcar(False)
        return False


def leer(producto_id: str) -> dict | None:
    """Devuelve el producto si está en Redis; si no, None (miss)."""
    clave = clave_producto(producto_id)
    try:
        bruto = obtener_cliente().get(clave)
        _marcar(True)
        if bruto is not None:
            return json.loads(bruto)
    except redis.RedisError:
        _marcar(False)
    except (json.JSONDecodeError, TypeError):
        logger.warning("valor corrupto en %s; se trata como miss", clave)
        invalidar(producto_id)
    # Fallback local acotado (solo mientras Redis no responde).
    bruto_local = memoria_leida(clave)
    if bruto_local:
        return json.loads(bruto_local)
    return None


def escribir(producto_id: str, datos: dict) -> None:
    """Puebla la caché tras un miss de BD (TTL configurable, §6)."""
    clave = clave_producto(producto_id)
    bruto = json.dumps(datos, default=str)
    try:
        obtener_cliente().set(clave, bruto, ex=ajustes.cache_ttl_seg)
        _marcar(True)
        memoria_borrada(clave)
    except redis.RedisError:
        _marcar(False)
        memoria_puesta(clave, bruto, ajustes.fallback_ttl_seg)


def invalidar(producto_id: str) -> None:
    """Invalidación tras commit (§6): se llama SIEMPRE después de persistir."""
    clave = clave_producto(producto_id)
    memoria_borrada(clave)
    try:
        obtener_cliente().delete(clave)
        _marcar(True)
    except redis.RedisError:
        _marcar(False)
        logger.warning("no se pudo invalidar %s; el TTL acota la obsolescencia", clave)
