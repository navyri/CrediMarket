"""Pruebas de INTEGRACIÓN del servicio Productos contra los contenedores reales.

Requiere `docker compose up -d` (PostgreSQL 5434 + Redis 6379 con las credenciales
de .env). Aquí NO hay mocks: se ejercitan la BD, la caché Redis y el JWT reales.
"""
import os
import sys
import time
from decimal import Decimal
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

# Entorno real de Compose, ANTES de importar la app (pydantic-settings lee en import).
os.environ["DATABASE_URL"] = os.environ.get(
    "DATABASE_URL",
    "postgresql+psycopg://svc_productos:CAMBIAR_prod_local@localhost:5434/credimarket",
)
os.environ["REDIS_URL"] = os.environ.get("REDIS_URL", "redis://localhost:6379/0")
os.environ["REDIS_PASSWORD"] = os.environ.get("REDIS_PASSWORD", "CAMBIAR_redis_local")
os.environ["JWT_SECRET"] = os.environ.get("JWT_SECRET", "CAMBIAR_jwt_local_largo_32+")

import jwt                                        # noqa: E402
import pytest                                      # noqa: E402
import redis                                       # noqa: E402
from fastapi.testclient import TestClient          # noqa: E402

from app.config import ajustes                     # noqa: E402
from app.main import app                           # noqa: E402

SKU = f"TEST-{int(time.time())}"


def _token(rol: str) -> str:
    return jwt.encode({"sub": "u-test", "cliente_id": "c-test", "rol": rol,
                       "exp": int(time.time()) + 600},
                      ajustes.jwt_secret, algorithm=ajustes.jwt_algorithm)


def _r():
    return TestClient(app)


def _redis():
    return redis.Redis.from_url(ajustes.redis_url, password=ajustes.redis_password,
                                decode_responses=True)


@pytest.fixture(autouse=True)
def _cortacircuitos_reiniciado():
    """Cada prueba empieza con el cortacircuitos de Redis cerrado (§6)."""
    from app import cache
    cache.reiniciar_cortacircuitos()
    yield
    cache.reiniciar_cortacircuitos()


def test_salud_y_lectura_listo():
    with _r() as cliente:
        assert cliente.get("/health").json()["estado"] == "ok"
        listo = cliente.get("/ready")
        assert listo.status_code == 200
        assert listo.json()["bd"] is True and listo.json()["redis"] is True


