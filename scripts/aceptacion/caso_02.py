"""Caso §12.2 — Solicitud rechazada.

Evidencia esperada: registro de la decisión y versión del modelo; no hay reserva.
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from _comun import (crear_producto, evidencia, existencia, registrar_cliente,
                    solicitar, salir)

CASO = 2
REQUISITO = "§12.2 Solicitud rechazada"
ESPERADO = "Registro de la decisión y versión del modelo; no hay reserva."


def main() -> dict:
    # Perfil con deuda > ingresos: la regla de control previa lo rechaza.
    cliente = registrar_cliente(bueno=False)
    producto = crear_producto(precio=175_000, stock=3)
    stock = existencia(producto)

    r = solicitar(cliente["cliente_id"], producto, token=cliente["token"])
    assert r.status_code in (201, 202), f"{r.status_code}: {r.text}"
    cuerpo = r.json()
    prestamo_id = cuerpo["prestamo_id"]

    assert cuerpo["estado"] == "RECHAZADA", cuerpo["estado"]
    assert cuerpo["motivo"], "rechazo sin motivo registrado"
    assert cuerpo["modelo_version"], "decisión sin versión del modelo"
    assert not cuerpo.get("reserva_id"), "rechazo con reserva asociada"

    # La decisión queda persistida (no es una respuesta simulada).
    from _comun import URL_PRESTAMOS, admin_token, auth
    import requests
    leido = requests.get(f"{URL_PRESTAMOS}/prestamos/{prestamo_id}",
                         headers=auth(admin_token()), timeout=15).json()
    assert leido["estado"] == "RECHAZADA" and leido["motivo"] == cuerpo["motivo"]
    assert leido["modelo_version"] == cuerpo["modelo_version"]

    # El inventario no se tocó.
    despues = existencia(producto)
    assert despues["reservada"] == stock["reservada"] == 0, despues

    return evidencia(
        CASO, REQUISITO, ESPERADO,
        f"préstamo {prestamo_id[:8]}… RECHAZADA y persistida: motivo "
        f"{cuerpo['motivo']!r}, modelo {cuerpo['modelo_version']}, sin reserva "
        f"(reservada={despues['reservada']})",
        ok=True,
        detalle={"prestamo_id": prestamo_id, "motivo": cuerpo["motivo"],
                 "modelo_version": cuerpo["modelo_version"],
                 "probabilidad": cuerpo["probabilidad_incumplimiento"],
                 "umbral": cuerpo["umbral"], "reserva_id": None,
                 "stock": despues})


if __name__ == "__main__":
    salir(main())
