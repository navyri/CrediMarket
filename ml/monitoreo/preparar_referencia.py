"""Exporta la línea base de deriva (PSI) desde el histórico de entrenamiento.

§8/§15.2 (P2-TEST-020): el monitoreo compara cada lote de producción contra la
distribución de referencia. Aquí se calcula esa referencia UNA vez, desde
`ml/datos/entrenamiento.csv` (semilla 42, splits fijos), y se guarda como JSON
en `ml/modelos/referencia_psi.json`: bordes por cuantiles para las variables
numéricas y proporciones para `tipo_empleo`.

El servicio Préstamos solo LEE este archivo (no reentrena ni recalibra): la
línea base es fija y versionable, igual que el modelo activo.

Uso:
    python ml/monitoreo/preparar_referencia.py [ruta/entrenamiento.csv]
"""
import hashlib
import json
import sys
from datetime import datetime, timezone
from pathlib import Path

import numpy as np
import pandas as pd

sys.stdout.reconfigure(encoding="utf-8", errors="replace")

RAIZ = Path(__file__).resolve().parents[2]
DEFAULT_ENTRADA = RAIZ / "ml" / "datos" / "entrenamiento.csv"
SALIDA = RAIZ / "ml" / "modelos" / "referencia_psi.json"

# Variables del modelo (§8.B): numéricas con cortes por cuantiles + categórica.
NUMERICAS = [
    "ingresos_mensuales_cop", "obligaciones_mensuales_cop",
    "antiguedad_laboral_meses", "meses_historial_crediticio",
    "creditos_previos", "atrasos_previos_30d", "porcentaje_pago_puntual",
    "monto_solicitado_cop", "plazo_meses", "cuota_estimada_cop",
]
CATEGORICAS = ["tipo_empleo"]
BINS = 10   # mismos cortes que el diagnóstico (cuantiles 0..1)


def sha256_de(ruta: Path) -> str:
    h = hashlib.sha256()
    with ruta.open("rb") as archivo:
        for bloque in iter(lambda: archivo.read(1 << 20), b""):
            h.update(bloque)
    return h.hexdigest()


def referencia_numerica(serie: pd.Series) -> dict:
    """Bordes internos por cuantiles + proporciones observadas (10 cortes)."""
    valores = pd.to_numeric(serie, errors="coerce").dropna().to_numpy()
    cortes = np.unique(np.quantile(valores, np.linspace(0, 1, BINS + 1)))
    internos = [float(c) for c in cortes[1:-1]]          # sin ±inf
    bordes = [-np.inf, *internos, np.inf]
    conteos = np.histogram(valores, bins=np.array(bordes))[0]
    proporciones = (conteos / len(valores)).tolist()
    return {"bordes": internos, "proporciones": proporciones,
            "n": int(len(valores))}


def referencia_categorica(serie: pd.Series) -> dict:
    limpio = serie.astype(str).str.strip().str.lower().fillna("desconocido")
    conteos = limpio.value_counts(normalize=True)
    return {"proporciones": {k: float(v) for k, v in conteos.items()},
            "n": int(len(limpio))}


def main(entrada: Path = DEFAULT_ENTRADA) -> int:
    if not entrada.exists():
        print(f"no existe {entrada}", file=sys.stderr)
        return 1
    datos = pd.read_csv(entrada)
    faltantes = [v for v in NUMERICAS + CATEGORICAS if v not in datos.columns]
    if faltantes:
        print(f"faltan columnas: {faltantes}", file=sys.stderr)
        return 1

    referencia = {
        "descripcion": ("Línea base de deriva: distribución del histórico de "
                        "entrenamiento contra la que se mide el PSI de cada "
                        "lote (P2-TEST-020)."),
        "fuente": str(entrada.relative_to(RAIZ)).replace("\\", "/"),
        "sha256_fuente": sha256_de(entrada),
        "filas": int(len(datos)),
        "bins": BINS,
        "generado_en": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "numericas": {v: referencia_numerica(datos[v]) for v in NUMERICAS},
        "categoricas": {v: referencia_categorica(datos[v]) for v in CATEGORICAS},
    }
    SALIDA.write_text(json.dumps(referencia, indent=2, ensure_ascii=False) + "\n",
                      encoding="utf-8")
    psi_self = max(psi_de_referencia(referencia, datos)[1].values())
    print(f"referencia escrita en {SALIDA} ({len(datos)} filas)")
    print(f"PSI del histórico contra sí mismo = {psi_self:.6f} (debe ser 0)")
    return 0


def psi_de_referencia(referencia: dict, lote: pd.DataFrame) -> tuple[float, dict]:
    """PSI de un lote contra la línea base (reutilizado por la demo)."""
    from bisect import bisect_right

    psi: dict[str, float] = {}
    for variable, ref in referencia["numericas"].items():
        valores = pd.to_numeric(lote[variable], errors="coerce").dropna()
        if len(valores) == 0:
            continue
        internos = ref["bordes"]
        conteos = [0] * (len(internos) + 1)
        for valor in valores:
            conteos[bisect_right(internos, valor)] += 1
        observado = np.array(conteos) / len(valores)
        esperado = np.clip(np.array(ref["proporciones"]), 1e-6, None)
        observado = np.clip(observado, 1e-6, None)
        psi[variable] = float(np.sum((observado - esperado)
                                     * np.log(observado / esperado)))
    for variable, ref in referencia["categoricas"].items():
        conteos: dict[str, int] = {}
        serie = lote[variable].astype(str).str.strip().str.lower() \
            .fillna("desconocido")
        for valor in serie:
            conteos[valor] = conteos.get(valor, 0) + 1
        total = sum(conteos.values())
        categorias = set(conteos) | set(ref["proporciones"])
        esperado = np.clip(np.array([ref["proporciones"].get(c, 0.0)
                                     for c in categorias]), 1e-6, None)
        observado = np.clip(np.array([conteos.get(c, 0) / total
                                      for c in categorias]), 1e-6, None)
        psi[variable] = float(np.sum((observado - esperado)
                                     * np.log(observado / esperado)))
    maximo = max(psi.values()) if psi else 0.0
    return maximo, psi


if __name__ == "__main__":
    ruta = Path(sys.argv[1]) if len(sys.argv) > 1 else DEFAULT_ENTRADA
    raise SystemExit(main(ruta))
