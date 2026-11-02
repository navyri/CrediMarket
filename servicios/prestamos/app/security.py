"""Control de acceso del servicio Préstamos: mismo JWT compartido (P2-DEC-012)."""
from fastapi import Depends, HTTPException, Request

import jwt

from .config import ajustes


def obtener_token(request: Request) -> str | None:
    cabecera = request.headers.get("Authorization", "")
    if cabecera.lower().startswith("bearer "):
        return cabecera[7:].strip()
    return None


def requiere_rol(*roles: str):
    def dependencia(request: Request) -> dict:
        token = obtener_token(request)
        if not token:
            raise HTTPException(status_code=401,
                                detail={"title": "No autenticado", "status": 401,
                                        "detail": "falta el token"},
                                headers={"WWW-Authenticate": "Bearer"})
        try:
            datos = jwt.decode(token, ajustes.jwt_secret,
                               algorithms=[ajustes.jwt_algorithm])
        except jwt.ExpiredSignatureError:
            raise HTTPException(status_code=401,
                                detail={"title": "Sesión vencida", "status": 401,
                                        "detail": "el token expiró"},
                                headers={"WWW-Authenticate": "Bearer"})
        except jwt.InvalidTokenError:
            raise HTTPException(status_code=401,
                                detail={"title": "Token inválido", "status": 401,
                                        "detail": "firma no válida"},
                                headers={"WWW-Authenticate": "Bearer"})
        if roles and datos.get("rol") not in roles:
            raise HTTPException(status_code=403,
                                detail={"title": "Prohibido", "status": 403,
                                        "detail": f"rol '{datos.get('rol')}' insuficiente"})
        return datos

    return dependencia


def autenticado(request: Request) -> dict | None:
    """Token opcional: devuelve los datos si es válido, None si no lo hay."""
    if not obtener_token(request):
        return None
    try:
        return jwt.decode(obtener_token(request), ajustes.jwt_secret,
                          algorithms=[ajustes.jwt_algorithm])
    except jwt.InvalidTokenError:
        return None


def exigir_dueno_o_admin(datos: dict, cliente_id: str, instancia: str) -> None:
    """§10: un cliente solo ve lo suyo; 403 en caso contrario (prueba #13)."""
    if datos.get("rol") == "administrador":
        return
    if datos.get("cliente_id") != cliente_id:
        raise HTTPException(status_code=403,
                            detail={"title": "Prohibido", "status": 403,
                                    "detail": "préstamo perteneciente a otro cliente",
                                    "instance": instancia})


rol_administrador = requiere_rol("administrador")
rol_interno = requiere_rol("administrador", "servicio")
# Para crear un préstamo: un cliente (dueño) o un administrador en su nombre.
rol_cliente_o_admin = requiere_rol("cliente", "administrador")


def token_de_servicio() -> str:
    """JWT de uso interno (rol `servicio`) para llamar a Clientes y Productos.

    Firmado con el MISMO secreto (P2-DEC-012); nunca se emite a usuarios.
    """
    import time
    return jwt.encode({"sub": "prestamos", "rol": "servicio", "cliente_id": None,
                       "exp": int(time.time()) + 600},
                      ajustes.jwt_secret, algorithm=ajustes.jwt_algorithm)
