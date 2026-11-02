"""Caso §12.1 — Riesgo favorable con existencias.

Evidencia esperada: reserva confirmada, préstamo aprobado y entrega simulada
coherente (el stock descuenta exactamente una vez).
"""
import sys
from pathlib import Path

import requests

sys.path.insert(0, str(Path(__file__).resolve().parent))
from _comun import (URL_INVENTARIO, admin_token, auth, crear_producto,
                    esperar_estado, evidencia, existencia, registrar_cliente,
                    solicitar, salir)

CASO = 1
REQUISITO = "§12.1 Riesgo favorable con existencias"
ESPERADO = "Reserva confirmada, préstamo aprobado y entrega simulada coherente."


def main() -> dict:
    cliente = registrar_cliente(bueno=True)
    producto = crear_producto(precio=175_000, stock=5)
    antes = existencia(producto)

    r = solicitar(cliente["cliente_id"], producto, cantidad=2, token=cliente["token"])
    assert r.status_code == 202, f"se esperaba 202, llegó {r.status_code}: {r.text}"
    pendiente = r.json()
    assert pendiente["estado"] == "PENDIENTE_INVENTARIO", pendiente["estado"]
    prestamo_id = pendiente["prestamo_id"]

    # El backend confirma la reserva por el broker; la interfaz haría este polling.
    prestamo, traza = esperar_estado(prestamo_id,
                                     estados={"APROBADA", "RECHAZADA",
                                              "CANCELADA_SIN_STOCK"})
    assert prestamo["estado"] == "APROBADA", f"estado final {prestamo['estado']}"
    assert prestamo["reserva_id"], "aprobada sin reserva confirmada"

    token_admin = admin_token()
    reserva = requests.get(f"{URL_INVENTARIO}/reservas/{prestamo['reserva_id']}",
                           headers=auth(token_admin), timeout=15).json()
    assert reserva["estado"] == "RESERVADA" and reserva["cantidad"] == 2, reserva

    # Entrega simulada → el préstamo pasa a COMPLETADA y el stock descuenta.
    ent = requests.post(f"{URL_INVENTARIO}/reservas/{prestamo['reserva_id']}/entrega",
                        headers=auth(token_admin), timeout=15)
    assert ent.status_code == 200, ent.text
    final, traza2 = esperar_estado(prestamo_id, estados={"COMPLETADA"})
    despues = existencia(producto)
    assert despues["total"] == antes["total"] - 2, "la entrega no descontó el stock"
    # `antes` se midió ANTES de la reserva (reservada=0): al entregar, las 2
    # unidades reservadas salen del total y reservada vuelve a 0.
    assert despues["reservada"] == antes["reservada"], despues
    assert despues["disponible"] == antes["disponible"] - 2
    assert despues["disponible"] >= 0, "inventario negativo"

    return evidencia(
        CASO, REQUISITO, ESPERADO,
        f"préstamo {prestamo_id[:8]}… aprobado con reserva "
        f"{prestamo['reserva_id'][:8]}… y entregado (traza {'→'.join(traza + traza2)}); "
        f"stock {antes['total']}/{antes['reservada']} → "
        f"{despues['total']}/{despues['reservada']}",
        ok=True,
        detalle={"prestamo_id": prestamo_id, "reserva_id": prestamo["reserva_id"],
                 "traza_estados": traza + traza2, "stock_antes": antes,
                 "stock_despues": despues, "monto_total_cop": prestamo["monto_total_cop"]})


if __name__ == "__main__":
    salir(main())
