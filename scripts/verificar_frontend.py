"""Verificación del frontend empaquetado en Compose (entregables 2 y 5).

Comprueba, contra el sistema real, que el SPA servido por nginx responde y que
las APIs aceptan al navegador desde ese origen (preflight CORS + respuesta con
`Access-Control-Allow-Origin`), es decir, que el frontend de contenedor puede
consumir Productos, Clientes, Préstamos e Inventario sin secretos en el código.

Uso:  docker compose up -d && python scripts/verificar_frontend.py
Salida: docs/evidencias/frontend_contenedor.json
"""
import json
import os
import sys
from pathlib import Path

import requests

sys.stdout.reconfigure(encoding="utf-8")

RAIZ = Path(__file__).resolve().parents[1]
FRONTEND = os.environ.get("URL_FRONTEND", "http://localhost:8090")
ORIGEN = FRONTEND
URLS = {
    "productos": os.environ.get("URL_PRODUCTOS", "http://localhost:8001"),
    "clientes": os.environ.get("URL_CLIENTES", "http://localhost:8002"),
    "prestamos": os.environ.get("URL_PRESTAMOS", "http://localhost:8003"),
    "inventario": os.environ.get("URL_INVENTARIO", "http://localhost:8004"),
}
ADMIN_EMAIL = os.environ.get("ACEP_ADMIN_EMAIL", "admin@credimarket.demo")
ADMIN_PASSWORD = os.environ.get("ACEP_ADMIN_PASSWORD", "CAMBIAR_admin_local")

comprobaciones: list[dict] = []


def comprobar(nombre: str, condicion: bool, detalle) -> bool:
    comprobaciones.append({"comprobacion": nombre, "ok": bool(condicion),
                           "detalle": detalle})
    print(f"  [{'OK ' if condicion else 'FALLO'}] {nombre}: {detalle}")
    return bool(condicion)


def main() -> int:
    ok = True

    # 1) El SPA responde y trae el HTML de producción (favicon + theme-color).
    r = requests.get(f"{FRONTEND}/", timeout=15)
    cuerpo = r.text
    ok &= comprobar("SPA en nginx", r.status_code == 200,
                    f"GET {FRONTEND}/ → {r.status_code}")
    ok &= comprobar("HTML de producción",
                    'id="raiz"' in cuerpo and "theme-color" in cuerpo
                    and "assets/index-" in cuerpo,
                    "contiene #raiz, theme-color y bundle con hash")

    # 2) Los assets del build cargan.
    assets = [p for p in cuerpo.split('"') if p.startswith("/assets/")]
    cargados = sum(1 for a in set(assets)
                   if requests.get(f"{FRONTEND}{a}", timeout=15).status_code == 200)
    ok &= comprobar("assets del bundle", cargados == len(set(assets)) and cargados > 0,
                    f"{cargados}/{len(set(assets))} con 200")

    # 3) Preflight CORS desde el origen del frontend hacia cada API.
    for nombre, base in URLS.items():
        pre = requests.options(f"{base}/auth/token" if nombre == "clientes"
                               else base + "/",
                               headers={"Origin": ORIGEN,
                                        "Access-Control-Request-Method": "GET",
                                        "Access-Control-Request-Headers":
                                            "authorization,content-type"},
                               timeout=15)
        permitido = ORIGEN in pre.headers.get("Access-Control-Allow-Origin", "")
        ok &= comprobar(f"preflight CORS → {nombre}",
                        pre.status_code in (200, 204) and permitido,
                        f"{pre.status_code} · ACAO="
                        f"{pre.headers.get('Access-Control-Allow-Origin')}")

    # 4) Petición real con Origin: login y lectura del catálogo.
    login = requests.post(f"{URLS['clientes']}/auth/token",
                          json={"email": ADMIN_EMAIL, "password": ADMIN_PASSWORD},
                          headers={"Origin": ORIGEN}, timeout=15)
    ok &= comprobar("login desde el origen del frontend",
                    login.status_code == 200
                    and ORIGEN in login.headers.get("Access-Control-Allow-Origin", ""),
                    f"{login.status_code} · ACAO="
                    f"{login.headers.get('Access-Control-Allow-Origin')}")
    token = login.json().get("access_token")
    catalogo = requests.get(f"{URLS['productos']}/productos",
                            headers={"Origin": ORIGEN,
                                     "Authorization": f"Bearer {token}"},
                            timeout=15)
    ok &= comprobar("catálogo con sesión",
                    catalogo.status_code == 200
                    and ORIGEN in catalogo.headers.get("Access-Control-Allow-Origin", ""),
                    f"{catalogo.status_code} · "
                    f"{len(catalogo.json().get('items', []))} productos")

    evidencia = {
        "verificacion": "frontend empaquetado en Docker (nginx) + CORS (§10, §13.2)",
        "origen": ORIGEN,
        "ok": ok,
        "comprobaciones": comprobaciones,
    }
    destino = RAIZ / "docs" / "evidencias" / "frontend_contenedor.json"
    destino.write_text(json.dumps(evidencia, indent=2, ensure_ascii=False) + "\n",
                       encoding="utf-8")
    print(f"\n{'RESULTADO: OK' if ok else 'RESULTADO: FALLO'} · evidencia en {destino}")
    return 0 if ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
