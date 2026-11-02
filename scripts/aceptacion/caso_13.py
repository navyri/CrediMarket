"""Caso §12.13 — Préstamos ajenos.

Evidencia esperada: un cliente con token propio no lee ni cancela el préstamo
de otro cliente (403); el dueño y el administrador sí pueden.
"""
import sys
from pathlib import Path

import requests

sys.path.insert(0, str(Path(__file__).resolve().parent))
from _comun import (URL_PRESTAMOS, admin_token, auth, crear_producto, evidencia,
                    esperar_estado, registrar_cliente, solicitar, salir)

CASO = 13
REQUISITO = "§12.13 Cliente accede a préstamos ajenos"
ESPERADO = "Rechazado por autorización (403) con token de otro cliente."


def main() -> dict:
    dueno = registrar_cliente(bueno=True)
    ajeno = registrar_cliente(bueno=True)
    producto = crear_producto(precio=175_000, stock=2)

    r = solicitar(dueno["cliente_id"], producto, token=dueno["token"])
    assert r.status_code == 202, r.text
    prestamo_id = r.json()["prestamo_id"]
    esperar_estado(prestamo_id, estados={"APROBADA", "RECHAZADA",
                                         "CANCELADA_SIN_STOCK"})

    # 1) El dueño SÍ lee su préstamo.
    propio = requests.get(f"{URL_PRESTAMOS}/prestamos/{prestamo_id}",
                          headers=auth(dueno["token"]), timeout=15)
    assert propio.status_code == 200, propio.text

    # 2) Otro cliente autenticado: 403 al leerlo…
    ajeno_get = requests.get(f"{URL_PRESTAMOS}/prestamos/{prestamo_id}",
                             headers=auth(ajeno["token"]), timeout=15)
    assert ajeno_get.status_code == 403, \
        f"lectura ajena: {ajeno_get.status_code}"
    # El cuerpo es JSON legible para la interfaz (problem+json o detail).
    assert ajeno_get.json(), "respuesta 403 sin cuerpo legible"

    # …y 403 al intentar cancelarlo.
    ajeno_post = requests.post(f"{URL_PRESTAMOS}/prestamos/{prestamo_id}/cancelar",
                               headers=auth(ajeno["token"]), timeout=15)
    assert ajeno_post.status_code == 403, \
        f"cancelación ajena: {ajeno_post.status_code}"

    # 3) Sin token → 401; el administrador sigue viéndolo (rol superior).
    sin_token = requests.get(f"{URL_PRESTAMOS}/prestamos/{prestamo_id}",
                             timeout=15)
    assert sin_token.status_code == 401, sin_token.status_code
    admin = requests.get(f"{URL_PRESTAMOS}/prestamos/{prestamo_id}",
                         headers=auth(admin_token()), timeout=15)
    assert admin.status_code == 200, admin.status_code

    # El préstamo del dueño no fue tocado por los intentos ajenos.
    final = requests.get(f"{URL_PRESTAMOS}/prestamos/{prestamo_id}",
                         headers=auth(dueno["token"]), timeout=15).json()
    assert final["estado"] == admin.json()["estado"]

    return evidencia(
        CASO, REQUISITO, ESPERADO,
        f"préstamo {prestamo_id[:8]}…: dueño 200, cliente ajeno 403 en GET y "
        f"403 en cancelar (JSON legible), sin token 401, admin 200; estado "
        f"inalalterado {final['estado']}",
        ok=True,
        detalle={"prestamo_id": prestamo_id,
                 "dueno_get": propio.status_code,
                 "ajeno_get": ajeno_get.status_code,
                 "ajeno_cancelar": ajeno_post.status_code,
                 "sin_token": sin_token.status_code,
                 "admin_get": admin.status_code,
                 "estado_final": final["estado"]})


if __name__ == "__main__":
    salir(main())
