"""Rutas REST del servicio Productos (contrato en docs/arquitectura/contratos-rest.md)."""
from decimal import Decimal

from fastapi import APIRouter, Depends, Query, Request
from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from . import cache, estadisticas
from .db import obtener_sesion
from .models import Producto
from .schemas import (
    Cotizacion,
    ProductoActualizacion,
    ProductoCreacion,
    ProductoLectura,
    ProductoLista,
)
from .security import problema, rol_administrador, rol_interno

router = APIRouter()


def _datos_cache(producto: Producto) -> dict:
    return {
        "id": producto.id,
        "sku": producto.sku,
        "nombre": producto.nombre,
        "categoria": producto.categoria,
        "descripcion": producto.descripcion,
        "precio_cop": str(producto.precio_cop),
        "activo": producto.activo,
        "version": producto.version,
        "creado_en": producto.creado_en.isoformat(),
        "actualizado_en": producto.actualizado_en.isoformat(),
    }


def _de_cache(datos: dict) -> ProductoLectura:
    return ProductoLectura(
        id=datos["id"],
        sku=datos["sku"],
        nombre=datos["nombre"],
        categoria=datos["categoria"],
        descripcion=datos.get("descripcion"),
        precio_cop=Decimal(datos["precio_cop"]),
        activo=datos["activo"],
        version=datos["version"],
        creado_en=datos["creado_en"],
        actualizado_en=datos["actualizado_en"],
    )


@router.get("/productos", response_model=ProductoLista)
def listar_productos(
    categoria: str | None = None,
    solo_activos: bool = True,
    pagina: int = Query(1, ge=1),
    tamano: int = Query(20, ge=1, le=100),
    sesion: Session = Depends(obtener_sesion),
):
    consulta = select(Producto)
    conteo = select(func.count()).select_from(Producto)
    if categoria:
        consulta = consulta.where(Producto.categoria == categoria)
        conteo = conteo.where(Producto.categoria == categoria)
    if solo_activos:
        consulta = consulta.where(Producto.activo.is_(True))
        conteo = conteo.where(Producto.activo.is_(True))
    total = sesion.scalar(conteo) or 0
    items = (
        sesion.scalars(
            consulta.order_by(Producto.creado_en).offset((pagina - 1) * tamano).limit(tamano)
        ).all()
    )
    return ProductoLista(
        total=total,
        pagina=pagina,
        tamano=tamano,
        items=[ProductoLectura.model_validate(i) for i in items],
    )


@router.get("/productos/{producto_id}", response_model=ProductoLectura)
def obtener_producto(producto_id: str, sesion: Session = Depends(obtener_sesion)):
    # 1) Intento de caché (hit → respuesta directa).
    datos = cache.leer(producto_id)
    if datos is not None:
        return _de_cache(datos)
    # 2) Miss → BD → pueble con TTL.
    producto = sesion.get(Producto, producto_id)
    if producto is None:
        return problema(404, "Recurso no encontrado", f"producto {producto_id} no existe",
                        f"/productos/{producto_id}")
    cache.escribir(producto_id, _datos_cache(producto))
    return ProductoLectura.model_validate(producto)


@router.post("/productos", response_model=ProductoLectura, status_code=201)
def crear_producto(
    cuerpo: ProductoCreacion,
    request: Request,
    sesion: Session = Depends(obtener_sesion),
    _auth: dict = Depends(rol_administrador),
):
    producto = Producto(**cuerpo.model_dump())
    sesion.add(producto)
    try:
        sesion.commit()
    except IntegrityError:
        sesion.rollback()
        return problema(409, "Conflicto", f"ya existe un producto con sku {cuerpo.sku}",
                        str(request.url.path))
    sesion.refresh(producto)
    return ProductoLectura.model_validate(producto)


@router.patch("/productos/{producto_id}", response_model=ProductoLectura)
def actualizar_producto(
    producto_id: str,
    cuerpo: ProductoActualizacion,
    request: Request,
    sesion: Session = Depends(obtener_sesion),
    _auth: dict = Depends(rol_administrador),
):
    producto = sesion.get(Producto, producto_id)
    if producto is None:
        return problema(404, "Recurso no encontrado", f"producto {producto_id} no existe",
                        str(request.url.path))
    cambios = cuerpo.model_dump(exclude_unset=True)
    if not cambios:
        return problema(400, "Solicitud inválida", "sin campos que actualizar",
                        str(request.url.path))
    for campo, valor in cambios.items():
        setattr(producto, campo, valor)
    producto.version += 1
    sesion.commit()                       # commit primero (§6)
    sesion.refresh(producto)
    cache.invalidar(producto_id)          # invalidación tras commit (§6)
    return ProductoLectura.model_validate(producto)


@router.post("/productos/{producto_id}/desactivar", response_model=ProductoLectura)
def desactivar_producto(
    producto_id: str,
    request: Request,
    sesion: Session = Depends(obtener_sesion),
    _auth: dict = Depends(rol_administrador),
):
    producto = sesion.get(Producto, producto_id)
    if producto is None:
        return problema(404, "Recurso no encontrado", f"producto {producto_id} no existe",
                        str(request.url.path))
    producto.activo = False
    producto.version += 1
    sesion.commit()
    sesion.refresh(producto)
    cache.invalidar(producto_id)
    return ProductoLectura.model_validate(producto)


@router.get("/productos/{producto_id}/cotizacion", response_model=Cotizacion)
def cotizar_producto(
    producto_id: str,
    request: Request,
    sesion: Session = Depends(obtener_sesion),
    _auth: dict = Depends(rol_interno),
):
    """Fuente de verdad para Préstamos: lee SIEMPRE de BD, nunca de Redis (§6)."""
    producto = sesion.get(Producto, producto_id)
    if producto is None:
        return problema(404, "Recurso no encontrado", f"producto {producto_id} no existe",
                        str(request.url.path))
    if not producto.activo:
        return problema(409, "Producto inactivo",
                        f"producto {producto_id} no admite nuevas operaciones",
                        str(request.url.path))
    return Cotizacion(
        producto_id=producto.id,
        precio_cop=producto.precio_cop,
        version=producto.version,
        vigente_desde=producto.actualizado_en,
    )


@router.get("/cache/estadisticas")
def estadisticas_cache(_auth: dict = Depends(rol_administrador)):
    """Hit-rate, fallback y latencia p50/p95 de Redis (§6, P2-TEST-019).

    Métricas de observación del proceso actual: demuestran que el cache-aside
    funciona y que la caché degrada a memoria local sin bloquear lecturas.
    """
    resumen = estadisticas.resumen()
    resumen["redis_disponible"] = cache.redis_esta_disponible()
    return resumen
