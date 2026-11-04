"""§10/§13.7 · Siembra el catálogo de demostración (productos + existencias).

Un clon limpio trae PostgreSQL vacío: el admin lo crea el arranque de Clientes,
pero **no** hay productos ni stock, y sin ellos los escenarios 3.2–3.4 de
`docs/guia-demo.md` (aprobado, rechazo y sin existencias) no se pueden ejecutar
desde el navegador.

Este script crea un catálogo pequeño pero completo usando las APIs reales (sin
atajos a la base de datos):

  · 6 productos con SKU estable `DEMO-01…DEMO-06` → **idempotente**: repetirlo
    no duplica nada;
  · 5 con existencias y **1 sin stock** (para el escenario CANCELADA_SIN_STOCK);
  · 2 con precio distinto para mostrar la invalidación de caché (§6, escenario
    de precio modificado).

Uso (con el Compose levantado y el modelo activo listo):

    python scripts/sembrar_demo.py [--stock 10] [--forzar]
"""
import argparse
import json
import os
import sys
import urllib.error
import urllib.request
from pathlib import Path

URL_PRODUCTOS = os.environ.get("API_PRODUCTOS", "http://localhost:8001")
URL_INVENTARIO = os.environ.get("API_INVENTARIO", "http://localhost:8004")
URL_CLIENTES = os.environ.get("API_CLIENTES", "http://localhost:8002")

ADMIN_EMAIL = os.environ.get("ACEP_ADMIN_EMAIL", "admin@credimarket.demo")
ADMIN_PASSWORD = os.environ.get("ACEP_ADMIN_PASSWORD", "CAMBIAR_admin_local")

# SKU estable + precio + existencias objetivo (0 = sin stock, a propósito).
CATALOGO = [
    ("DEMO-01", "Laptop Credi 15\"", "tecnologia", 2_450_000, True),
    ("DEMO-02", "Monitor Credi 27\"", "tecnologia", 890_000, True),
    ("DEMO-03", "Silla ergonómica", "hogar", 640_000, True),
    ("DEMO-04", "Bicicleta urbana", "deporte", 1_180_000, True),
    ("DEMO-05", "Set de ollas acero", "hogar", 385_000, True),
    # Sin existencias: el escenario 3.4 debe terminar en CANCELADA_SIN_STOCK.
    ("DEMO-06", "Consola Credi Play", "tecnologia", 1_990_000, False),
]


def pedir(metodo: str, url: str, token: str | None = None,
          cuerpo: dict | None = None) -> tuple[int, dict]:
    datos = json.dumps(cuerpo).encode("utf-8") if cuerpo is not None else None
    peticion = urllib.request.Request(url, data=datos, method=metodo)
    peticion.add_header("Content-Type", "application/json")
    if token:
        peticion.add_header("Authorization", f"Bearer {token}")
    try:
        with urllib.request.urlopen(peticion, timeout=20) as respuesta:
            texto = respuesta.read().decode("utf-8")
            return respuesta.status, json.loads(texto) if texto else {}
    except urllib.error.HTTPError as error:
        texto = error.read().decode("utf-8")
        try:
            return error.code, json.loads(texto) if texto else {}
        except json.JSONDecodeError:
            return error.code, {"detail": texto}


def token_admin() -> str:
    estado, cuerpo = pedir("POST", f"{URL_CLIENTES}/auth/token",
                           cuerpo={"email": ADMIN_EMAIL,
                                   "password": ADMIN_PASSWORD})
    if estado != 200:
        raise SystemExit(
            f"no se pudo iniciar sesión como admin ({estado}): {cuerpo}\n"
            "¿Está el Compose levantado? ¿Cambiaste ADMIN_PASSWORD en .env?")
    return cuerpo["access_token"]


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--stock", type=int, default=10,
                        help="existencias por producto con stock (por defecto 10)")
    parser.add_argument("--forzar", action="store_true",
                        help="crea los productos aunque ya existan los SKUs")
    args = parser.parse_args()

    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")

    token = token_admin()
    creados = existentes = rellenados = 0
    print(f"{'SKU':10} {'producto':28} {'precio':>12} {'stock':>7}")

    for sku, nombre, categoria, precio, con_stock in CATALOGO:
        estado, producto = pedir(
            "POST", f"{URL_PRODUCTOS}/productos", token,
            {"sku": sku, "nombre": nombre, "categoria": categoria,
             "precio_cop": precio, "descripcion": "semilla de demostración"})

        if estado == 201:
            pid = producto["id"]
            creados += 1
        elif estado in (409, 400) and not args.forzar:
            # Ya existe el SKU: lo buscamos para completar su stock.
            lista = pedir("GET", f"{URL_PRODUCTOS}/productos?tamano=100", token)[1]
            coincidencia = next((p for p in lista.get("items", [])
                                 if p.get("sku") == sku), None)
            if coincidencia is None:
                print(f"{sku:10} {nombre:28} no se pudo localizar ({estado})")
                continue
            pid = coincidencia["id"]
            existentes += 1
        else:
            raise SystemExit(f"no se pudo crear {sku}: {estado} {producto}")

        objetivo = args.stock if con_stock else 0
        if objetivo > 0:
            actual = pedir("GET", f"{URL_INVENTARIO}/existencias/{pid}", token)[1]
            disponibles = int(actual.get("disponible", 0) or 0) if actual else 0
            if disponibles < objetivo:
                faltan = objetivo - disponibles
                estado_e, cuerpo_e = pedir(
                    "POST", f"{URL_INVENTARIO}/entradas", token,
                    {"producto_id": pid, "cantidad": faltan,
                     "referencia": "siembra de demo"})
                if estado_e not in (200, 201):
                    raise SystemExit(f"no se pudo registrar stock de {sku}: "
                                     f"{estado_e} {cuerpo_e}")
                rellenados += 1
                disponibles = objetivo
        else:
            disponibles = 0

        marca = "" if con_stock else "  ← sin stock (escenario 3.4)"
        print(f"{sku:10} {nombre:28} {precio:12,} {disponibles:7}{marca}")

    print(f"\nCreados {creados} · ya existían {existentes} · "
          f"stock completado {rellenados}")
    print(f"Catálogo listo en {URL_PRODUCTOS}/productos "
          f"(frontend: http://localhost:8090)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
