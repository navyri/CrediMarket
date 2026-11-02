"""Exporta el historial de MLflow a JSON (entregable 4: artefactos de ML).

Lee el Tracking Server del Compose (MLFLOW_TRACKING_URI o http://localhost:5000)
y vuelca experimentos, corridas, parámetros y métricas a
`docs/evidencias/experimentos_mlflow.json`, para que el informe de selección del
modelo se lea de datos consultables y no de una captura aislada (§8.C).

Uso:  python scripts/ml/exportar_experimentos.py
"""
import json
import os
import sys
from pathlib import Path

sys.stdout.reconfigure(encoding="utf-8")
os.environ.setdefault("MLFLOW_DISABLE_AGENT_HINT", "1")

import mlflow                                          # noqa: E402
from mlflow import MlflowClient                        # noqa: E402

RAIZ = Path(__file__).resolve().parents[2]
DESTINO = RAIZ / "docs" / "evidencias" / "experimentos_mlflow.json"
URI = os.environ.get("MLFLOW_TRACKING_URI", "http://localhost:5000")

INTERES = ("roc_auc", "average_precision", "pr_auc", "f1", "precision", "recall",
           "accuracy", "brier", "umbral", "fit_time", "confusion", "costo")


def _filtrar(d: dict) -> dict:
    return {k: v for k, v in sorted(d.items())
            if any(p in k.lower() for p in INTERES)}


def main() -> int:
    mlflow.set_tracking_uri(URI)
    cliente = MlflowClient()

    experimentos = []
    for exp in cliente.search_experiments():
        corridas = cliente.search_runs(experiment_ids=[exp.experiment_id],
                                       max_results=200, order_by=["start_time DESC"])
        experimentos.append({
            "experiment_id": exp.experiment_id,
            "nombre": exp.name,
            "corridas": [{
                "run_id": r.info.run_id,
                "nombre": r.data.tags.get("mlflow.runName"),
                "estado": r.info.status,
                "inicio": r.info.start_time,
                "fin": r.info.end_time,
                "etiqueta": r.data.tags.get("mlflow.source.type"),
                "parametros": dict(sorted(r.data.params.items())),
                "metricas": _filtrar(r.data.metrics),
                "artifact_uri": r.info.artifact_uri,
            } for r in corridas],
        })

    total = sum(len(e["corridas"]) for e in experimentos)
    salida = {
        "tracking_uri": URI,
        "experimentos": experimentos,
        "total_corridas": total,
    }
    DESTINO.parent.mkdir(parents=True, exist_ok=True)
    DESTINO.write_text(json.dumps(salida, indent=2, ensure_ascii=False) + "\n",
                       encoding="utf-8")
    print(f"{len(experimentos)} experimentos · {total} corridas")
    for e in experimentos:
        print(f"  - {e['nombre']}: {len(e['corridas'])} corridas")
    print(f"Evidencia: {DESTINO}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
