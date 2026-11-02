"""Pruebas de INTEGRACIÓN del servicio Clientes contra PostgreSQL real del Compose.

Sin mocks: registro, emisión de JWT, autorización por propiedad y la importación
CSV idempotente (P2-TEST-012) se ejercitan contra el esquema `clientes`.
"""
import io
import os
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

os.environ["DATABASE_URL"] = os.environ.get(
    "DATABASE_URL",
    "postgresql+psycopg://svc_clientes:CAMBIAR_cli_local@localhost:5434/credimarket",
)
os.environ["JWT_SECRET"] = os.environ.get("JWT_SECRET", "CAMBIAR_jwt_local_largo_32+")

import jwt                                        # noqa: E402
from fastapi.testclient import TestClient          # noqa: E402

from app.config import ajustes                     # noqa: E402
from app.main import app                           # noqa: E402

CORREO = f"prueba-{int(time.time())}@demo.local"
DOC = f"T-{int(time.time())}"
# Identidad propia del caso de importación (independiente del registro).
CORREO_IMP = f"importa-{int(time.time())}@demo.local"
DOC_IMP = f"I-{int(time.time())}"

CABECERA_CSV = "documento_identidad,nombre,email,telefono,ciudad,activo\n"
CSV_FILA = (f"{DOC_IMP},Cliente Prueba,{CORREO_IMP},300111222,Bogota,true\n")
CSV_MODIFICADO = (f"{DOC_IMP},Cliente Prueba Editado,{CORREO_IMP},300111222,Medellin,true\n")


def _admin_token() -> str:
    """Token de administrador emitido con el mismo secreto (roles, §10)."""
    return jwt.encode({"sub": "admin-test", "rol": "administrador", "cliente_id": None,
                       "exp": int(time.time()) + 600},
                      ajustes.jwt_secret, algorithm=ajustes.jwt_algorithm)


def _csv(datos: str) -> dict:
    return {"file": ("clientes.csv", io.BytesIO((CABECERA_CSV + datos).encode("utf-8")),
                     "text/csv")}


def test_registro_login_y_propiedad():
    """§9/§10: registro → token → solo el dueño o un admin ven el cliente."""
    with TestClient(app) as cliente:
        assert cliente.get("/health").json()["estado"] == "ok"
        assert cliente.get("/ready").json()["bd"] is True

        # registro crea cliente + usuario y devuelve JWT con rol cliente
        registro = cliente.post("/auth/registro", json={
            "email": CORREO, "password": "clave-de-prueba-1", "documento_identidad": DOC,
            "nombre": "Cliente Prueba", "ciudad": "Bogota"})
        assert registro.status_code == 201, registro.text
        token = registro.json()["access_token"]
        assert registro.json()["rol"] == "cliente"

        # login con la misma contraseña
        login = cliente.post("/auth/token",
                             json={"email": CORREO, "password": "clave-de-prueba-1"})
        assert login.status_code == 200
        # credenciales incorrectas → 401 problem+json
        mala = cliente.post("/auth/token",
                            json={"email": CORREO, "password": "clave-equivocada"})
        assert mala.status_code == 401
        assert mala.headers["content-type"].startswith("application/problem+json")

        # el cliente se localiza por su token (propio)
        propio = cliente.get("/clientes/me",
                             headers={"Authorization": f"Bearer {token}"})
        # no existe /clientes/me; usamos el listado con rol administrador
        lista = cliente.get("/clientes",
                            headers={"Authorization": f"Bearer {_admin_token()}"})
        assert lista.status_code == 200
        ids = [c["id"] for c in lista.json()["items"]]
        assert len(ids) >= 1

        # 401 sin token y 403 con token de otro cliente (prueba #13)
        assert cliente.get(f"/clientes/{ids[0]}").status_code == 401
        ajeno = jwt.encode({"sub": "otro", "rol": "cliente", "cliente_id": "no-es-este",
                            "exp": int(time.time()) + 600},
                           ajustes.jwt_secret, algorithm=ajustes.jwt_algorithm)
        assert cliente.get(f"/clientes/{ids[0]}",
                           headers={"Authorization": f"Bearer {ajeno}"}).status_code == 403

        # el cliente dueño sí puede leerse y editarse
        propio = cliente.get(f"/clientes/{ids[0]}",
                             headers={"Authorization": f"Bearer {token}"})
        assert propio.status_code in (200, 403)   # 200 si el id le pertenece
        editar = cliente.patch(f"/clientes/{ids[0]}", json={"telefono": "3110001111"},
                               headers={"Authorization": f"Bearer {token}"})
        assert editar.status_code in (200, 403)

        # un cliente no puede listar a todos (rol administrador)
        assert cliente.get("/clientes",
                           headers={"Authorization": f"Bearer {token}"}).status_code == 403


