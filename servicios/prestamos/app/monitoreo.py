"""Monitoreo de desempeño y deriva del modelo en producción (§15.2, P2-9.4).

Dos insumos, ambos del DUEÑO del modelo (servicio Préstamos):

1. `MetricaInferencia`: una fila por decisión (solicitud o inferencia aislada)
   con latencia, probabilidad, umbral y el vector de variables. Alimenta
   `GET /monitoreo/estado` (tasas, p50/p95 de latencia, PSI del lote reciente).
2. `referencia_psi.json`: línea base exportada del histórico de entrenamiento
   por `ml/monitoreo/preparar_referencia.py`. El servicio solo la LEE: nunca
   recalibra por sí solo (P2-DEC-002).

PSI (Population Stability Index): por variable, cortes por cuantiles de la
línea base; 0 = idéntico, < 0.10 estable, ≥ 0.10 revisar, ≥ 0.25 alerta.
"""
import json
import logging
import math
import threading
import time
from bisect import bisect_right
from decimal import Decimal
from pathlib import Path

from sqlalchemy import select
from sqlalchemy.orm import Session

from .config import ajustes
from .models import MetricaInferencia

logger = logging.getLogger("prestamos.monitoreo")

# Umbrales clásicos de PSI (documentados en docs/arquitectura/estrategia-pruebas.md).
UMBRAL_REVISAR = 0.10
UMBRAL_ALERTA = 0.25
# Mínimo de inferencias para hablar de deriva con sentido estadístico.
MINIMO_PARA_PSI = 30

_bloqueo = threading.Lock()
_referencia: dict | None = None
_referencia_ruta: str | None = None
_referencia_mtime: float | None = None


# ------------------------------------------------------------------ línea base
def ruta_referencia() -> Path:
    return Path(ajustes.modelo_dir) / "referencia_psi.json"


def cargar_referencia(force: bool = False) -> dict | None:
    """Carga (y cachea) la línea base; None si aún no existe."""
    global _referencia, _referencia_ruta, _referencia_mtime
    ruta = ruta_referencia()
    try:
        mtime = ruta.stat().st_mtime
    except OSError:
        return None
    with _bloqueo:
        if (not force and _referencia is not None
                and _referencia_ruta == str(ruta) and _referencia_mtime == mtime):
            return _referencia
        try:
            _referencia = json.loads(ruta.read_text(encoding="utf-8"))
            _referencia_ruta = str(ruta)
            _referencia_mtime = mtime
        except (OSError, json.JSONDecodeError) as exc:
            logger.error("no se pudo leer la referencia de deriva: %s", exc)
            return None
        return _referencia


# ------------------------------------------------------------------------ PSI
def _clasificar(psi_max: float | None) -> str:
    if psi_max is None:
        return "sin_datos"
    if psi_max >= UMBRAL_ALERTA:
        return "alerta"
    if psi_max >= UMBRAL_REVISAR:
        return "revisar"
    return "estable"


def _psi_numerica(esperado: dict, valores: list[float]) -> float | None:
    valores = [v for v in valores if v is not None]
    if not valores:
        return None
    internos = esperado["bordes"]
    conteos = [0] * (len(internos) + 1)
    for valor in valores:
        conteos[bisect_right(internos, float(valor))] += 1
    observado = [max(c / len(valores), 1e-6) for c in conteos]
    base = [max(p, 1e-6) for p in esperado["proporciones"]]
    return float(sum((o - e) * math.log(o / e)
                     for o, e in zip(observado, base)))


def _psi_categorica(esperado: dict, valores: list) -> float | None:
    # Los vacíos van a `desconocido` (la misma regla con la que se construyó
    # la línea base): no se descartan ni se inventa una categoría nueva.
    limpios = ["desconocido" if v is None else (str(v).strip().lower()
                                                or "desconocido")
               for v in valores]
    if not limpios:
        return None
    conteos: dict[str, int] = {}
    for valor in limpios:
        conteos[valor] = conteos.get(valor, 0) + 1
    categorias = set(conteos) | set(esperado["proporciones"])
    total = len(limpios)
    psi = 0.0
    for categoria in categorias:
        o = max(conteos.get(categoria, 0) / total, 1e-6)
        e = max(esperado["proporciones"].get(categoria, 0.0), 1e-6)
        psi += (o - e) * math.log(o / e)
    return float(psi)


