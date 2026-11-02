"""Rutas REST del servicio Clientes (contrato en docs/arquitectura/contratos-rest.md)."""
import csv
import io
import re

from fastapi import APIRouter, Depends, File, Request, UploadFile
from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from .db import obtener_sesion
from .models import Cliente, Usuario
from .schemas import (
    ClienteActualizacion,
    ClienteCreacion,
    ClienteLectura,
    ClienteLista,
    ErrorImportacion,
    Login,
    Registro,
    ResultadoImportacion,
    Token,
)
from .security import (
    autenticado,
    cliente_por_documento,
    emitir_token,
    exigir_dueno_o_admin,
    hash_password,
    rol_administrador,
    rol_interno,
    usuario_por_email,
    verificar_password,
)

router = APIRouter()

# Columnas admitidas en la importación (§9: "pueden adaptar los campos").
COLUMNAS_OBLIGATORIAS = {"documento_identidad", "nombre", "email"}
COLUMNAS_OPCIONALES = {"telefono", "ciudad", "activo"}
# Perfil financiero del cliente (P2-7): adaptado del histórico; opcional.
COLUMNAS_PERFIL = {
    "ingresos_mensuales_cop", "obligaciones_mensuales_cop", "tipo_empleo",
    "antiguedad_laboral_meses", "meses_historial_crediticio",
    "creditos_previos", "atrasos_previos_30d", "porcentaje_pago_puntual",
}
COLUMNAS_CONOCIDAS = COLUMNAS_OBLIGATORIAS | COLUMNAS_OPCIONALES | COLUMNAS_PERFIL
# Tipos numéricos del perfil: None si el valor está vacío (dato faltante
# legítimo; el imputador del pipeline lo absorbe en inferencia, §8.B).
PERFIL_NUMERICO = {
    "ingresos_mensuales_cop": float, "obligaciones_mensuales_cop": float,
    "antiguedad_laboral_meses": float, "meses_historial_crediticio": float,
    "creditos_previos": int, "atrasos_previos_30d": int,
    "porcentaje_pago_puntual": float,
}
_RE_EMAIL = re.compile(r"[^@\s]+@[^@\s]+\.[^@\s]+$")


def _perfil_de_fila(fila: dict) -> tuple[dict, str | None]:
    """Extrae y valida el perfil financiero de una fila CSV.

    Devuelve (perfil, motivo_de_rechazo). Un valor vacío se vuelve None;
    un valor no numérico rechaza la fila (no se inventa información).
    """
    perfil: dict = {}
    for columna, convertidor in PERFIL_NUMERICO.items():
        crudo = (fila.get(columna) or "").strip()
        if not crudo:
            perfil[columna] = None
            continue
        try:
            perfil[columna] = convertidor(float(crudo))
        except (ValueError, OverflowError):
            return {}, f"{columna} no numérico: {crudo!r}"
    perfil["tipo_empleo"] = (fila.get("tipo_empleo") or "").strip().lower() or None
    if perfil.get("tipo_empleo") and len(perfil["tipo_empleo"]) > 40:
        return {}, f"tipo_empleo excede 40 caracteres: {perfil['tipo_empleo']!r}"
    return perfil, None


def _problema(status: int, titulo: str, detalle: str, instance: str, errores=None):
    from fastapi.responses import JSONResponse
    cuerpo = {"type": "about:blank", "title": titulo, "status": status,
              "detail": detalle, "instance": instance}
    if errores:
        cuerpo["errors"] = errores
    return JSONResponse(status_code=status, content=cuerpo,
                        media_type="application/problem+json")


# ---------------------------------------------------------------- autenticación
@router.post("/auth/registro", response_model=Token, status_code=201)
def registrar(cuerpo: Registro, request: Request, sesion: Session = Depends(obtener_sesion)):
    if usuario_por_email(sesion, cuerpo.email):
        return _problema(409, "Conflicto", "el email ya está registrado",
                         str(request.url.path))
    if cliente_por_documento(sesion, cuerpo.documento_identidad):
        return _problema(409, "Conflicto", "el documento ya está registrado",
                         str(request.url.path))
    cliente = Cliente(documento_identidad=cuerpo.documento_identidad, nombre=cuerpo.nombre,
                      email=cuerpo.email.lower(), telefono=cuerpo.telefono,
                      ciudad=cuerpo.ciudad, activo=True)
    sesion.add(cliente)
    sesion.flush()
    usuario = Usuario(email=cuerpo.email.lower(), password_hash=hash_password(cuerpo.password),
                      rol="cliente", cliente_id=cliente.id)
    sesion.add(usuario)
    try:
        sesion.commit()
    except IntegrityError:
        sesion.rollback()
        return _problema(409, "Conflicto", "registro duplicado", str(request.url.path))
    sesion.refresh(usuario)
    return emitir_token(usuario)


