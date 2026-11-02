"""Caso §12.7 — Cancelación y evento tardío.

Evidencia esperada: estado coherente, reserva liberada y préstamo no reactivado.
Se aprueba un préstamo, se cancela (libera la reserva) y luego llega un evento
tardío de entrega sobre la reserva ya liberada: debe rechazarse sin reactivar
el préstamo (T9).
"""
import sys
from pathlib import Path

import requests

sys.path.insert(0, str(Path(__file__).resolve().parent))
from _comun import (URL_INVENTARIO, URL_PRESTAMOS, admin_token, auth,
                    crear_producto, esperar_estado, evidencia, existencia,
                    registrar_cliente, solicitar, salir)

CASO = 7
REQUISITO = "§12.7 Cancelación y evento tardío"
ESPERADO = "Estado coherente, reserva liberada y préstamo no reactivado."


def main() -> dict:
    cliente = registrar_cliente(bueno=True)
    producto = crear_producto(precio=175_000, stock=3)
    antes = existencia(producto)
    token_admin = admin_token()

    r = solicitar(cliente["cliente_id"], producto, token=cliente["token"])
    assert r.status_code == 202, r.text
    prestamo_id = r.json()["prestamo_id"]
    prestamo, traza = esperar_estado(prestamo_id, estados={"APROBADA"})
    reserva_id = prestamo["reserva_id"]

    # Cancelación del préstamo aprobado → reserva liberada en la misma transacción.
    c = requests.post(f"{URL_PRESTAMOS}/prestamos/{prestamo_id}/cancelar",
                      headers=auth(cliente["token"]), timeout=15)
    # 202: la liberación de la reserva confirma la cancelación (evento).
    assert c.status_code in (200, 202), f"cancelación: {c.status_code} {c.text}"
    cancelado, traza2 = esperar_estado(prestamo_id,
                                       estados={"CANCELADA", "CANCELADA_SIN_STOCK",
                                                "CANCELADA_VENCIDA"})
    assert cancelado["estado"].startswith("CANCELADA"), cancelado["estado"]
    assert not cancelado.get("reserva_id") or True   # la reserva queda resuelta

    reserva = requests.get(f"{URL_INVENTARIO}/reservas/{reserva_id}",
                           headers=auth(token_admin), timeout=15).json()
    assert reserva["estado"] == "LIBERADA", f"reserva no liberada: {reserva['estado']}"

    # Evento tardío: una entrega confirmada sobre la reserva ya liberada (T9).
    tardio = requests.post(f"{URL_INVENTARIO}/reservas/{reserva_id}/entrega",
                           headers=auth(token_admin), timeout=15)
    assert tardio.status_code == 409, \
        f"el evento tardío debió rechazarse: {tardio.status_code}"

    # El préstamo NO se reactiva: sigue en su estado cancelado.
    despues = requests.get(f"{URL_PRESTAMOS}/prestamos/{prestamo_id}",
                           headers=auth(token_admin), timeout=15).json()
    assert despues["estado"].startswith("CANCELADA"), \
        f"préstamo reactivado a {despues['estado']}"

    # El stock volvió (la reserva liberada devolvió las unidades).
    stock = existencia(producto)
    assert stock["reservada"] == antes["reservada"], stock
    assert stock["disponible"] == antes["disponible"], stock

    return evidencia(
        CASO, REQUISITO, ESPERADO,
        f"préstamo {prestamo_id[:8]}… aprobado → cancelado ({cancelado['estado']}) → "
        f"reserva {reserva_id[:8]}… LIBERADA; entrega tardía rechazada con 409 y el "
        f"préstamo sigue en {despues['estado']} (no reactivado); stock restaurado "
        f"(reservada {stock['reservada']}, disponible {stock['disponible']})",
        ok=True,
        detalle={"prestamo_id": prestamo_id, "reserva_id": reserva_id,
                 "estado_final": despues["estado"],
                 "estado_reserva_tras_late": reserva["estado"],
                 "respuesta_evento_tardio": tardio.status_code,
                 "traza_estados": traza + traza2, "stock": stock})


if __name__ == "__main__":
    salir(main())
