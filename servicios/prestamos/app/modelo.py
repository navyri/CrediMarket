"""Carga y exposición del modelo ACTIVO de riesgo (§8.D).

El servicio Préstamos dueño del modelo: lee `activo.json` (escrito por la
promoción explícita, nunca "la última corrida") y carga el pipeline completo
exportado por `ml/train/entrenar.py`. Si no hay modelo, el servicio sigue
vivo pero `/ready` responde 503 (§8.E) y no decide préstamos.

La inferencia usa el MISMO `Pipeline` exportado (preprocesamiento incluido):
imputación y escalado ya vienen dentro del artefacto (§8.B).
"""
import json
import logging
import threading
import time
from pathlib import Path

import joblib
import pandas as pd

from .config import ajustes

logger = logging.getLogger("prestamos.modelo")

_bloqueo = threading.Lock()
_activo: dict | None = None          # ficha de activo.json
_pipeline = None                     # Pipeline de joblib
_cargado_en: str | None = None
_error_carga: str | None = None


def _ahora_iso() -> str:
    return time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())


def _ruta_activo() -> Path:
    return Path(ajustes.modelo_dir) / "activo.json"


def recargar() -> bool:
    """(Re)carga el modelo activo desde disco. Devuelve True si quedó listo."""
    global _activo, _pipeline, _cargado_en, _error_carga
    ruta = _ruta_activo()
    with _bloqueo:
        if not ruta.exists():
            _activo = _pipeline = None
            _error_carga = f"no existe {ruta}: ejecuta la promoción explícita"
            logger.warning(_error_carga)
            return False
        try:
            ficha = json.loads(ruta.read_text(encoding="utf-8"))
            artefacto = Path(ajustes.modelo_dir) / ficha["modelo_version"] / "modelo.joblib"
            pipeline = joblib.load(artefacto)
            _activo, _pipeline = ficha, pipeline
            _cargado_en = ficha.get("promovido_en")
            _error_carga = None
            logger.info("modelo activo cargado: %s (umbral=%s)",
                        ficha["modelo_version"], ficha["umbral"])
            return True
        except Exception as exc:                       # noqa: BLE001
            _activo = _pipeline = None
            _error_carga = f"error cargando el modelo activo: {exc}"
            logger.exception(_error_carga)
            return False


def disponible() -> bool:
    return _pipeline is not None


def error_carga() -> str | None:
    return _error_carga


def ficha_activa() -> dict | None:
    return _activo


def info() -> dict | None:
    """Detalle para `GET /modelo/info` (§8.E)."""
    if _activo is None:
        return None
    return {
        "modelo_version": _activo["modelo_version"],
        "run_id": _activo.get("run_id"),
        "umbral": _activo["umbral"],
        "variables": _activo.get("variables", []),
        "fecha_promocion": _activo.get("promovido_en", ""),
        "mlflow_url": ajustes.url_mlflow,
        "candidato": _activo.get("candidato"),
        "roc_auc_validacion": _activo.get("roc_auc_validacion"),
        "metricas_prueba": _activo.get("metricas_prueba"),
    }


def predecir(fila: dict) -> float:
    """Probabilidad de `incumplimiento_90d` para una fila de variables.

    Lanza si el modelo no está cargado: el caller decide qué responder.
    """
    if _pipeline is None or _activo is None:
        raise RuntimeError(_error_carga or "modelo no disponible")
    columnas = _activo.get("variables")
    entrada = pd.DataFrame([{c: fila.get(c) for c in columnas}])
    return float(_pipeline.predict_proba(entrada)[0][1])


# ------------------------------------------------------- promoción / rollback
_HISTORIAL = "historial_promociones.jsonl"


def _ruta(version: str) -> Path:
    return Path(ajustes.modelo_dir) / version


def versiones_exportadas() -> list[str]:
    """Versiones con artefacto exportado (carpeta con modelo.joblib + ficha)."""
    base = Path(ajustes.modelo_dir)
    if not base.exists():
        return []
    return sorted(d.name for d in base.iterdir()
                  if d.is_dir() and (d / "modelo.joblib").exists()
                  and (d / "metadatos.json").exists())


