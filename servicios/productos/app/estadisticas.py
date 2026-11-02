"""Métricas de la caché Redis para el servicio Productos (§6, P2-TEST-019).

Contadores en memoria (propios del servicio) para demostrar el comportamiento
cache-aside en producción:

- `hit_rate`: aciertos sobre lecturas totales (Redis o fallback);
- `fallback`: lecturas servidas por la memoria local mientras Redis no
  responde (la caché nunca bloquea una lectura, §6);
- `latencia_redis_ms`: p50/p95 de las operaciones GET sobre Redis (muestra
  acotada, no crece sin límite);
- `invalidaciones`: DEL tras commit (fuente de verdad siempre en BD, §6).

Las métricas son de observación: si el proceso se reinicia vuelven a cero; el
histórico durable es la propia BD (§6).
"""
import threading
import time
from collections import deque

_MAX_MUESTRAS = 2000

_bloqueo = threading.Lock()
_aciertos = 0
_fallos = 0
_fallback = 0
_invalidaciones = 0
_errores_redis = 0
_latencias: deque[float] = deque(maxlen=_MAX_MUESTRAS)


def registrar_lectura(estado: str, latencia_ms: float | None = None) -> None:
    """`estado`: "acierto" (Redis), "fallback" (memoria local) o "fallo"."""
    global _aciertos, _fallos, _fallback
    with _bloqueo:
        if estado == "acierto":
            _aciertos += 1
        elif estado == "fallback":
            _fallback += 1
        else:
            _fallos += 1
        if latencia_ms is not None:
            _latencias.append(latencia_ms)


def registrar_invalidacion() -> None:
    global _invalidaciones
    with _bloqueo:
        _invalidaciones += 1


def registrar_error_redis() -> None:
    global _errores_redis
    with _bloqueo:
        _errores_redis += 1


def reiniciar() -> None:
    """Reinicia los contadores (uso en pruebas)."""
    global _aciertos, _fallos, _fallback, _invalidaciones, _errores_redis
    with _bloqueo:
        _aciertos = _fallos = _fallback = _invalidaciones = _errores_redis = 0
        _latencias.clear()


def _percentil(ordenados: list[float], p: float) -> float | None:
    if not ordenados:
        return None
    if len(ordenados) == 1:
        return ordenados[0]
    k = (len(ordenados) - 1) * p
    inferior = int(k)
    superior = min(inferior + 1, len(ordenados) - 1)
    return (ordenados[inferior]
            + (ordenados[superior] - ordenados[inferior]) * (k - inferior))


def resumen() -> dict:
    with _bloqueo:
        total = _aciertos + _fallos + _fallback
        latencias = sorted(_latencias)
        return {
            "redis_disponible": None,   # lo completa el caller (evita ciclo)
            "lecturas": {
                "total": total,
                "aciertos": _aciertos,
                "fallos": _fallos,
                "fallback": _fallback,
                "hit_rate": round(_aciertos / total, 4) if total else None,
                "tasa_fallback": round(_fallback / total, 4) if total else None,
            },
            "latencia_redis_ms": {
                "p50": round(_percentil(latencias, 0.50), 3)
                if latencias else None,
                "p95": round(_percentil(latencias, 0.95), 3)
                if latencias else None,
                "muestra": len(latencias),
            },
            "invalidaciones": _invalidaciones,
            "errores_redis": _errores_redis,
        }


def tiempo() -> float:
    return time.perf_counter()
