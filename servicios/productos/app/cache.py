"""Cache-aside con Redis para el servicio Productos (§6 del enunciado).

Patrón implementado:
- lectura: clave `productos:v1:{id}` → miss → BD → `SET` con TTL;
- escritura: commit → invalidación (`DEL`) de la clave y del fallback local;
- indisponibilidad: fallback acotado en memoria con TTL corto; la caché nunca
  bloquea una lectura ni oculta la fuente de verdad (§6: la deduplicación y la
  cotización oficial viven en BD, jamás en Redis).

Cada operación deja su métrica en `estadisticas` (P2-TEST-019): hit-rate,
fallback y latencia p50/p95 del GET sobre Redis.
"""
import json
import logging

import redis

from . import estadisticas
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
    """Devuelve el producto si está en Redis; si no, None (miss).

    El fallback local SOLO se usa cuando Redis no responde (indisponibilidad,
    P2-TEST-008). Un miss legítimo devuelve None para que la ruta lea la BD y
    repueble la caché: servir el fallback en un miss dejaría datos obsoletos
    sin repoblar Redis.
    """
    clave = clave_producto(producto_id)
    inicio = estadisticas.tiempo()
    redis_respondio = False
    bruto = None
    latencia = None
    try:
        bruto = obtener_cliente().get(clave)
        latencia = (estadisticas.tiempo() - inicio) * 1000
        redis_respondio = True
        _marcar(True)
    except redis.RedisError:
        _marcar(False)
        estadisticas.registrar_error_redis()

    if redis_respondio:
        if bruto is not None:
            try:
                datos = json.loads(bruto)
            except (json.JSONDecodeError, TypeError):
                logger.warning("valor corrupto en %s; se trata como miss", clave)
                invalidar(producto_id)
                datos = None
            if datos is not None:
                estadisticas.registrar_lectura("acierto", latencia)
                return datos
        # Miss (o valor corrupto ya invalidado): la ruta lee BD y repuebla.
        estadisticas.registrar_lectura("fallo", latencia)
        return None

    # Redis no respondió: fallback local acotado (P2-TEST-008).
    bruto_local = memoria_leida(clave)
    if bruto_local:
        estadisticas.registrar_lectura("fallback")
        return json.loads(bruto_local)
    estadisticas.registrar_lectura("fallo")
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
        estadisticas.registrar_error_redis()
        memoria_puesta(clave, bruto, ajustes.fallback_ttl_seg)


def invalidar(producto_id: str) -> None:
    """Invalidación tras commit (§6): se llama SIEMPRE después de persistir."""
    clave = clave_producto(producto_id)
    memoria_borrada(clave)
    try:
        obtener_cliente().delete(clave)
        _marcar(True)
        estadisticas.registrar_invalidacion()
    except redis.RedisError:
        _marcar(False)
        estadisticas.registrar_error_redis()
        logger.warning("no se pudo invalidar %s; el TTL acota la obsolescencia", clave)
