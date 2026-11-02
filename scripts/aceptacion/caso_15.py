"""Caso §12.15 — Pendiente y actualización asíncrona.

Evidencia esperada: 202 inmediato en PENDIENTE_INVENTARIO y polling que
observa la transición asíncrona hasta APROBADA con la reserva confirmada.
"""
import sys
import time
from pathlib import Path

import requests

sys.path.insert(0, str(Path(__file__).resolve().parent))
from _comun import (URL_INVENTARIO, URL_PRESTAMOS, admin_token, auth,
                    crear_producto, evidencia, existencia, registrar_cliente,
                    solicitar, salir)

CASO = 15
REQUISITO = "§12.15 Pendiente y actualización asíncrona"
ESPERADO = "202 + polling hasta APROBADA (la confirmación llega por mensaje)."


def main() -> dict:
    cliente = registrar_cliente(bueno=True)
    producto = crear_producto(precio=175_000, stock=3)
    antes = existencia(producto)

    # 1) Respuesta INMEDIATA: 202 con el préstamo aún sin resolver.
    inicio = time.time()
    r = solicitar(cliente["cliente_id"], producto, token=cliente["token"])
    latencia_ms = (time.time() - inicio) * 1000
    assert r.status_code == 202, f"{r.status_code}: {r.text}"
    cuerpo = r.json()
    assert cuerpo["estado"] == "PENDIENTE_INVENTARIO", cuerpo["estado"]
    assert latencia_ms < 5000, f"el 202 tardó {latencia_ms:.0f} ms"
    prestamo_id = cuerpo["prestamo_id"]

    # 2) Polling con TRAZA (lo que haría la interfaz cada 2.5 s).
    token_admin = admin_token()
    traza: list[dict] = []
    final = None
    limite = time.time() + 45
    while time.time() < limite:
        g = requests.get(f"{URL_PRESTAMOS}/prestamos/{prestamo_id}",
                         headers=auth(token_admin), timeout=15)
        assert g.status_code == 200, g.text
        p = g.json()
        if not traza or traza[-1]["estado"] != p["estado"]:
            traza.append({"t_ms": int((time.time() - inicio) * 1000),
                          "estado": p["estado"]})
        if p["estado"] in {"APROBADA", "RECHAZADA", "CANCELADA_SIN_STOCK"}:
            final = p
            break
        time.sleep(0.5)
    assert final is not None, f"sin estado final; traza={traza}"
    assert final["estado"] == "APROBADA", final["estado"]
    assert len(traza) >= 2 and traza[0]["estado"] == "PENDIENTE_INVENTARIO", traza

    # 3) La confirmación es real: reserva en Inventario y stock reservado.
    reserva = requests.get(f"{URL_INVENTARIO}/reservas/{final['reserva_id']}",
                           headers=auth(token_admin), timeout=15).json()
    assert reserva["estado"] == "RESERVADA", reserva["estado"]
    stock = existencia(producto)
    assert stock["reservada"] == antes["reservada"] + 1, stock
    assert stock["disponible"] == antes["disponible"] - 1, stock

    return evidencia(
        CASO, REQUISITO, ESPERADO,
        f"POST → 202 en {latencia_ms:.0f} ms (PENDIENTE_INVENTARIO) y polling "
        f"{' → '.join(f'{x["estado"]}@{x["t_ms"]}ms' for x in traza)}; reserva "
        f"{final['reserva_id'][:8]}… RESERVADA y stock reservada "
        f"{antes['reservada']} → {stock['reservada']}",
        ok=True,
        detalle={"prestamo_id": prestamo_id, "reserva_id": final["reserva_id"],
                 "latencia_202_ms": round(latencia_ms, 1), "traza": traza,
                 "stock_antes": antes, "stock_despues": stock})


if __name__ == "__main__":
    salir(main())