def test_ciclo_completo_cache_aside():
    """CRUD + miss → BD → pueble → hit → invalidación tras commit (§6, P2-TEST-009)."""
    with _r() as cliente:
        # creación (rol administrador)
        creado = cliente.post(
            "/productos",
            json={"sku": SKU, "nombre": "Teclado mecanico", "categoria": "perifericos",
                  "precio_cop": 150000},
            headers={"Authorization": f"Bearer {_token('administrador')}"},
        )
        assert creado.status_code == 201, creado.text
        pid = creado.json()["id"]
        assert creado.json()["version"] == 1

        # 401 sin token en un endpoint protegido
        assert cliente.post("/productos", json={"sku": "x", "nombre": "x",
                                                "categoria": "x",
                                                "precio_cop": 1}).status_code == 401
        # 403 con rol cliente
        assert cliente.post(
            "/productos",
            json={"sku": "x", "nombre": "x", "categoria": "x", "precio_cop": 1},
            headers={"Authorization": f"Bearer {_token('cliente')}"},
        ).status_code == 403

        # miss → BD → pueble Redis
        _redis().delete(f"productos:v1:{pid}")
        lectura = cliente.get(f"/productos/{pid}")
        assert lectura.status_code == 200
        assert Decimal(lectura.json()["precio_cop"]) == Decimal("150000")
        assert _redis().get(f"productos:v1:{pid}") is not None       # pueble real

        # hit → viene de Redis (el TTL está activo)
        assert _redis().ttl(f"productos:v1:{pid}") > 0

        # actualización: version++ e invalidación tras commit
        actualizado = cliente.patch(
            f"/productos/{pid}",
            json={"precio_cop": 175000},
            headers={"Authorization": f"Bearer {_token('administrador')}"},
        )
        assert actualizado.status_code == 200
        assert actualizado.json()["version"] == 2
        assert _redis().get(f"productos:v1:{pid}") is None           # invalidado

        # la nueva lectura ya refleja el precio modificado
        nueva = Decimal(cliente.get(f"/productos/{pid}").json()["precio_cop"])
        assert nueva == Decimal("175000")

        # cotización interna (fuente de verdad, lee BD)
        cot = cliente.get(
            f"/productos/{pid}/cotizacion",
            headers={"Authorization": f"Bearer {_token('servicio')}"},
        )
        assert cot.status_code == 200
        assert Decimal(cot.json()["precio_cop"]) == Decimal("175000")
        assert cot.json()["version"] == 2

        # un cliente NO puede consultar la cotización interna (§9)
        assert cliente.get(
            f"/productos/{pid}/cotizacion",
            headers={"Authorization": f"Bearer {_token('cliente')}"},
        ).status_code == 403

        # validación de entrada → 400 con problem+json y detalle de campos
        invalido = cliente.post(
            "/productos",
            json={"sku": SKU + "-bad", "nombre": "x", "categoria": "x",
                  "precio_cop": -5},
            headers={"Authorization": f"Bearer {_token('administrador')}"},
        )
        assert invalido.status_code == 400, invalido.text
        assert invalido.headers["content-type"].startswith("application/problem+json")
        assert invalido.json()["errors"], "debe detallar el campo inválido"

        # listado público y 404 con problem+json
        assert cliente.get("/productos").status_code == 200
        no_existe = cliente.get("/productos/no-existe")
        assert no_existe.status_code == 404
        assert no_existe.headers["content-type"].startswith("application/problem+json")


def test_redis_caido_no_toma_el_servicio():
    """P2-TEST-008: con la caché apagada la lectura sigue respondiendo 200 (fallback)."""
    from unittest.mock import patch

    with _r() as cliente:
        pid = cliente.get("/productos", params={"tamano": 1}).json()["items"][0]["id"]
        from app import cache
        roto = redis.Redis.from_url("redis://localhost:6399/0", socket_connect_timeout=1)
        with patch.object(cache, "obtener_cliente", return_value=roto):
            respuesta = cliente.get(f"/productos/{pid}")
        assert respuesta.status_code == 200


def test_estadisticas_de_cache_reportan_hit_rate_y_latencias():
    """P2-TEST-019: p50/p95, hit-rate y fallback medidos sobre Redis real."""
    with _r() as cliente:
        # Un mismo producto: 1.ª lectura (miss → pueble) y luego hits reales.
        pid = cliente.get("/productos", params={"tamano": 1}).json()["items"][0]["id"]
        cliente.get(f"/productos/{pid}")          # miss → BD → SET
        cliente.get(f"/productos/{pid}")          # hit
        cliente.get(f"/productos/{pid}")          # hit

        # Solo administrador ve las métricas (§10).
        sin_rol = cliente.get("/cache/estadisticas")
        assert sin_rol.status_code in (401, 403)
        cliente_rol = cliente.get(
            "/cache/estadisticas",
            headers={"Authorization": f"Bearer {_token('cliente')}"})
        assert cliente_rol.status_code == 403

        resumen = cliente.get(
            "/cache/estadisticas",
            headers={"Authorization": f"Bearer {_token('administrador')}"}).json()
        assert resumen["redis_disponible"] is True
        assert resumen["lecturas"]["aciertos"] >= 2        # los hits de arriba
        assert resumen["lecturas"]["hit_rate"] > 0
        assert resumen["latencia_redis_ms"]["p50"] is not None
        assert resumen["latencia_redis_ms"]["p95"] >= resumen["latencia_redis_ms"]["p50"]
        assert resumen["invalidaciones"] >= 0