@router.post("/auth/token", response_model=Token)
def token(cuerpo: Login, request: Request, sesion: Session = Depends(obtener_sesion)):
    usuario = usuario_por_email(sesion, cuerpo.email)
    if usuario is None or not verificar_password(cuerpo.password, usuario.password_hash):
        return _problema(401, "No autenticado", "credenciales inválidas",
                         str(request.url.path),
                         [{"campo": "email/password", "mensaje": "no coinciden"}])
    if usuario.cliente_id:
        cliente = sesion.get(Cliente, usuario.cliente_id)
        if cliente is not None and not cliente.activo:
            return _problema(403, "Prohibido", "cliente inactivo", str(request.url.path))
    return emitir_token(usuario)


# ----------------------------------------------------------------------- CRUD
@router.post("/clientes", response_model=ClienteLectura, status_code=201)
def crear_cliente(cuerpo: ClienteCreacion, request: Request,
                  sesion: Session = Depends(obtener_sesion),
                  _auth: dict = Depends(rol_administrador)):
    if usuario_por_email(sesion, cuerpo.email):
        return _problema(409, "Conflicto", "el email ya está registrado",
                         str(request.url.path))
    cliente = Cliente(**{k: v for k, v in cuerpo.model_dump().items()})
    sesion.add(cliente)
    try:
        sesion.commit()
    except IntegrityError:
        sesion.rollback()
        return _problema(409, "Conflicto", "documento o email ya existentes",
                         str(request.url.path))
    sesion.refresh(cliente)
    return ClienteLectura.model_validate(cliente)


@router.get("/clientes", response_model=ClienteLista)
def listar_clientes(pagina: int = 1, tamano: int = 50,
                    sesion: Session = Depends(obtener_sesion),
                    _auth: dict = Depends(rol_administrador)):
    total = sesion.scalar(select(func.count()).select_from(Cliente)) or 0
    items = sesion.scalars(select(Cliente).order_by(Cliente.creado_en)
                           .offset((pagina - 1) * tamano).limit(tamano)).all()
    return ClienteLista(total=total,
                        items=[ClienteLectura.model_validate(i) for i in items])


@router.get("/clientes/{cliente_id}", response_model=ClienteLectura)
def obtener_cliente(cliente_id: str, request: Request,
                    sesion: Session = Depends(obtener_sesion),
                    datos: dict = Depends(autenticado)):
    if datos is None:
        return _problema(401, "No autenticado", "falta el token", str(request.url.path))
    cliente = sesion.get(Cliente, cliente_id)
    if cliente is None:
        return _problema(404, "Recurso no encontrado", f"cliente {cliente_id} no existe",
                         str(request.url.path))
    exigir_dueno_o_admin(datos, cliente.id, str(request.url.path))
    return ClienteLectura.model_validate(cliente)


@router.patch("/clientes/{cliente_id}", response_model=ClienteLectura)
def actualizar_cliente(cliente_id: str, cuerpo: ClienteActualizacion, request: Request,
                       sesion: Session = Depends(obtener_sesion),
                       datos: dict = Depends(autenticado)):
    if datos is None:
        return _problema(401, "No autenticado", "falta el token", str(request.url.path))
    cliente = sesion.get(Cliente, cliente_id)
    if cliente is None:
        return _problema(404, "Recurso no encontrado", f"cliente {cliente_id} no existe",
                         str(request.url.path))
    exigir_dueno_o_admin(datos, cliente.id, str(request.url.path))
    cambios = cuerpo.model_dump(exclude_unset=True)
    if not cambios:
        return _problema(400, "Solicitud inválida", "sin campos que actualizar",
                         str(request.url.path))
    if "activo" in cambios and datos.get("rol") != "administrador":
        return _problema(403, "Prohibido", "solo un administrador activa o desactiva",
                         str(request.url.path))
    for campo, valor in cambios.items():
        setattr(cliente, campo, valor)
    sesion.commit()
    sesion.refresh(cliente)
    return ClienteLectura.model_validate(cliente)


# ------------------------------------------------------------ importación CSV
def _validar_fila(fila: dict) -> str | None:
    """Devuelve el motivo de rechazo o None si la fila es válida."""
    documento = (fila.get("documento_identidad") or "").strip()
    nombre = (fila.get("nombre") or "").strip()
    email = (fila.get("email") or "").strip().lower()
    if not documento:
        return "documento_identidad vacío"
    if len(documento) > 30:
        return "documento_identidad excede 30 caracteres"
    if not nombre:
        return "nombre vacío"
    if not _RE_EMAIL.match(email):
        return f"email inválido: {email!r}"
    activo = (fila.get("activo") or "true").strip().lower()
    if activo not in ("true", "false", "1", "0", "si", "no"):
        return f"activo inválido: {activo!r}"
    return None


