"""Control de acceso del servicio Inventario: mismo JWT compartido (P2-DEC-012)."""
from fastapi import Depends, HTTPException, Request

from .config import ajustes

import jwt


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


rol_administrador = requiere_rol("administrador")
rol_interno = requiere_rol("administrador", "servicio")