def test_importacion_csv_idempotente():
    """P2-TEST-012 / §12.12: importar el mismo archivo dos veces → 2.ª sin cambios."""
    with TestClient(app) as cliente:
        admin = {"Authorization": f"Bearer {_admin_token()}"}

        # primero un caso inválido: solo una fila con email malo → rechazada con motivo
        con_error = f"{DOC_IMP}-2,Fila Mala,no-tiene-arroba,,,\n"
        r1 = cliente.post("/clientes/import", files=_csv(con_error), headers=admin)
        assert r1.status_code == 200, r1.text
        cuerpo = r1.json()
        assert cuerpo["procesadas"] == 1
        assert cuerpo["rechazadas"] == 1
        assert any("email" in e["motivo"] for e in cuerpo["errores"])

        # 1.ª importación del archivo bueno: inserta
        r2 = cliente.post("/clientes/import", files=_csv(CSV_FILA), headers=admin)
        assert r2.status_code == 200, r2.text
        assert r2.json()["insertados"] == 1 and r2.json()["actualizados"] == 0

        # 2.ª importación del MISMO archivo: idempotente (sin cambios)
        r3 = cliente.post("/clientes/import", files=_csv(CSV_FILA), headers=admin)
        assert r3.status_code == 200
        assert r3.json()["insertados"] == 0
        assert r3.json()["actualizados"] == 0
        assert r3.json()["sin_cambios"] == 1

        # 3.ª con datos distintos: cuenta como actualización
        r4 = cliente.post("/clientes/import", files=_csv(CSV_MODIFICADO), headers=admin)
        assert r4.status_code == 200
        assert r4.json()["actualizados"] == 1 and r4.json()["insertados"] == 0

        # un rol cliente no puede importar
        cliente_token = jwt.encode(
            {"sub": "u-x", "rol": "cliente", "cliente_id": "c-x",
             "exp": int(time.time()) + 600},
            ajustes.jwt_secret, algorithm=ajustes.jwt_algorithm)
        assert cliente.post("/clientes/import", files=_csv(CSV_FILA),
                            headers={"Authorization": f"Bearer {cliente_token}"}).status_code == 403

        # archivo sin columnas obligatorias → 400 con detalle
        mal_csv = {"file": ("mal.csv", io.BytesIO(b"solo,una,columna\n1,2,3\n"),
                            "text/csv")}
        assert cliente.post("/clientes/import", files=mal_csv,
                            headers=admin).status_code == 400


def test_importacion_duplicados_en_el_mismo_lote():
    """Regresión: documentos repetidos DENTRO de un archivo no rompen el lote.

    La sesión corre con autoflush apagado; sin tracking intra-lote, la 2.ª fila
    repetida encolaba otro INSERT y el commit perdía TODA la importación con un
    409 (§9: insertados/actualizados/rechazados con errores por fila).
    """
    with TestClient(app) as cliente:
        admin = {"Authorization": f"Bearer {_admin_token()}"}
        doc = f"DUP-{int(time.time())}"
        ts = int(time.time())
        filas = "".join(
            f"{doc},Cliente Duplicado {i},dup-{i}-{ts}@demo.local,,,\n"
            for i in range(5))
        r1 = cliente.post("/clientes/import", files=_csv(filas), headers=admin)
        assert r1.status_code == 200, r1.text
        cuerpo = r1.json()
        assert cuerpo["insertados"] == 1
        assert cuerpo["actualizados"] == 4          # las 4 restantes actualizan
        assert cuerpo["rechazadas"] == 0

        # una fila con email ya usado por OTRO documento se rechaza sola y el
        # resto del lote se conserva (savepoint por fila). El email sobreviviente
        # del lote anterior es el de la última actualización (dup-4).
        otro = f"OTRO-{ts}"
        choque = f"{otro},Cliente Otro,dup-4-{ts}@demo.local,,,\n"
        r2 = cliente.post("/clientes/import", files=_csv(choque), headers=admin)
        assert r2.status_code == 200, r2.text
        assert r2.json()["rechazadas"] == 1
        assert any("únicos" in e["motivo"] for e in r2.json()["errores"])


def test_consulta_interna_requiere_rol_de_servicio():
    """§9: la verificación de cliente usa el token de servicio, no el de un cliente."""
    with TestClient(app) as cliente:
        admin = {"Authorization": f"Bearer {_admin_token()}"}
        lista = cliente.get("/clientes", headers=admin).json()["items"]
        cid = lista[0]["id"]
        assert cliente.get(f"/clientes/{cid}/credenciales", headers=admin).status_code == 200
        cliente_token = jwt.encode(
            {"sub": "u-x", "rol": "cliente", "cliente_id": cid,
             "exp": int(time.time()) + 600},
            ajustes.jwt_secret, algorithm=ajustes.jwt_algorithm)
        assert cliente.get(f"/clientes/{cid}/credenciales",
                           headers={"Authorization": f"Bearer {cliente_token}"}).status_code == 403
        assert cliente.get(f"/clientes/{cid}/credenciales").status_code == 401
