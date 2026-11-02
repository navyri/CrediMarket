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
import time

import redis

from . import estadisticas
from .config import ajustes
from .security import memoria_borrada, memoria_leida, memoria_puesta

logger = logging.getLogger("productos.cache")

_cliente_redis: redis.Redis | None = None
_redis_disponible = True

# Cortacircuitos (§6: "si Redis falla, seguir respondiendo ... con un tiempo de
# espera acotado"). Sin esta ventana, cada petición pagaría el timeout de
# conexión a un Redis caído (medido: p50 ≈ 4,8 s por lectura). Tras el primer
# fallo se salta Redis durante `cache_fail_fast_seg` y se reintenta al vencer.
_ventana_fallo_hasta: float = 0.0


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


def _redis_en_fallo() -> bool:
    """True mientras dura la ventana de fail-fast abierta tras un fallo."""
    return time.monotonic() < _ventana_fallo_hasta


def _anotar_fallo() -> None:
    """Abre el cortacircuitos: durante `cache_fail_fast_seg` no se toca Redis."""
    global _ventana_fallo_hasta
    _marcar(False)
    _ventana_fallo_hasta = time.monotonic() + ajustes.cache_fail_fast_seg


def _anotar_ok() -> None:
    """Cierra el cortacircuitos: Redis volvió a responder."""
    global _ventana_fallo_hasta
    _marcar(True)
    _ventana_fallo_hasta = 0.0


def reiniciar_cortacircuitos() -> None:
    """Cierra la ventana (pruebas y recuperación forzada)."""
    global _ventana_fallo_hasta, _redis_disponible
    _ventana_fallo_hasta = 0.0
    _redis_disponible = True


def redis_esta_disponible() -> bool:
    if _redis_en_fallo():                     # ventana abierta: respuesta inmediata
        return False
    try:
        obtener_cliente().ping()
        _anotar_ok()
        return True
    except redis.RedisError:
        _anotar_fallo()
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
    if _redis_en_fallo():
        # Cortacircuitos abierto: se omite el intento para que la espera sea
        # acotada (§6) en lugar de pagar el timeout de conexión en cada petición.
        estadisticas.registrar_error_redis()
    else:
        try:
            bruto = obtener_cliente().get(clave)
            latencia = (estadisticas.tiempo() - inicio) * 1000
            redis_respondio = True
            _anotar_ok()
        except redis.RedisError:
            estadisticas.registrar_error_redis()
            _anotar_fallo()

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
    if _redis_en_fallo():
        estadisticas.registrar_error_redis()     # intento omitido (Redis caído)
        memoria_puesta(clave, bruto, ajustes.fallback_ttl_seg)
        return
    try:
        obtener_cliente().set(clave, bruto, ex=ajustes.cache_ttl_seg)
        _anotar_ok()
        memoria_borrada(clave)
    except redis.RedisError:
        estadisticas.registrar_error_redis()
        _anotar_fallo()
        memoria_puesta(clave, bruto, ajustes.fallback_ttl_seg)


def invalidar(producto_id: str) -> None:
    """Invalidación tras commit (§6): se llama SIEMPRE después de persistir."""
    clave = clave_producto(producto_id)
    memoria_borrada(clave)
    if _redis_en_fallo():
        estadisticas.registrar_error_redis()     # intento omitido (Redis caído)
        logger.warning("ventana de fallo abierta; %s queda acotada por el TTL",
                       clave)
        return
    try:
        obtener_cliente().delete(clave)
        _anotar_ok()
        estadisticas.registrar_invalidacion()
    except redis.RedisError:
        estadisticas.registrar_error_redis()
        _anotar_fallo()
        logger.warning("no se pudo invalidar %s; el TTL acota la obsolescencia", clave)
