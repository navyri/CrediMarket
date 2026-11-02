"""Caso §12.5 — Misma petición y mismo evento repetidos.

Evidencia esperada: un préstamo y un único efecto sobre el inventario.
- misma Idempotency-Key + mismo cuerpo → la MISMA respuesta (mismo préstamo);
- misma clave con cuerpo distinto → 409;
- evento (entrega) repetido → un solo descuento de stock.
"""
import sys
import uuid
from pathlib import Path

import requests

sys.path.insert(0, str(Path(__file__).resolve().parent))
from _comun import (URL_INVENTARIO, URL_PRESTAMOS, admin_token, auth,
                    crear_producto, esperar_estado, evidencia, existencia,
                    registrar_cliente, solicitar, salir)

CASO = 5
REQUISITO = "§12.5 Misma petición y mismo evento repetidos"
ESPERADO = "Un préstamo y un único efecto sobre el inventario."


def main() -> dict:
    cliente = registrar_cliente(bueno=True)
    producto = crear_producto(precio=175_000, stock=4)
    antes = existencia(producto)
    clave = str(uuid.uuid4())

    # 1) Misma petición dos veces (misma clave + mismo cuerpo).
    r1 = solicitar(cliente["cliente_id"], producto, clave=clave, token=cliente["token"])
    r2 = solicitar(cliente["cliente_id"], producto, clave=clave, token=cliente["token"])
    assert r1.status_code in (201, 202) and r2.status_code == r1.status_code, \
        f"{r1.status_code}/{r2.status_code}"
    assert r1.json()["prestamo_id"] == r2.json()["prestamo_id"], \
        "la repetición creó un préstamo distinto"

    # 2) Misma clave con cuerpo distinto → 409 (§9).
    r3 = solicitar(cliente["cliente_id"], producto, cantidad=2, clave=clave,
                   token=cliente["token"])
    assert r3.status_code == 409, f"se esperaba 409, llegó {r3.status_code}"

    prestamo_id = r1.json()["prestamo_id"]
    prestamo, traza = esperar_estado(prestamo_id, estados={"APROBADA"})
    reserva_id = prestamo["reserva_id"]
    token_admin = admin_token()

    # 3) Mismo evento repetido (reentrega tras reconexión): un solo efecto.
    e1 = requests.post(f"{URL_INVENTARIO}/reservas/{reserva_id}/entrega",
                       headers=auth(token_admin), timeout=15)
    e2 = requests.post(f"{URL_INVENTARIO}/reservas/{reserva_id}/entrega",
                       headers=auth(token_admin), timeout=15)
    assert e1.status_code == 200, e1.text
    assert e2.status_code == 409, f"la reentrega debió chocar: {e2.status_code}"

    despues = existencia(producto)
    assert despues["total"] == antes["total"] - 1, \
        f"efecto duplicado: {antes['total']} → {despues['total']}"

    # Un solo préstamo con esa clave en el historial del cliente.
    lista = requests.get(f"{URL_PRESTAMOS}/prestamos?pagina=1&tamano=100",
                         headers=auth(token_admin), timeout=15).json()
    del_cliente = [p for p in lista["items"] if p["cliente_id"] == cliente["cliente_id"]]
    assert len(del_cliente) == 1, f"se crearon {len(del_cliente)} préstamos"

    return evidencia(
        CASO, REQUISITO, ESPERADO,
        f"misma clave×2 → 1 préstamo ({prestamo_id[:8]}…); clave repetida con cuerpo "
        f"distinto → 409; entrega repetida → 200 y luego 409 con un solo descuento "
        f"({antes['total']} → {despues['total']}); préstamos del cliente = 1",
        ok=True,
        detalle={"prestamo_id": prestamo_id, "segunda_respuesta_misma_clave": r2.json()["prestamo_id"],
                 "clave_cuerpo_distinto": r3.status_code,
                 "entrega_1": e1.status_code, "entrega_2": e2.status_code,
                 "stock_antes": antes, "stock_despues": despues,
                 "prestamos_del_cliente": len(del_cliente)})


if __name__ == "__main__":
    salir(main())
