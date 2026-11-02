"""Caso §12.9 — Precio modificado.

Evidencia esperada: invalidación de caché y monto del préstamo basado en la
cotización vigente (el cliente nunca envía precio, §4).
"""
import sys
from pathlib import Path

import requests

sys.path.insert(0, str(Path(__file__).resolve().parent))
from _comun import (URL_PRESTAMOS, URL_PRODUCTOS, admin_token, auth,
                    crear_producto, esperar_estado, evidencia, redis_cli,
                    registrar_cliente, solicitar, salir)

CASO = 9
REQUISITO = "§12.9 Precio modificado"
ESPERADO = "Invalidación de caché y monto del préstamo basado en la cotización vigente."


def main() -> dict:
    token_admin = admin_token()
    producto = crear_producto(precio=175_000, stock=3)
    r = redis_cli()

    # 1) Poblar la caché con el precio original.
    g1 = requests.get(f"{URL_PRODUCTOS}/productos/{producto}",
                      headers=auth(token_admin), timeout=15).json()
    assert float(g1["precio_cop"]) == 175000
    clave = f"productos:v1:{producto}"
    assert r.exists(clave), "la caché no se pobló"

    # 2) Actualizar el precio (versión nueva) → invalidación obligatoria.
    p = requests.patch(f"{URL_PRODUCTOS}/productos/{producto}",
                       headers=auth(token_admin), json={"precio_cop": 250_000},
                       timeout=15)
    assert p.status_code == 200, p.text
    assert p.json()["version"] == g1["version"] + 1, "la versión no avanzó"
    cache_invalidada = not r.exists(clave)

    # 3) La siguiente lectura devuelve el precio vigente.
    g2 = requests.get(f"{URL_PRODUCTOS}/productos/{producto}",
                      headers=auth(token_admin), timeout=15).json()
    assert float(g2["precio_cop"]) == 250000, g2["precio_cop"]

    # 4) Un préstamo posterior usa la cotización VIGENTE (250.000), no la vieja.
    cliente = registrar_cliente(bueno=True)
    rr = solicitar(cliente["cliente_id"], producto, cantidad=1,
                   token=cliente["token"])
    assert rr.status_code == 202, rr.text
    prestamo_id = rr.json()["prestamo_id"]
    assert float(rr.json()["precio_unitario_cop"]) == 250000, \
        f"monto con precio viejo: {rr.json()['precio_unitario_cop']}"
    assert float(rr.json()["monto_total_cop"]) == 250000, rr.json()["monto_total_cop"]
    esperar_estado(prestamo_id, estados={"APROBADA", "CANCELADA_SIN_STOCK",
                                         "RECHAZADA"})

    return evidencia(
        CASO, REQUISITO, ESPERADO,
        f"precio 175.000 (v{g1['version']}) → PATCH 250.000 (v{p.json()['version']}) → "
        f"caché invalidada={cache_invalidada} → GET devuelve 250.000 → préstamo "
        f"{prestamo_id[:8]}… cotizado a 250.000 (monto_total=250000)",
        ok=True,
        detalle={"producto_id": producto, "precio_viejo": 175000,
                 "precio_nuevo": 250000, "version_antes": g1["version"],
                 "version_despues": p.json()["version"],
                 "cache_invalidada": cache_invalidada,
                 "precio_unitario_prestamo": rr.json()["precio_unitario_cop"],
                 "monto_total_cop": rr.json()["monto_total_cop"]})


if __name__ == "__main__":
    salir(main())
