"""Caso §12.16 — Formulario inválido / sesión vencida / API caída.

Evidencia esperada: mensajes claros y recuperación. Cubre:
- solicitud sin `Idempotency-Key` → 400 problem+json con `errors[]`;
- campo extra en el cuerpo → 422 (extra="forbid", §4: el cliente no envía precio);
- JWT expirado → 401 con detalle;
- API caída → `ConnectionError` del cliente y recuperación al volver el servicio.
"""
import sys
import time
from pathlib import Path

import jwt
import requests

sys.path.insert(0, str(Path(__file__).resolve().parent))
from _comun import (URL_PRESTAMOS, admin_token, auth, crear_producto, evidencia,
                    registrar_cliente, salir)

CASO = 16
REQUISITO = "§12.16 Formulario inválido / sesión vencida / API caída"
ESPERADO = "Mensajes claros y recuperación."


def _problem(r: requests.Response) -> dict:
    assert r.headers.get("content-type", "").startswith(
        "application/problem+json"), f"sin problem+json: {r.headers}"
    return r.json()


def main() -> dict:
    cliente = registrar_cliente(bueno=True)
    producto = crear_producto(precio=175_000, stock=1)
    detalle: dict = {}

    # 1) Formulario inválido: falta Idempotency-Key → 400 + errors[] por campo.
    r1 = requests.post(f"{URL_PRESTAMOS}/prestamos", headers=auth(cliente["token"]),
                       json={"cliente_id": cliente["cliente_id"],
                             "producto_id": producto, "cantidad": 1,
                             "plazo_meses": 12}, timeout=30)
    assert r1.status_code == 400, r1.status_code
    p1 = _problem(r1)
    assert p1["title"] == "Solicitud inválida", p1
    assert any(e.get("campo") == "Idempotency-Key" for e in p1.get("errors", [])), p1
    detalle["sin_idempotency_key"] = {"status": r1.status_code, "detail": p1.get("detail")}

    # 2) Campo prohibido: precio (el navegador NUNCA lo envía, §4).
    #    Convención del proyecto (contratos-rest.md): la validación de
    #    FastAPI se mapea a 400 problem+json con `errors[]` por campo.
    r2 = requests.post(f"{URL_PRESTAMOS}/prestamos",
                       headers={**auth(cliente["token"]),
                                "Idempotency-Key": f"extra-{int(time.time())}"},
                       json={"cliente_id": cliente["cliente_id"],
                             "producto_id": producto, "cantidad": 1,
                             "plazo_meses": 12, "precio_unitario_cop": 1},
                       timeout=30)
    assert r2.status_code == 400, r2.status_code
    p2 = _problem(r2)
    assert any(e.get("campo") == "precio_unitario_cop"
               for e in p2.get("errors", [])), p2
    detalle["campo_extra"] = {"status": r2.status_code,
                              "errors": p2.get("errors")}

    # 3) Sesión vencida: JWT firmado con el secreto correcto pero expirado → 401.
    import os
    vencido = jwt.encode({"sub": cliente["cliente_id"], "rol": "cliente",
                          "cliente_id": cliente["cliente_id"],
                          "exp": int(time.time()) - 3600},
                         os.environ.get("JWT_SECRET", "CAMBIAR_jwt_local_largo_32+"),
                         algorithm="HS256")
    r3 = requests.get(f"{URL_PRESTAMOS}/prestamos/{producto}",   # 404/401: importa el 401
                      headers=auth(vencido), timeout=15)
    assert r3.status_code == 401, r3.status_code
    # El guardián envuelve el problema en `detail` ({"title":…, "detail":…}).
    p3 = r3.json().get("detail") or {}
    assert p3.get("title") == "Sesión vencida", p3
    assert "expir" in (p3.get("detail") or "").lower(), p3
    detalle["jwt_expirado"] = {"status": r3.status_code, "detail": p3.get("detail")}

    # 4) API caída: se detiene el contenedor de Préstamos; el cliente falla
    #    con ConnectionError y, al volver el servicio, se recupera.
    import subprocess
    from _comun import RAIZ

    def _compose(*args: str) -> subprocess.CompletedProcess:
        return subprocess.run(["docker", "compose", *args], cwd=RAIZ,
                              capture_output=True, text=True, timeout=300)

    bajar = False
    try:
        _compose("stop", "prestamos")
        bajar = True
        time.sleep(2)
        try:
            requests.get(f"{URL_PRESTAMOS}/prestamos?pagina=1&tamano=1",
                         headers=auth(admin_token()), timeout=5)
            raise AssertionError("el servicio seguía respondiendo tras detenerlo")
        except requests.exceptions.ConnectionError:
            pass
        detalle["api_caida"] = {"excepcion": "ConnectionError",
                                "servicio": "prestamos detenido"}

        # Recuperación: al volver el servicio, la misma llamada responde 200.
        _compose("start", "prestamos")
        bajar = False
        recuperado = False
        for _ in range(60):
            try:
                g = requests.get(f"{URL_PRESTAMOS}/prestamos?pagina=1&tamano=1",
                                 headers=auth(admin_token()), timeout=5)
                if g.status_code == 200:
                    recuperado = True
                    break
            except requests.exceptions.ConnectionError:
                pass
            time.sleep(1)
        assert recuperado, "el servicio no se recuperó"
        detalle["api_caida"]["recuperado"] = True
    finally:
        if bajar:   # el servicio siempre termina levantado
            _compose("start", "prestamos")

    return evidencia(
        CASO, REQUISITO, ESPERADO,
        f"sin Idempotency-Key → 400 problem+json con errors[]; precio extra → "
        f"400 problem+json con errors[] por campo; JWT expirado → 401 "
        f"'{p3.get('detail')}'; API detenida → ConnectionError y recuperación "
        f"confirmada con 200",
        ok=True, detalle=detalle)


if __name__ == "__main__":
    salir(main())