def _mismos_datos(cliente: Cliente, fila: dict, perfil: dict) -> bool:
    activo = (fila.get("activo") or "true").strip().lower() in ("true", "1", "si")
    if not (
        cliente.nombre == fila["nombre"].strip()
        and cliente.email == fila["email"].strip().lower()
        and (cliente.telefono or "") == (fila.get("telefono") or "").strip()
        and (cliente.ciudad or "") == (fila.get("ciudad") or "").strip()
        and cliente.activo == activo
    ):
        return False
    # El perfil también debe coincidir: una fila con perfil distinto actualiza.
    for campo, valor in perfil.items():
        actual = getattr(cliente, campo)
        if valor is None:
            if actual is not None:
                return False
        elif campo == "tipo_empleo":
            if actual != valor:
                return False
        elif actual is None or abs(float(actual) - float(valor)) > 1e-6:
            return False
    return True


@router.post("/clientes/import", response_model=ResultadoImportacion)
def importar_clientes(request: Request, file: UploadFile = File(...),
                      sesion: Session = Depends(obtener_sesion),
                      _auth: dict = Depends(rol_administrador)):
    """Importación idempotente (§9, P2-TEST-012): clave = documento_identidad."""
    nombre_archivo = file.filename or "clientes.csv"
    if not nombre_archivo.lower().endswith(".csv"):
        return _problema(400, "Solicitud inválida", "se espera un archivo .csv",
                         str(request.url.path))
    contenido = file.file.read()
    try:
        texto = contenido.decode("utf-8-sig")
    except UnicodeDecodeError:
        return _problema(400, "Solicitud inválida", "el archivo debe estar en UTF-8",
                         str(request.url.path))

    lector = csv.DictReader(io.StringIO(texto))
    if not lector.fieldnames:
        return _problema(400, "Solicitud inválida", "archivo sin cabecera",
                         str(request.url.path))
    campos = {c.strip().lower() for c in lector.fieldnames}
    faltantes = COLUMNAS_OBLIGATORIAS - campos
    if faltantes:
        return _problema(400, "Solicitud inválida",
                         f"faltan columnas obligatorias: {sorted(faltantes)}",
                         str(request.url.path))
    desconocidas = campos - COLUMNAS_CONOCIDAS
    if desconocidas:
        return _problema(400, "Solicitud inválida",
                         f"columnas no reconocidas: {sorted(desconocidas)}",
                         str(request.url.path))

    procesadas = insertados = actualizados = sin_cambios = rechazadas = 0
    errores: list[ErrorImportacion] = []

    for indice, fila_bruta in enumerate(lector, start=2):   # fila 1 = cabecera
        fila = {(k or "").strip().lower(): (v or "").strip()
                for k, v in fila_bruta.items() if k is not None}
        procesadas += 1
        motivo = _validar_fila(fila)
        if not motivo:
            perfil, motivo = _perfil_de_fila(fila)
        if motivo:
            rechazadas += 1
            errores.append(ErrorImportacion(fila=indice, motivo=motivo))
            continue

        existente = cliente_por_documento(sesion, fila["documento_identidad"])
        if existente is None:
            nuevo = Cliente(
                documento_identidad=fila["documento_identidad"],
                nombre=fila["nombre"],
                email=fila["email"].lower(),
                telefono=fila.get("telefono") or None,
                ciudad=fila.get("ciudad") or None,
                activo=(fila.get("activo", "true").lower() in ("true", "1", "si")),
                **perfil,
            )
            sesion.add(nuevo)
            insertados += 1
        elif _mismos_datos(existente, fila, perfil):
            sin_cambios += 1
        else:
            existente.nombre = fila["nombre"]
            existente.email = fila["email"].lower()
            existente.telefono = fila.get("telefono") or None
            existente.ciudad = fila.get("ciudad") or None
            existente.activo = fila.get("activo", "true").lower() in ("true", "1", "si")
            for campo, valor in perfil.items():
                setattr(existente, campo, valor)
            actualizados += 1

    try:
        sesion.commit()
    except IntegrityError as exc:
        # Fila que chocó con un email ya usado por otro documento: se reporta y no
        # se pierde el resto de la importación.
        sesion.rollback()
        return _problema(409, "Conflicto",
                         f"colisión de datos únicos: {exc.orig}".replace("\n", " ")[:300],
                         str(request.url.path))

    return ResultadoImportacion(
        archivo=nombre_archivo,
        procesadas=procesadas,
        insertados=insertados,
        actualizados=actualizados,
        sin_cambios=sin_cambios,
        rechazadas=rechazadas,
        errores=errores,
    )


# -------------------------------------------------------------- uso interno
@router.get("/clientes/{cliente_id}/credenciales")
def verificar_cliente_interno(cliente_id: str, request: Request,
                              sesion: Session = Depends(obtener_sesion),
                              _auth: dict = Depends(rol_interno)):
    """Consulta interna (token de servicio): existe y está activo (§9)."""
    cliente = sesion.get(Cliente, cliente_id)
    if cliente is None:
        return _problema(404, "Recurso no encontrado", f"cliente {cliente_id} no existe",
                         str(request.url.path))
    return {"cliente_id": cliente.id, "activo": cliente.activo,
            "nombre": cliente.nombre, "email": cliente.email}
