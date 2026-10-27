"""P2-6 · Promoción explícita y rollback del modelo activo de CrediMarket.

La promoción es un acto deliberado: nunca se sirve "la última corrida". Este
script valida que el artefacto exportado carga y predice, y solo entonces
actualiza `ml/modelos/activo.json`, el archivo que el servicio Préstamos lee
en arranque. Cada promoción se apunta en `ml/modelos/historial_promociones.jsonl`,
de modo que `rollback` siempre sabe a qué versión volver.

Reglas (§8.C):
- `promover` exige una versión exportada en `ml/modelos/<v>/` con metadatos;
- antes de escribir el activo se carga el pipeline con joblib y se ejecuta una
  predicción de prueba: un artefacto corrupto bloquea la promoción;
- `rollback` reactiva la última promoción anterior distinta de la actual;
- el servicio Préstamos NUNCA cambia de modelo por sí solo: `/admin/modelo/promover`
  invoca esta misma lógica (P2-7).

Uso:
    python ml/export/administrar_activo.py promover v1 [--motivo "..."]
    python ml/export/administrar_activo.py promover v2 [--motivo "..."]
    python ml/export/administrar_activo.py rollback
    python ml/export/administrar_activo.py estado
"""
import argparse
import json
import sys
import time
from pathlib import Path

RAIZ = Path(__file__).resolve().parents[2]
MODELOS = RAIZ / "ml" / "modelos"
ACTIVO = MODELOS / "activo.json"
HISTORIAL = MODELOS / "historial_promociones.jsonl"

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")


def _leer_json(ruta: Path) -> dict:
    return json.loads(ruta.read_text(encoding="utf-8"))


def _escribir_json(ruta: Path, datos: dict) -> None:
    ruta.write_text(json.dumps(datos, indent=2, ensure_ascii=False) + "\n",
                    encoding="utf-8")


def _apuntar_historial(entrada: dict) -> None:
    with HISTORIAL.open("a", encoding="utf-8") as archivo:
        archivo.write(json.dumps(entrada, ensure_ascii=False) + "\n")


def _historial() -> list[dict]:
    if not HISTORIAL.exists():
        return []
    return [json.loads(linea) for linea in
            HISTORIAL.read_text(encoding="utf-8").splitlines() if linea.strip()]


def verificar_artefacto(version: str) -> dict:
    """Carga el pipeline exportado y predice: la promoción exige un modelo útil."""
    import joblib
    import pandas as pd

    carpeta = MODELOS / version
    artefacto = carpeta / "modelo.joblib"
    metadatos = carpeta / "metadatos.json"
    if not artefacto.exists():
        raise SystemExit(f"no existe el artefacto exportado: {artefacto}")
    if not metadatos.exists():
        raise SystemExit(f"faltan los metadatos del modelo: {metadatos}")

    pipeline = joblib.load(artefacto)
    ficha = _leer_json(metadatos)

    # Ejemplo realista con valores faltantes: el imputador del pipeline debe
    # absorberlos sin error (es lo que ocurrirá en producción).
    ejemplo = pd.DataFrame([{v: None for v in ficha["variables"]}])
    proba = pipeline.predict_proba(ejemplo)[0][1]
    if not 0.0 <= float(proba) <= 1.0:
        raise SystemExit(f"la predicción de prueba salió fuera de [0,1]: {proba}")
    return ficha


def promover(version: str, motivo: str) -> dict:
    ficha = verificar_artefacto(version)
    anterior = _leer_json(ACTIVO) if ACTIVO.exists() else None

    activo = {
        "modelo_version": version,
        "mlflow_model": ficha.get("mlflow_model", "credimarket-incumplimiento"),
        "mlflow_version": ficha.get("mlflow_version"),
        "run_id": ficha.get("run_id"),
        "candidato": ficha["candidato"],
        "umbral": ficha["umbral"],
        "metrica_seleccion": ficha["metrica_seleccion"],
        "roc_auc_validacion": ficha["roc_auc_validacion"],
        "metricas_prueba": ficha["metricas_prueba"],
        "variables": ficha["variables"],
        "promovido_en": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        "motivo": motivo,
        "version_anterior": anterior["modelo_version"] if anterior else None,
    }
    _escribir_json(ACTIVO, activo)
    _apuntar_historial({k: activo[k] for k in
                        ("modelo_version", "run_id", "umbral", "promovido_en",
                         "motivo")})
    return activo


def rollback() -> dict:
    """Reactiva la última promoción anterior distinta de la actual."""
    if not ACTIVO.exists():
        raise SystemExit("no hay modelo activo: nada desde donde volver")
    actual = _leer_json(ACTIVO)
    entradas = [e for e in _historial()
                if e["modelo_version"] != actual["modelo_version"]]
    if not entradas:
        raise SystemExit("no hay una promoción anterior registrada: nada que restaurar")
    objetivo = entradas[-1]["modelo_version"]
    return promover(objetivo, motivo=f"rollback desde {actual['modelo_version']}")


def estado() -> None:
    if ACTIVO.exists():
        print(json.dumps(_leer_json(ACTIVO), indent=2, ensure_ascii=False))
    else:
        print("sin modelo activo: ejecuta `promover v1`")


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest="comando", required=True)

    p_promover = sub.add_parser("promover", help="promueve una versión exportada")
    p_promover.add_argument("version", choices=["v1", "v2"])
    p_promover.add_argument("--motivo", default="promocion explicita")

    sub.add_parser("rollback", help="vuelve a la promoción anterior")
    sub.add_parser("estado", help="muestra el modelo activo")

    args = parser.parse_args()
    if args.comando == "promover":
        activo = promover(args.version, args.motivo)
        print(f"promovida {activo['modelo_version']} "
              f"(umbral={activo['umbral']}, run={activo['run_id']})")
    elif args.comando == "rollback":
        activo = rollback()
        print(f"rollback a {activo['modelo_version']} "
              f"(umbral={activo['umbral']}, motivo={activo['motivo']})")
    else:
        estado()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
