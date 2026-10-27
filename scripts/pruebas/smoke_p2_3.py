"""Verificación manual extremo a extremo de P2-3 contra los contenedores reales.

Uso:  python scripts/pruebas/smoke_p2_3.py
Requiere: docker compose up -d --build (productos :8001, clientes :8002, redis, pg).
"""
import os
import sys
import time
import uuid

import httpx
import jwt

BASE_PROD = os.environ.get("URL_PRODUCTOS_LOCAL", "http://localhost:8001")
BASE_CLI = os.environ.get("URL_CLIENTES_LOCAL", "http://localhost:8002")
JWT_SECRET = os.environ.get("JWT_SECRET", "CAMBIAR_jwt_local_largo_32+")
ADMIN_EMAIL = os.environ.get("ADMIN_EMAIL", "admin@credimarket.demo")
ADMIN_PASSWORD = os.environ.get("ADMIN_PASSWORD", "CAMBIAR_admin_local")

PASOS: list[tuple[str, bool, str]] = []

# La consola de Windows (cp1252) no admite flechas Unicode; se fija UTF-8.
if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")


def comprobar(nombre: str, condicion: bool, detalle: str = "") -> None:
    PASOS.append((nombre, condicion, detalle))
    print(f"  [{'OK ' if condicion else 'FALLA'}] {nombre} {detalle}")


def token_servicio() -> str:
    """Rol `servicio`: firmado con el mismo secreto (uso interno, §9)."""
    return jwt.encode({"sub": "prestamos", "rol": "servicio", "cliente_id": None,
                       "exp": int(time.time()) + 600},
                      JWT_SECRET, algorithm="HS256")


def main() -> int:
    print("== P2-3 · verificación extremo a extremo ==")
    with httpx.Client(timeout=15) as c:
        # --- salud y listo ---
        comprobar("productos /health", c.get(f"{BASE_PROD}/health").status_code == 200)
        comprobar("productos /ready (bd+redis)",
                  c.get(f"{BASE_PROD}/ready").json().get("bd") is True)
        comprobar("clientes /health", c.get(f"{BASE_CLI}/health").status_code == 200)

        # --- autenticación de administrador ---
        login = c.post(f"{BASE_CLI}/auth/token",
                       json={"email": ADMIN_EMAIL, "password": ADMIN_PASSWORD})
        comprobar("login administrador", login.status_code == 200, f"({login.status_code})")
        if login.status_code != 200:
            return 1
        admin = {"Authorization": f"Bearer {login.json()['access_token']}"}

        # --- registro de cliente y propiedad del recurso ---
        correo = f"demo-{uuid.uuid4().hex[:8]}@demo.local"
        reg = c.post(f"{BASE_CLI}/auth/registro", json={
            "email": correo, "password": "clave-de-demo-123",
            "documento_identidad": f"DOC-{uuid.uuid4().hex[:8]}",
            "nombre": "Cliente Demo", "ciudad": "Bogota"})
        comprobar("registro de cliente → 201 + JWT", reg.status_code == 201)
        token_cliente = {"Authorization": f"Bearer {reg.json().get('access_token', '')}"}

        no_admin = c.get(f"{BASE_CLI}/clientes", headers=token_cliente)
        comprobar("cliente no lista a todos (403)", no_admin.status_code == 403,
                  f"({no_admin.status_code})")

        # --- CRUD de productos con caché ---
        sku = f"SMOKE-{uuid.uuid4().hex[:8]}"
        creado = c.post(f"{BASE_PROD}/productos", headers=admin,
                        json={"sku": sku, "nombre": "Monitor 27 pulgadas",
                              "categoria": "pantallas", "precio_cop": 890000})
        comprobar("POST /productos (admin) → 201", creado.status_code == 201,
                  f"({creado.status_code})")
        if creado.status_code != 201:
            print("    detalle:", creado.text[:300])
            return 1
        pid = creado.json()["id"]

        sin_token = c.post(f"{BASE_PROD}/productos",
                           json={"sku": "x", "nombre": "x", "categoria": "x",
                                 "precio_cop": 1})
        comprobar("POST /productos sin token → 401", sin_token.status_code == 401)

        # miss → BD → pueble (se observa la clave en el contenedor de Redis aparte)
        lectura = c.get(f"{BASE_PROD}/productos/{pid}")
        comprobar("GET /productos/{id} → 200", lectura.status_code == 200)
        comprobar("precio persistido", str(lectura.json()["precio_cop"]) in
                  ("890000", "890000.00"), f"({lectura.json()['precio_cop']})")

        actualizado = c.patch(f"{BASE_PROD}/productos/{pid}", headers=admin,
                              json={"precio_cop": 950000})
        comprobar("PATCH incrementa version",
                  actualizado.json().get("version") == 2,
                  f"(v{actualizado.json().get('version')})")

        cot = c.get(f"{BASE_PROD}/productos/{pid}/cotizacion",
                    headers={"Authorization": f"Bearer {token_servicio()}"})
        comprobar("cotización interna con token de servicio",
                  cot.status_code == 200 and str(cot.json()["precio_cop"]).startswith("950000"),
                  f"({cot.status_code})")

        cot_cliente = c.get(f"{BASE_PROD}/productos/{pid}/cotizacion",
                            headers=token_cliente)
        comprobar("cotización prohibida para rol cliente (403)",
                  cot_cliente.status_code == 403, f"({cot_cliente.status_code})")

        # --- importación CSV idempotente ---
        import io
        doc = f"I-{uuid.uuid4().hex[:8]}"
        filas = (f"documento_identidad,nombre,email,telefono,ciudad,activo\n"
                 f"{doc},Cliente Importado,importado-{uuid.uuid4().hex[:6]}@demo.local,,Bogota,true\n")
        i1 = c.post(f"{BASE_CLI}/clientes/import", headers=admin,
                    files={"file": ("clientes.csv", io.BytesIO(filas.encode()), "text/csv")})
        i2 = c.post(f"{BASE_CLI}/clientes/import", headers=admin,
                    files={"file": ("clientes.csv", io.BytesIO(filas.encode()), "text/csv")})
        comprobar("importación 1.ª → 1 insertado",
                  i1.status_code == 200 and i1.json()["insertados"] == 1,
                  f"({i1.json() if i1.status_code == 200 else i1.status_code})")
        comprobar("importación 2.ª idempotente (0 insertados, 0 actualizados)",
                  i2.status_code == 200 and i2.json()["insertados"] == 0
                  and i2.json()["actualizados"] == 0,
                  f"({i2.json() if i2.status_code == 200 else i2.status_code})")

    fallos = [p for p in PASOS if not p[1]]
    print(f"\n== resultado: {len(PASOS) - len(fallos)}/{len(PASOS)} comprobaciones OK ==")
    if fallos:
        for nombre, _, detalle in fallos:
            print(f"  FALTA: {nombre} {detalle}")
    return 1 if fallos else 0


if __name__ == "__main__":
    sys.exit(main())
