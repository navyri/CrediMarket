"""Medición puntual de drift (PSI) entre el histórico de entrenamiento y
lotes de producción. Se usa para decidir el diseño de P2-9; no es el entregable."""
import sys
from pathlib import Path

import numpy as np
import pandas as pd

sys.stdout.reconfigure(encoding="utf-8", errors="replace")

RAIZ = Path(r"C:\Users\usuario\Downloads\CrediMarket")
REF = RAIZ / "ml" / "datos" / "entrenamiento.csv"
NUEVO = Path(r"C:\Users\usuario\Downloads\final parte 2\solicitudes_nuevas.csv")

VARIABLES = ["ingresos_mensuales_cop", "obligaciones_mensuales_cop",
             "antiguedad_laboral_meses", "meses_historial_crediticio",
             "creditos_previos", "atrasos_previos_30d",
             "porcentaje_pago_puntual", "monto_solicitado_cop", "plazo_meses",
             "cuota_estimada_cop"]


def psi(ref: pd.Series, obs: pd.Series, bins: int = 10) -> float:
    """Population Stability Index con cortes por cuantiles de la referencia."""
    ref = pd.to_numeric(ref, errors="coerce").dropna()
    obs = pd.to_numeric(obs, errors="coerce").dropna()
    cortes = np.unique(np.quantile(ref, np.linspace(0, 1, bins + 1)))
    if len(cortes) < 3:
        return 0.0
    cortes[0], cortes[-1] = -np.inf, np.inf
    r = np.histogram(ref, bins=cortes)[0] / len(ref)
    o = np.histogram(obs, bins=cortes)[0] / len(obs)
    r, o = np.clip(r, 1e-6, None), np.clip(o, 1e-6, None)
    return float(np.sum((o - r) * np.log(o / r)))


def main() -> int:
    ref = pd.read_csv(REF)
    obs = pd.read_csv(NUEVO)
    print(f"referencia={len(ref)} filas · observado={len(obs)} filas\n")
    print(f"{'variable':32} {'PSI':>8}  estado")
    peor = 0.0
    for v in VARIABLES:
        valor = psi(ref[v], obs[v])
        peor = max(peor, valor)
        estado = ("estable" if valor < 0.10 else
                  "revisar" if valor < 0.25 else "ALERTA")
        print(f"{v:32} {valor:8.4f}  {estado}")
    print(f"\nPSI máximo = {peor:.4f}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
