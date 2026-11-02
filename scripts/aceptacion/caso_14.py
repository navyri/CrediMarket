"""Caso §12.14 — Flujo desde frontend.

Evidencia esperada: el build del frontend existe y la secuencia EXACTA que
ejecuta la interfaz (§10) reproducida por REST deja los mismos datos
persistidos: registro → perfil → catálogo (precio del sistema) → solicitud
sin precio → aprobación con reserva.
"""
import subprocess
import sys
import time
from pathlib import Path

import requests

sys.path.insert(0, str(Path(__file__).resolve().parent))
from _comun import (RAIZ, URL_CLIENTES, URL_PRESTAMOS, admin_token, auth,
                    crear_producto, esperar_estado, evidencia, registrar_cliente,
                    salir)

CASO = 14
REQUISITO = "§12.14 Flujo desde frontend"
ESPERADO = "Navegador, datos persistidos (la secuencia de la UI deja estado real)."


def main() -> dict:
    # 1) El frontend compila (el bundle que sirve la interfaz).
    import shutil
    npm = shutil.which("npm") or "npm"     # Windows: resuelve npm.cmd
    build = subprocess.run([npm, "run", "build"], cwd=RAIZ / "frontend",
                           capture_output=True, text=True, timeout=600)
    assert build.returncode == 0, f"build falló: {build.stderr[-800:]}"
    dist = RAIZ / "frontend" / "dist" / "index.html"
    assert dist.exists(), "sin dist/index.html tras el build"

    # 2) Misma secuencia que la UI, en el mismo orden (sin precio ni tasa):
    #    a. Crear cuenta (POST /auth/registro) + perfil financiero (PATCH).
    cliente = registrar_cliente(bueno=True)

    #    b. Catálogo: el precio lo manda Productos (GET), el navegador no lo envía.
    producto = crear_producto(precio=175_000, stock=3)
    token_admin = admin_token()
    catalogo = requests.get(f"{URL_CLIENTES.replace('8002', '8001')}"
                            f"/productos/{producto}", timeout=15).json()
    assert float(catalogo["precio_cop"]) == 175000

    #    c. Solicitud con solo producto/cantidad/plazo + Idempotency-Key.
    r = requests.post(f"{URL_PRESTAMOS}/prestamos",
                      headers={**auth(cliente["token"]),
                               "Idempotency-Key": f"ui-{int(time.time())}"},
                      json={"cliente_id": cliente["cliente_id"],
                            "producto_id": producto, "cantidad": 1,
                            "plazo_meses": 12}, timeout=30)
    assert r.status_code == 202, f"{r.status_code}: {r.text}"
    cuerpo = r.json()
    assert float(cuerpo["precio_unitario_cop"]) == 175000, \
        "no usó la cotización vigente"
    assert cuerpo["estado"] == "PENDIENTE_INVENTARIO"

    #    d. Seguimiento (polling de la UI) hasta la aprobación final.
    prestamo, traza = esperar_estado(cuerpo["prestamo_id"],
                                     estados={"APROBADA", "RECHAZADA",
                                              "CANCELADA_SIN_STOCK"})
    assert prestamo["estado"] == "APROBADA", prestamo["estado"]

    # 3) Los datos quedan PERSISTIDOS (relectura independiente como hace la UI
    #    al volver a la pantalla de detalle).
    leido = requests.get(f"{URL_PRESTAMOS}/prestamos/{prestamo['id']}",
                         headers=auth(token_admin), timeout=15).json()
    assert leido["producto_id"] == producto
    assert leido["cliente_id"] == cliente["cliente_id"]
    assert float(leido["monto_total_cop"]) == 175000
    assert leido["reserva_id"] and leido["estado"] == "APROBADA"

    return evidencia(
        CASO, REQUISITO, ESPERADO,
        f"build OK (dist/index.html) y secuencia de la UI reproducida por REST: "
        f"registro+perfil → catálogo 175.000 → solicitud 202 → "
        f"{'→'.join(traza)} con reserva {leido['reserva_id'][:8]}…; relectura "
        f"persistida (monto {leido['monto_total_cop']}, estado {leido['estado']})",
        ok=True,
        detalle={"build": build.returncode, "dist": str(dist.relative_to(RAIZ)),
                 "prestamo_id": leido["id"], "reserva_id": leido["reserva_id"],
                 "traza_estados": traza, "monto_total_cop": leido["monto_total_cop"],
                 "precio_unitario_cop": leido["precio_unitario_cop"]})


if __name__ == "__main__":
    salir(main())
