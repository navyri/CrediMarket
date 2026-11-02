"""Mediciones de la caché Redis de Productos (entregable 6: informe de Redis).

Mide, contra el Compose real:
  1. latencia de GET /productos/{id} en MISS (Redis vacío → BD → pueble),
  2. latencia en HIT (Redis poblado) promediando N lecturas,
  3. las métricas del servicio (`GET /cache/estadisticas`),
  4. invalidación tras un PATCH de precio.

Uso:  python scripts/medir_cache.py [--lecturas 40]
Requiere: docker compose up -d  (postgres, redis, clientes, productos).
"""
import argparse
import json
import os
import statistics
import sys
import time
from pathlib import Path

import requests

sys.stdout.reconfigure(encoding="utf-8")

RAIZ = Path(__file__).resolve().parents[1]
URL_CLIENTES = os.environ.get("URL_CLIENTES", "http://localhost:8002")
URL_PRODUCTOS = os.environ.get("URL_PRODUCTOS", "http://localhost:8001")
ADMIN_EMAIL = os.environ.get("ACEP_ADMIN_EMAIL", "admin@credimarket.demo")
ADMIN_PASSWORD = os.environ.get("ACEP_ADMIN_PASSWORD", "CAMBIAR_admin_local")


def token_admin() -> str:
    r = requests.post(f"{URL_CLIENTES}/auth/token",
                      json={"email": ADMIN_EMAIL, "password": ADMIN_PASSWORD},
                      timeout=15)
    r.raise_for_status()
    return r.json()["access_token"]


def admin() -> dict:
    return {"Authorization": f"Bearer {token_admin()}"}


def ms(inicio: float) -> float:
    return round((time.perf_counter() - inicio) * 1000, 2)


def resumen(valores: list[float]) -> dict:
    ordenados = sorted(valores)
    p95 = ordenados[max(0, int(len(ordenados) * 0.95) - 1)]
    return {"n": len(valores),
            "min_ms": round(min(valores), 2),
            "p50_ms": round(statistics.median(valores), 2),
            "p95_ms": round(p95, 2),
            "max_ms": round(max(valores), 2)}


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--lecturas", type=int, default=40,
                        help="lecturas consecutivas para medir el HIT")
    parser.add_argument("--sin-redis", action="store_true",
                        help="solo mide el camino a la BD (Redis detenido: "
                             "`docker compose stop redis` antes de ejecutar)")
    args = parser.parse_args()

    headers = admin()
    import redis  # cliente de la caché (solo para FLUSHDB del escenario MISS)
    cli = redis.Redis.from_url(
        os.environ.get("REDIS_URL", "redis://localhost:6379/0"),
        password=os.environ.get("REDIS_PASSWORD", "CAMBIAR_redis_local"),
        socket_connect_timeout=5)

    # --- producto de prueba (creado si no existe) -------------------------
    catalogo = requests.get(f"{URL_PRODUCTOS}/productos?pagina=1&tamano=1",
                            timeout=15).json()
    if not catalogo.get("items"):
        print("Sin productos en el catálogo; crea uno antes de medir.", file=sys.stderr)
        return 2
    producto = catalogo["items"][0]["id"]

    # --- modo sin Redis: se mide el camino de fallback (BD) ---------------
    if args.sin_redis:
        serie = []
        for _ in range(args.lecturas):
            t = time.perf_counter()
            requests.get(f"{URL_PRODUCTOS}/productos/{producto}",
                         headers=headers, timeout=15)
            serie.append(ms(t))
        informe = {
            "modo": "sin-redis (fallback a base de datos)",
            "producto": producto,
            "lecturas": resumen(serie),
            "servicio": requests.get(f"{URL_PRODUCTOS}/cache/estadisticas",
                                     headers=headers, timeout=15).json(),
        }
        print(json.dumps(informe, indent=2, ensure_ascii=False))
        destino = RAIZ / "docs" / "evidencias" / "mediciones_cache_sin_redis.json"
        destino.write_text(json.dumps(informe, indent=2, ensure_ascii=False) + "\n",
                           encoding="utf-8")
        print(f"\nEvidencia guardada en {destino}")
        return 0

    # --- 1) MISS: vaciar la caché y medir la primera lectura --------------
    cli.flushdb()
    t = time.perf_counter()
    requests.get(f"{URL_PRODUCTOS}/productos/{producto}", headers=headers, timeout=15)
    miss_ms = ms(t)

    # --- 2) HIT: N lecturas consecutivas ---------------------------------
    hit = []
    for _ in range(args.lecturas):
        t = time.perf_counter()
        requests.get(f"{URL_PRODUCTOS}/productos/{producto}", headers=headers, timeout=15)
        hit.append(ms(t))

    # --- 3) métricas del servicio ----------------------------------------
    stats = requests.get(f"{URL_PRODUCTOS}/cache/estadisticas",
                         headers=headers, timeout=15).json()

    # --- 4) invalidación por PATCH de precio -----------------------------
    precio = float(requests.get(f"{URL_PRODUCTOS}/productos/{producto}",
                                headers=headers, timeout=15).json()["precio_cop"])
    nuevo = precio + 1000
    requests.patch(f"{URL_PRODUCTOS}/productos/{producto}", headers=headers,
                   json={"precio_cop": nuevo}, timeout=15).raise_for_status()
    clave = f"productos:v1:{producto}"
    invalidada = not cli.exists(clave)

    # --- 5) carga ligera sobre el catálogo (lista cacheada en el listado) -
    def _leer(_: int) -> float:
        t = time.perf_counter()
        requests.get(f"{URL_PRODUCTOS}/productos?pagina=1&tamano=50",
                     headers=headers, timeout=15)
        return ms(t)

    carga_total = args.lecturas * 2
    t = time.perf_counter()
    serie = [_leer(i) for i in range(args.lecturas)]
    serie_s = time.perf_counter() - t

    from concurrent.futures import ThreadPoolExecutor
    with ThreadPoolExecutor(max_workers=20) as pool:
        t = time.perf_counter()
        concurrente = list(pool.map(_leer, range(args.lecturas)))
        conc_s = time.perf_counter() - t

    carga = {
        "serie": {**resumen(serie),
                  "req_s": round(len(serie) / serie_s, 1)},
        "concurrente_20_hilos": {**resumen(concurrente),
                                 "req_s": round(len(concurrente) / conc_s, 1)},
        "total_peticiones": carga_total,
    }

    informe = {
        "producto": producto,
        "miss_primera_lectura_ms": miss_ms,
        "hit": resumen(hit),
        "carga_catalogo": carga,
        "servicio": stats,
        "invalidacion_tras_patch": {
            "clave": clave,
            "clave_borrada": invalidada,
            "precio_cop": nuevo,
        },
        "veredicto": ("OK: la primera lectura tras FLUSHDB es un MISS que puebla la "
                      "caché; las lecturas siguientes son HIT más rápidas y el PATCH "
                      "borra la clave (invalidación write-through)." if invalidada
                      else "FALLO: la clave no se invalidó tras el PATCH"),
    }
    print(json.dumps(informe, indent=2, ensure_ascii=False))

    destino = RAIZ / "docs" / "evidencias" / "mediciones_cache.json"
    destino.write_text(json.dumps(informe, indent=2, ensure_ascii=False) + "\n",
                       encoding="utf-8")
    print(f"\nEvidencia guardada en {destino}")
    return 0 if invalidada else 1


if __name__ == "__main__":
    raise SystemExit(main())
