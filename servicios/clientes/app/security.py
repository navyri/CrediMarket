"""Autenticación del sistema CrediMarket (P2-DEC-012): JWT emitido en Clientes.

La emisión vive en este servicio (dueño de `usuario`), sin crear un quinto
servicio (§9). bcrypt hashea las contraseñas; ningún secreto se versiona.
"""
import time

import bcrypt
import jwt
from fastapi import Depends, HTTPException, Request
from sqlalchemy import select
from sqlalchemy.orm import Session

from .config import ajustes
from .db import obtener_sesion
from .models import Cliente, Usuario


def hash_password(password: str) -> str:
    return bcrypt.hashpw(password.encode("utf-8"), bcrypt.gensalt()).decode("utf-8")


def verificar_password(password: str, hash_guardado: str) -> bool:
    try:
        return bcrypt.checkpw(password.encode("utf-8"), hash_guardado.encode("utf-8"))
    except ValueError:
        return False


def emitir_token(usuario: Usuario) -> dict:
    exp = int(time.time()) + ajustes.jwt_exp_min * 60
    payload = {
        "sub": usuario.id,
        "email": usuario.email,
        "cliente_id": usuario.cliente_id,
        "rol": usuario.rol,
        "exp": exp,
    }
    token = jwt.encode(payload, ajustes.jwt_secret, algorithm=ajustes.jwt_algorithm)
    return {"access_token": token, "token_type": "bearer", "rol": usuario.rol,
            "cliente_id": usuario.cliente_id, "exp": exp}


def obtener_token(request: Request) -> str | None:
    cabecera = request.headers.get("Authorization", "")
    if cabecera.lower().startswith("bearer "):
        return cabecera[7:].strip()
    return None


def _datos_token(request: Request) -> dict:
    token = obtener_token(request)
    if not token:
        raise HTTPException(status_code=401,
                            detail={"title": "No autenticado", "status": 401,
                                    "detail": "falta el token"},
                            headers={"WWW-Authenticate": "Bearer"})
    try:
        return jwt.decode(token, ajustes.jwt_secret, algorithms=[ajustes.jwt_algorithm])
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


def requiere_rol(*roles: str):
    def dependencia(request: Request) -> dict:
        datos = _datos_token(request)
        if roles and datos.get("rol") not in roles:
            raise HTTPException(status_code=403,
                                detail={"title": "Prohibido", "status": 403,
                                        "detail": f"rol '{datos.get('rol')}' insuficiente"})
        return datos

    return dependencia


rol_administrador = requiere_rol("administrador")
# Uso interno: el token de servicio (rol `servicio`) o un administrador.
rol_interno = requiere_rol("administrador", "servicio")


def autenticado(request: Request) -> dict | None:
    """Token opcional: devuelve los datos si es válido, None si no lo hay."""
    if not obtener_token(request):
        return None
    return _datos_token(request)


def exigir_dueno_o_admin(datos: dict, cliente_id: str, instancia: str) -> None:
    """§10: un cliente solo ve lo suyo; 403 en caso contrario (prueba #13)."""
    if datos.get("rol") == "administrador":
        return
    if datos.get("cliente_id") != cliente_id:
        raise HTTPException(status_code=403,
                            detail={"title": "Prohibido", "status": 403,
                                    "detail": "recurso perteneciente a otro cliente",
                                    "instance": instancia})


def usuario_por_email(sesion: Session, email: str) -> Usuario | None:
    return sesion.scalar(select(Usuario).where(Usuario.email == email.lower()))


def cliente_por_documento(sesion: Session, documento: str) -> Cliente | None:
    return sesion.scalar(select(Cliente).where(Cliente.documento_identidad == documento))
