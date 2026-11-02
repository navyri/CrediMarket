"""Utilidades compartidas por las 16 pruebas de aceptación de §12.

Cada caso es un script independiente (`caso_NN.py`) que corre contra el
Compose real (sin mocks) y deja su evidencia en
`docs/evidencias/aceptacion/caso_NN.json`. El orquestador `ejecutar_todas.py`
produce `resultados.json`.

Uso:  python scripts/aceptacion/caso_01.py
"""
import json
import os
import sys
import time
import uuid
from pathlib import Path

import requests

# Windows (cp1252) no imprime flechas/acentos: el resto de la suite ya corre
# con UTF-8 y las evidencias contienen `→` y `…`.
if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")

RAIZ = Path(__file__).resolve().parents[2]
EVIDENCIAS = RAIZ / "docs" / "evidencias" / "aceptacion"
EVIDENCIAS.mkdir(parents=True, exist_ok=True)

URL_PRODUCTOS = os.environ.get("API_PRODUCTOS", "http://localhost:8001")
URL_CLIENTES = os.environ.get("API_CLIENTES", "http://localhost:8002")
URL_PRESTAMOS = os.environ.get("API_PRESTAMOS", "http://localhost:8003")
URL_INVENTARIO = os.environ.get("API_INVENTARIO", "http://localhost:8004")

ADMIN_EMAIL = os.environ.get("ACEP_ADMIN_EMAIL", "admin@credimarket.demo")
ADMIN_PASSWORD = os.environ.get("ACEP_ADMIN_PASSWORD", "CAMBIAR_admin_local")


def admin_token() -> str:
    r = requests.post(f"{URL_CLIENTES}/auth/token",
                      json={"email": ADMIN_EMAIL, "password": ADMIN_PASSWORD},
                      timeout=15)
    r.raise_for_status()
    return r.json()["access_token"]


def auth(token: str) -> dict:
    return {"Authorization": f"Bearer {token}"}


def registrar_cliente(bueno: bool = True) -> dict:
    """Crea un cliente de aceptación con perfil que garantiza el resultado.

    `bueno=True` → riesgo favorable (decisión del modelo por debajo del umbral);
    `bueno=False` → deuda > ingresos, la regla de control lo rechaza.
    """
    sufijo = uuid.uuid4().hex[:10]
    email = f"acep-{sufijo}@demo.local"
    doc = f"ACEP-{sufijo}"
    r = requests.post(f"{URL_CLIENTES}/auth/registro", json={
        "email": email, "password": "clave_aceptacion_1",
        "documento_identidad": doc, "nombre": f"Cliente Aceptación {sufijo}",
        "ciudad": "Bogota"}, timeout=15)
    r.raise_for_status()
    cuerpo = r.json()
    perfil = ({"ingresos_mensuales_cop": 4_000_000, "obligaciones_mensuales_cop": 500_000,
               "tipo_empleo": "dependiente", "antiguedad_laboral_meses": 36,
               "meses_historial_crediticio": 48, "creditos_previos": 2,
               "atrasos_previos_30d": 0, "porcentaje_pago_puntual": 95}
              if bueno else
              {"ingresos_mensuales_cop": 1_000_000, "obligaciones_mensuales_cop": 5_000_000,
               "tipo_empleo": "independiente", "antiguedad_laboral_meses": 6,
               "meses_historial_crediticio": 12, "creditos_previos": 5,
               "atrasos_previos_30d": 9, "porcentaje_pago_puntual": 40})
    p = requests.patch(f"{URL_CLIENTES}/clientes/{cuerpo['cliente_id']}",
                       json=perfil, headers=auth(cuerpo["access_token"]), timeout=15)
    p.raise_for_status()
    return {"cliente_id": cuerpo["cliente_id"], "token": cuerpo["access_token"],
            "email": email, "documento": doc}


