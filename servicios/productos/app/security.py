"""Control de acceso: JWT compartido (P2-DEC-012) y problem+json (RFC 9457)."""
import time
from typing import Callable

import jwt
from fastapi import Depends, HTTPException, Request
from fastapi.responses import JSONResponse

from .config import ajustes

# Fallback acotado en memoria: solo se usa mientras Redis no responde (P2-TEST-008).
_MEMORIA: dict[str, tuple[float, str]] = {}


def problema(status: int, titulo: str, detalle: str, instance: str, errores=None) -> JSONResponse:
    cuerpo = {
        "type": "about:blank",
        "title": titulo,
        "status": status,
        "detail": detalle,
        "instance": instance,
    }
    if errores:
        cuerpo["errors"] = errores
    return JSONResponse(status_code=status, content=cuerpo, media_type="application/problem+json")


def obtener_token(request: Request) -> str | None:
    cabecera = request.headers.get("Authorization", "")
    if cabecera.lower().startswith("bearer "):
        return cabecera[7:].strip()
    return None


def decodificar_token(token: str) -> dict:
    return jwt.decode(token, ajustes.jwt_secret, algorithms=[ajustes.jwt_algorithm])


def requiere_rol(*roles: str) -> Callable:
    """Dependencia: valida firma, expiración y rol del JWT."""

    def dependencia(request: Request) -> dict:
        token = obtener_token(request)
        if not token:
            raise HTTPException(
                status_code=401,
                detail={"title": "No autenticado", "status": 401, "detail": "falta el token"},
                headers={"WWW-Authenticate": "Bearer"},
            )
        try:
            datos = decodificar_token(token)
        except jwt.ExpiredSignatureError:
            raise HTTPException(
                status_code=401,
                detail={"title": "Sesión vencida", "status": 401, "detail": "el token expiró"},
                headers={"WWW-Authenticate": "Bearer"},
            )
        except jwt.InvalidTokenError:
            raise HTTPException(
                status_code=401,
                detail={"title": "Token inválido", "status": 401, "detail": "firma no válida"},
                headers={"WWW-Authenticate": "Bearer"},
            )
        rol = datos.get("rol")
        if roles and rol not in roles:
            raise HTTPException(
                status_code=403,
                detail={"title": "Prohibido", "status": 403, "detail": f"rol '{rol}' insuficiente"},
            )
        return datos

    return dependencia


rol_administrador = requiere_rol("administrador")
rol_interno = requiere_rol("administrador", "servicio")


def memoria_puesta(clave: str, valor: str, ttl: int) -> None:
    """Guarda en el fallback local (solo acotado, con expiración)."""
    if len(_MEMORIA) >= ajustes.fallback_max_entradas:
        _MEMORIA.clear()
    _MEMORIA[clave] = (time.monotonic() + ttl, valor)


def memoria_leida(clave: str) -> str | None:
    entrada = _MEMORIA.get(clave)
    if not entrada:
        return None
    expira, valor = entrada
    if time.monotonic() > expira:
        _MEMORIA.pop(clave, None)
        return None
    return valor


def memoria_borrada(clave: str) -> None:
    _MEMORIA.pop(clave, None)


def memoria_vacia() -> None:
    _MEMORIA.clear()