def _verificar_artefacto(version: str) -> dict:
    """Carga el pipeline exportado y predice: la promoción exige un modelo útil."""
    carpeta = _ruta(version)
    ficha = json.loads((carpeta / "metadatos.json").read_text(encoding="utf-8"))
    pipeline = joblib.load(carpeta / "modelo.joblib")
    # Ejemplo realista con faltantes: el imputador del pipeline debe
    # absorberlos sin error (es lo que ocurrirá en producción).
    ejemplo = pd.DataFrame([{v: None for v in ficha["variables"]}])
    proba = pipeline.predict_proba(ejemplo)[0][1]
    if not 0.0 <= float(proba) <= 1.0:
        raise ValueError(f"la predicción de prueba salió fuera de [0,1]: {proba}")
    return ficha


def _historial() -> list[dict]:
    ruta = Path(ajustes.modelo_dir) / _HISTORIAL
    if not ruta.exists():
        return []
    return [json.loads(linea) for linea in
            ruta.read_text(encoding="utf-8").splitlines() if linea.strip()]


def promover(version: str, motivo: str) -> dict:
    """Promoción EXPLÍCITA (§8.D): nunca se sirve "la última corrida".

    1. verifica que el artefacto exportado carga y predice (bloquea un
       artefacto corrupto);
    2. escribe `activo.json` (lo que el servicio carga y recarga);
    3. apunta la decisión en `historial_promociones.jsonl`;
    4. recarga el modelo en memoria.

    El rollback es una promoción explícita de la versión anterior registrada
    en el historial: el servicio nunca decide por sí solo (P2-DEC-002).
    """
    ficha = _verificar_artefacto(version)
    ruta_activo = Path(ajustes.modelo_dir) / "activo.json"
    anterior = json.loads(ruta_activo.read_text(encoding="utf-8")) \
        if ruta_activo.exists() else None

    activo = {
        "modelo_version": version,
        "mlflow_model": ficha.get("mlflow_model", "credimarket-incumplimiento"),
        "mlflow_version": ficha.get("mlflow_version"),
        "run_id": ficha.get("run_id"),
        "candidato": ficha["candidato"],
        "umbral": ficha["umbral"],
        "metrica_seleccion": ficha.get("metrica_seleccion"),
        "roc_auc_validacion": ficha.get("roc_auc_validacion"),
        "metricas_prueba": ficha.get("metricas_prueba"),
        "variables": ficha["variables"],
        "promovido_en": _ahora_iso(),
        "motivo": motivo,
        "version_anterior": anterior["modelo_version"] if anterior else None,
    }
    ruta_activo.write_text(json.dumps(activo, indent=2, ensure_ascii=False) + "\n",
                           encoding="utf-8")
    with (Path(ajustes.modelo_dir) / _HISTORIAL).open("a", encoding="utf-8") as archivo:
        archivo.write(json.dumps({k: activo[k] for k in
                                  ("modelo_version", "run_id", "umbral",
                                   "promovido_en", "motivo")},
                                 ensure_ascii=False) + "\n")
    recargar()
    logger.info("modelo %s promovido: %s", version, motivo)
    return activo


def rollback(motivo: str = "rollback") -> dict:
    """Reactiva la última promoción anterior distinta de la actual (§8.D)."""
    ruta_activo = Path(ajustes.modelo_dir) / "activo.json"
    if not ruta_activo.exists():
        raise ValueError("no hay modelo activo: nada desde donde volver")
    actual = json.loads(ruta_activo.read_text(encoding="utf-8"))
    previas = [e for e in _historial()
               if e["modelo_version"] != actual["modelo_version"]]
    if not previas:
        raise ValueError("no hay una promoción anterior registrada: nada que restaurar")
    return promover(previas[-1]["modelo_version"],
                    motivo=f"{motivo} desde {actual['modelo_version']}")
