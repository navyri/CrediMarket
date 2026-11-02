"""Caso §12.3 — Riesgo favorable sin existencias.

Evidencia esperada: cancelación por falta de stock; no hay inventario negativo.
"""
import sys
from pathlib import Path

import requests

sys.path.insert(0, str(Path(__file__).resolve().parent))
from _comun import (URL_INVENTARIO, admin_token, auth, crear_producto, evidencia,
                    existencia, registrar_cliente, solicitar, salir)

CASO = 3
REQUISITO = "§12.3 Riesgo favorable sin existencias"
ESPERADO = "Cancelación por falta de stock; no hay inventario negativo."


def main() -> dict:
    cliente = registrar_cliente(bueno=True)   # riesgo favorable
    producto = crear_producto(precio=175_000, stock=0)   # sin existencias

    r = solicitar(cliente["cliente_id"], producto, token=cliente["token"])
    assert r.status_code in (201, 202), f"{r.status_code}: {r.text}"
    cuerpo = r.json()
    prestamo_id = cuerpo["prestamo_id"]

    # La cancelación por stock puede venir del consumidor de Inventario.
    from _comun import esperar_estado
    final, traza = esperar_estado(prestamo_id,
                                  estados={"CANCELADA_SIN_STOCK", "APROBADA",
                                           "RECHAZADA"}, timeout=30)
    assert final["estado"] == "CANCELADA_SIN_STOCK", final["estado"]
    assert "stock" in (final["motivo"] or "").lower() or "existencia" in (final["motivo"] or "").lower(), final["motivo"]

    # No hay reserva y el inventario nunca queda negativo.
    assert not final.get("reserva_id"), "cancelada con reserva"
    stock = existencia(producto)
    if stock is not None:
        assert stock["disponible"] >= 0 and stock["total"] >= 0, stock
        assert stock["reservada"] == 0, stock
    # Y no existe ninguna reserva para este préstamo.
    token_admin = admin_token()
    reservas = requests.get(f"{URL_INVENTARIO}/reservas?limite=100",
                            headers=auth(token_admin), timeout=15).json()
    ajenas = [x for x in reservas if x["prestamo_id"] == prestamo_id]
    assert not ajenas, f"reserva creada sin existencias: {ajenas}"

    return evidencia(
        CASO, REQUISITO, ESPERADO,
        f"préstamo {prestamo_id[:8]}… CANCELADA_SIN_STOCK (motivo: "
        f"{final['motivo']}), sin reserva y sin stock negativo "
        f"(existencia={stock})",
        ok=True,
        detalle={"prestamo_id": prestamo_id, "estado": final["estado"],
                 "motivo": final["motivo"], "traza_estados": traza,
                 "stock": stock, "reservas_del_prestamo": 0})


if __name__ == "__main__":
    salir(main())
