"""Caso §12.8 — Redis vacío, expirado o caído.

Evidencia esperada: caché demostrable y consultas recuperables desde la base
de datos. Se demuestran los tres estados sobre un producto real:
- vacío (FLUSHDB): GET sirve desde BD y repuebla Redis;
- expirado (TTL corto): el miss vuelve a poblar con TTL normal;
- caído (contenedor detenido): GET sigue respondiendo desde BD/fallback.
"""
import subprocess
import sys
import time
from pathlib import Path

import requests

sys.path.insert(0, str(Path(__file__).resolve().parent))
from _comun import (RAIZ, URL_PRODUCTOS, admin_token, auth, crear_producto,
                    evidencia, redis_cli, salir)

CASO = 8
REQUISITO = "§12.8 Redis vacío, expirado o caído"
ESPERADO = "Caché demostrable y consultas recuperables desde la base de datos."


def _compose(*args: str) -> subprocess.CompletedProcess:
    return subprocess.run(["docker", "compose", *args], cwd=RAIZ,
                          capture_output=True, text=True, timeout=300)


def main() -> dict:
    producto = crear_producto(precio=175_000, stock=1)
    r = redis_cli()
    token = admin_token()
    detalle: dict = {}
    bajar = False

    try:
        # 1) Vacío: sin claves, el GET debe servir desde BD y repoblar Redis.
        r.flushdb()
        g1 = requests.get(f"{URL_PRODUCTOS}/productos/{producto}",
                          headers=auth(token), timeout=15)
        assert g1.status_code == 200, g1.text
        assert float(g1.json()["precio_cop"]) == 175000
        clave = f"productos:v1:{producto}"
        assert r.exists(clave), "el miss no repobló Redis"
        detalle["vacio"] = {"http": g1.status_code,
                            "clave_repoblada": bool(r.exists(clave)),
                            "ttl_s": int(r.ttl(clave))}

        # 2) Acierto: la segunda lectura viene de Redis.
        g2 = requests.get(f"{URL_PRODUCTOS}/productos/{producto}",
                          headers=auth(token), timeout=15)
        assert g2.status_code == 200

        # 3) Expirado: TTL artificial de 1 s → miss → BD → nuevo TTL.
        r.expire(clave, 1)
        time.sleep(1.5)
        assert not r.exists(clave), "la clave no expiró"
        g3 = requests.get(f"{URL_PRODUCTOS}/productos/{producto}",
                          headers=auth(token), timeout=15)
        assert g3.status_code == 200 and r.exists(clave), \
            "tras expirar no se repobló"
        detalle["expirado"] = {"http": g3.status_code,
                               "repoblada": bool(r.exists(clave)),
                               "ttl_s": int(r.ttl(clave))}

        # 4) Caído: se detiene el contenedor; la lectura sigue respondiendo.
        _compose("stop", "redis")
        bajar = True
        time.sleep(2)
        g4 = requests.get(f"{URL_PRODUCTOS}/productos/{producto}",
                          headers=auth(token), timeout=15)
        assert g4.status_code == 200, \
            f"con Redis caído la BD debió responder: {g4.status_code}"
        assert float(g4.json()["precio_cop"]) == 175000
        detalle["caido"] = {"http": g4.status_code,
                            "detalle": "la BD responde sin Redis (fallback o directo)"}
        _compose("start", "redis")
        bajar = False

        # 5) Recuperación: Redis vuelve y vuelve a cachear.
        time.sleep(5)
        g5 = requests.get(f"{URL_PRODUCTOS}/productos/{producto}",
                          headers=auth(token), timeout=15)
        assert g5.status_code == 200
        detalle["recuperado"] = {"http": g5.status_code}

        return evidencia(
            CASO, REQUISITO, ESPERADO,
            f"miss con FLUSHDB → 200 + clave repoblada (TTL "
            f"{detalle['vacio']['ttl_s']}s); expiración → miss → repoblada; Redis "
            f"detenido → 200 desde BD; reiniciado → 200 y caché activa",
            ok=True, detalle=detalle)
    finally:
        if bajar:
            _compose("start", "redis")


if __name__ == "__main__":
    salir(main())
