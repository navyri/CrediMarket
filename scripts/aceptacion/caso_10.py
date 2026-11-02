"""Caso §12.10 — Modelo exportado vs API.

Evidencia esperada: predicciones equivalentes y versión identificable. Se carga
el artefacto `modelo.joblib` exportado (el mismo que sirve el servicio) y se
compara su probabilidad con la del endpoint `/riesgo/predict` para el mismo
vector de variables.
"""
import json
import sys
from pathlib import Path

import requests

sys.path.insert(0, str(Path(__file__).resolve().parent))
from _comun import (RAIZ, URL_PRESTAMOS, admin_token, auth, evidencia, salir)

CASO = 10
REQUISITO = "§12.10 Modelo exportado vs API"
ESPERADO = "Predicciones equivalentes y versión identificable."

TASA_OFICIAL = float(__import__("os").environ.get("TASA_MENSUAL_OFICIAL", "0.018"))


def main() -> dict:
    token = admin_token()

    # Versión activa que sirve la API.
    info = requests.get(f"{URL_PRESTAMOS}/modelo/info", headers=auth(token),
                        timeout=15).json()
    version = info["modelo_version"]
    activo = json.loads((RAIZ / "ml" / "modelos" / "activo.json")
                        .read_text(encoding="utf-8"))
    assert activo["modelo_version"] == version, "info no coincide con activo.json"

    # Vector real de prueba (con un vacío, como el imputador debe absorber).
    cuerpo = {"ingresos_mensuales_cop": 3_500_000, "obligaciones_mensuales_cop": 900_000,
              "monto_solicitado_cop": 480_000, "plazo_meses": 18,
              "tipo_empleo": "dependiente", "antiguedad_laboral_meses": 30,
              "meses_historial_crediticio": 42, "creditos_previos": 2,
              "atrasos_previos_30d": 1, "porcentaje_pago_puntual": 88}

    # 1) Predicción por la API del servicio.
    api = requests.post(f"{URL_PRESTAMOS}/riesgo/predict", json=cuerpo,
                        headers=auth(token), timeout=30)
    assert api.status_code == 200, f"{api.status_code}: {api.text}"
    decision = api.json()
    assert decision["modelo_version"] == version
    assert decision["run_id"] == info["run_id"], "run_id no identificable"

    # 2) Misma predicción con el artefacto exportado, cargado fuera del servicio.
    import joblib
    import pandas as pd
    carpeta = RAIZ / "ml" / "modelos" / version
    ficha = json.loads((carpeta / "metadatos.json").read_text(encoding="utf-8"))
    pipeline = joblib.load(carpeta / "modelo.joblib")

    monto = float(cuerpo["monto_solicitado_cop"])
    plazo = int(cuerpo["plazo_meses"])
    cuota = monto * TASA_OFICIAL / (1 - (1 + TASA_OFICIAL) ** (-plazo))
    variables = {**cuerpo, "monto_solicitado_cop": monto, "plazo_meses": plazo,
                 "tasa_mensual": TASA_OFICIAL, "cuota_estimada_cop": round(cuota, 2)}
    entrada = pd.DataFrame([{c: variables.get(c) for c in ficha["variables"]}])
    proba_local = float(pipeline.predict_proba(entrada)[0][1])

    # 3) Equivalencia.
    proba_api = decision["probabilidad_incumplimiento"]
    assert abs(proba_api - proba_local) < 1e-9, \
        f"predicciones distintas: api={proba_api} artefacto={proba_local}"
    # La decisión es coherente con el umbral publicado.
    esperada = "FAVORABLE" if proba_api < decision["umbral"] else "DESFAVORABLE"
    assert decision["decision"] == esperada, decision

    return evidencia(
        CASO, REQUISITO, ESPERADO,
        f"versión {version} (run {decision['run_id'][:8]}…): probabilidad API "
        f"{proba_api:.10f} == artefacto {carpeta.name}/modelo.joblib "
        f"{proba_local:.10f} (|Δ| < 1e-9); decisión {decision['decision']} "
        f"vs umbral {decision['umbral']}",
        ok=True,
        detalle={"modelo_version": version, "run_id": decision["run_id"],
                 "probabilidad_api": proba_api, "probabilidad_artefacto": proba_local,
                 "umbral": decision["umbral"], "decision": decision["decision"],
                 "artefacto": str(carpeta / "modelo.joblib"),
                 "variables": ficha["variables"]})


if __name__ == "__main__":
    salir(main())
