"""Caso §12.4 — Dos solicitudes por la última unidad.

Evidencia esperada: solo una obtiene la reserva. Se prueban dos solicitudes
CONCURRENTES (httpx + asyncio) sobre un producto con stock = 1.
"""
import asyncio
import sys
from pathlib import Path

import httpx

sys.path.insert(0, str(Path(__file__).resolve().parent))
from _comun import (URL_PRESTAMOS, admin_token, auth, crear_producto, evidencia,
                    existencia, registrar_cliente, salir)

CASO = 4
REQUISITO = "§12.4 Dos solicitudes por la última unidad"
ESPERADO = "Solo una obtiene la reserva."


async def _solicitar_async(client: httpx.AsyncClient, cliente_id: str,
                           producto_id: str, token: str) -> tuple[int, dict]:
    import uuid
    r = await client.post(f"{URL_PRESTAMOS}/prestamos",
                          headers={**auth(token),
                                   "Idempotency-Key": str(uuid.uuid4())},
                          json={"cliente_id": cliente_id, "producto_id": producto_id,
                                "cantidad": 1, "plazo_meses": 12})
    return r.status_code, r.json()


async def _ambas(cliente_a: dict, cliente_b: dict, producto: str):
    async with httpx.AsyncClient(timeout=30) as client:
        return await asyncio.gather(
            _solicitar_async(client, cliente_a["cliente_id"], producto, cliente_a["token"]),
            _solicitar_async(client, cliente_b["cliente_id"], producto, cliente_b["token"]))


def main() -> dict:
    import time

    cliente_a = registrar_cliente(bueno=True)
    cliente_b = registrar_cliente(bueno=True)
    producto = crear_producto(precio=175_000, stock=1)
    antes = existencia(producto)

    respuestas = asyncio.run(_ambas(cliente_a, cliente_b, producto))
    estados_http = [c for c, _ in respuestas]
    assert all(c in (201, 202) for c in estados_http), f"códigos: {estados_http}"
    ids = [cuerpo["prestamo_id"] for _, cuerpo in respuestas]
    assert ids[0] != ids[1], "las dos solicitudes generaron el mismo préstamo"

    # Ambas llegan a estado final; exactamente una debe estar aprobada.
    from _comun import esperar_estado
    finales = []
    for pid in ids:
        prestamo, traza = esperar_estado(pid, estados={"APROBADA", "RECHAZADA",
                                                       "CANCELADA_SIN_STOCK"},
                                         timeout=45)
        finales.append((prestamo, traza))

    estados = sorted(p["estado"] for p, _ in finales)
    assert estados == ["APROBADA", "CANCELADA_SIN_STOCK"], f"estados: {estados}"

    aprobado = next(p for p, _ in finales if p["estado"] == "APROBADA")
    cancelado = next(p for p, _ in finales if p["estado"] == "CANCELADA_SIN_STOCK")
    assert aprobado["reserva_id"], "la ganadora no tiene reserva"
    assert not cancelado.get("reserva_id"), "la perdedora tiene reserva"

    # Inventario coherente: 1 reservada (la ganadora), 0 disponibles.
    stock = existencia(producto)
    assert stock["total"] == antes["total"] == 1
    assert stock["reservada"] == 1 and stock["disponible"] == 0, stock

    return evidencia(
        CASO, REQUISITO, ESPERADO,
        f"dos POST concurrentes sobre stock=1 → {aprobado['id'][:8]}… APROBADA con "
        f"reserva y {cancelado['id'][:8]}… CANCELADA_SIN_STOCK sin reserva; "
        f"stock final total=1 reservada=1 disponible=0",
        ok=True,
        detalle={"prestamo_ganador": aprobado["id"],
                 "prestamo_perdedor": cancelado["id"],
                 "codigos_http": estados_http, "stock": stock,
                 "motivo_perdedor": cancelado["motivo"]})


if __name__ == "__main__":
    salir(main())