def psi_lote(referencia: dict | None, filas: list[dict]) -> dict:
    """PSI de un lote de vectores de variables contra la línea base.

    `filas` son diccionarios con los nombres de las columnas del histórico
    (§9). Devuelve el PSI por variable, el máximo y su clasificación.
    """
    if not referencia:
        return {"estado": "sin_referencia", "filas": len(filas),
                "por_variable": {}, "psi_maximo": None}
    if not filas:
        return {"estado": "sin_datos", "filas": 0,
                "por_variable": {}, "psi_maximo": None}

    por_variable: dict[str, float] = {}
    for variable, esperado in referencia.get("numericas", {}).items():
        psi = _psi_numerica(esperado, [fila.get(variable) for fila in filas])
        if psi is not None:
            por_variable[variable] = round(psi, 6)
    for variable, esperado in referencia.get("categoricas", {}).items():
        psi = _psi_categorica(esperado, [fila.get(variable) for fila in filas])
        if psi is not None:
            por_variable[variable] = round(psi, 6)

    psi_max = max(por_variable.values()) if por_variable else None
    clasificacion = _clasificar(psi_max)
    # Muestra pequeña: el PSI se reporta pero no se clasifica (ruido de corte).
    if len(filas) < MINIMO_PARA_PSI:
        clasificacion = "insuficiente"
    return {"estado": clasificacion, "filas": len(filas),
            "por_variable": por_variable,
            "psi_maximo": round(psi_max, 6) if psi_max is not None else None,
            "variables_con_alerta": sorted(
                v for v, p in por_variable.items() if p >= UMBRAL_ALERTA),
            "variables_a_revisar": sorted(
                v for v, p in por_variable.items()
                if UMBRAL_REVISAR <= p < UMBRAL_ALERTA)}


# --------------------------------------------------------------- registro vivo
def registrar(sesion: Session, *, origen: str, prestamo_id: str | None,
              variables: dict, probabilidad: float, umbral: float,
              aplico_regla: bool, latencia_ms: float,
              modelo_version: str) -> MetricaInferencia:
    """Añade la métrica de una decisión a la MISMA transacción (sin commit)."""
    serializables: dict = {}
    for clave, valor in variables.items():
        if clave.startswith("_"):
            continue
        # `model_dump()` trae Decimal (JSON no lo serializa) y None es un
        # faltante legítimo que el imputador absorbe (§8.B).
        serializables[clave] = float(valor) if isinstance(valor, Decimal) \
            else valor
    metrica = MetricaInferencia(
        origen=origen, prestamo_id=prestamo_id,
        modelo_version=modelo_version or "sin-modelo",
        probabilidad=probabilidad, umbral=umbral,
        aplico_regla=aplico_regla, latencia_ms=round(latencia_ms, 3),
        variables=serializables)
    sesion.add(metrica)
    return metrica


def percentil(valores: list[float], p: float) -> float | None:
    """Percentil lineal (p en 0..1) sin dependencias externas."""
    if not valores:
        return None
    ordenados = sorted(valores)
    if len(ordenados) == 1:
        return ordenados[0]
    k = (len(ordenados) - 1) * p
    inferior = int(k)
    superior = min(inferior + 1, len(ordenados) - 1)
    return (ordenados[inferior]
            + (ordenados[superior] - ordenados[inferior]) * (k - inferior))


def estado(sesion: Session, limite: int = 500) -> dict:
    """Resumen de las últimas `limite` inferencias contra la línea base."""
    referencia = cargar_referencia()
    filas = sesion.scalars(
        select(MetricaInferencia)
        .order_by(MetricaInferencia.registrado_en.desc())
        .limit(limite)).all()

    if not filas:
        return {
            "total_inferencias": 0, "modelo_version": None,
            "latencia_ms": {"p50": None, "p95": None, "maxima": None},
            "probabilidad_media": None, "tasa_sobre_umbral": None,
            "aplicaron_regla": 0, "ventana": 0,
            "deriva": psi_lote(referencia, []),
            "linea_base": ficha_referencia(referencia),
            "estado": "sin_datos",
        }

    latencias = [f.latencia_ms for f in filas]
    probabilidades = [f.probabilidad for f in filas]
    sobre_umbral = sum(1 for f in filas if f.probabilidad >= f.umbral)
    vector = [f.variables for f in filas if isinstance(f.variables, dict)]
    deriva = psi_lote(referencia, vector)

    return {
        "total_inferencias": len(filas),
        "modelo_version": filas[0].modelo_version,
        "latencia_ms": {
            "p50": round(percentil(latencias, 0.50), 3),
            "p95": round(percentil(latencias, 0.95), 3),
            "maxima": round(max(latencias), 3),
        },
        "probabilidad_media": round(sum(probabilidades) / len(probabilidades), 6),
        "tasa_sobre_umbral": round(sobre_umbral / len(filas), 4),
        "aplicaron_regla": sum(1 for f in filas if f.aplico_regla),
        "ventana": len(filas),
        "deriva": deriva,
        "linea_base": ficha_referencia(referencia),
        "estado": deriva["estado"],
    }


def ficha_referencia(referencia: dict | None) -> dict | None:
    if not referencia:
        return None
    return {"fuente": referencia.get("fuente"),
            "filas": referencia.get("filas"),
            "generado_en": referencia.get("generado_en"),
            "sha256_fuente": referencia.get("sha256_fuente")}


def tiempo() -> float:
    return time.perf_counter()