def crear_producto(precio: float, stock: int, sku: str | None = None) -> str:
    """Producto activo con existencias registradas (admin). Devuelve su id."""
    sku = sku or f"AC-{uuid.uuid4().hex[:8]}"
    r = requests.post(f"{URL_PRODUCTOS}/productos", headers=auth(admin_token()), json={
        "sku": sku, "nombre": f"Producto aceptación {sku}",
        "categoria": "pruebas", "precio_cop": precio,
        "descripcion": "creado por scripts/aceptacion"}, timeout=15)
    r.raise_for_status()
    pid = r.json()["id"]
    if stock > 0:
        e = requests.post(f"{URL_INVENTARIO}/entradas", headers=auth(admin_token()),
                          json={"producto_id": pid, "cantidad": stock,
                                "referencia": "aceptacion"}, timeout=15)
        e.raise_for_status()
    return pid


def solicitar(cliente_id: str, producto_id: str, cantidad: int = 1,
              plazo: int = 12, clave: str | None = None,
              token: str | None = None) -> requests.Response:
    """POST /prestamos con Idempotency-Key (§9); devuelve la respuesta cruda."""
    return requests.post(f"{URL_PRESTAMOS}/prestamos",
                         headers={**auth(token or admin_token()),
                                  "Idempotency-Key": clave or str(uuid.uuid4())},
                         json={"cliente_id": cliente_id, "producto_id": producto_id,
                               "cantidad": cantidad, "plazo_meses": plazo},
                         timeout=30)


def esperar_estado(prestamo_id: str, estados: set[str], timeout: float = 45.0,
                   token: str | None = None) -> tuple[dict, list[str]]:
    """Polling (igual que la interfaz) hasta un estado final; devuelve (préstamo, traza)."""
    inicio = time.time()
    traza: list[str] = []
    while time.time() - inicio < timeout:
        r = requests.get(f"{URL_PRESTAMOS}/prestamos/{prestamo_id}",
                         headers=auth(token or admin_token()), timeout=15)
        r.raise_for_status()
        prestamo = r.json()
        if not traza or traza[-1] != prestamo["estado"]:
            traza.append(prestamo["estado"])
        if prestamo["estado"] in estados:
            return prestamo, traza
        time.sleep(0.5)
    raise TimeoutError(f"sin estado final en {timeout}s; traza={traza}")


def existencia(producto_id: str, token: str | None = None) -> dict | None:
    r = requests.get(f"{URL_INVENTARIO}/existencias/{producto_id}",
                     headers=auth(token or admin_token()), timeout=15)
    return r.json() if r.status_code == 200 else None


def redis_cli():
    """Cliente Redis real del Compose (para los casos 8 y 9)."""
    import redis
    return redis.Redis.from_url(
        os.environ.get("REDIS_URL", "redis://localhost:6379/0"),
        password=os.environ.get("REDIS_PASSWORD", "CAMBIAR_redis_local"),
        decode_responses=True)


def evidencia(caso: int, requisito: str, esperado: str, observado: str,
              ok: bool, detalle: dict | None = None) -> dict:
    """Escribe `docs/evidencias/aceptacion/caso_NN.json` y devuelve el registro."""
    registro = {
        "id": f"P2-TEST-{caso:03d}",
        "caso_s12": caso,
        "requisito": requisito,
        "esperado": esperado,
        "observado": observado,
        "estado": "OK" if ok else "FALLO",
        "detalle": detalle or {},
        "ejecutado_en": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        "commit": _commit(),
    }
    ruta = EVIDENCIAS / f"caso_{caso:02d}.json"
    ruta.write_text(json.dumps(registro, ensure_ascii=False, indent=2),
                    encoding="utf-8")
    print(f"[{'OK ' if ok else 'FALLO'}] P2-TEST-{caso:03d}: {observado}")
    return registro


def _commit() -> str:
    import subprocess
    try:
        salida = subprocess.run(["git", "rev-parse", "--short", "HEAD"],
                                cwd=RAIZ, capture_output=True, text=True, timeout=15)
        return salida.stdout.strip() or "desconocido"
    except Exception:
        return "desconocido"


def salir(registro: dict) -> None:
    sys.exit(0 if registro["estado"] == "OK" else 1)
