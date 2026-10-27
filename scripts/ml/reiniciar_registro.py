"""Reinicia el registro de modelos de MLflow (utilidad de demostración).

Borra las versiones indicadas del registro `credimarket-incumplimiento`; con
`--registro-completo` elimina también el modelo registrado, de modo que la
siguiente corrida vuelva a empezar la numeración en 1.

Uso:
    python scripts/ml/borrar_versiones_registro.py               # todas
    python scripts/ml/borrar_versiones_registro.py 3 4           # selectivas
    python scripts/ml/borrar_versiones_registro.py --registro-completo
"""
import os
import sys

os.environ.setdefault("MLFLOW_DISABLE_AGENT_HINT", "1")
import mlflow  # noqa: E402

NOMBRE = "credimarket-incumplimiento"
URI = "http://127.0.0.1:5000"


def main() -> int:
    objetivo = [a for a in sys.argv[1:] if not a.startswith("--")]
    completo = "--registro-completo" in sys.argv
    cliente = mlflow.tracking.MlflowClient(URI)

    if completo:
        try:
            cliente.delete_registered_model(NOMBRE)
            print(f"registro '{NOMBRE}' eliminado por completo")
        except mlflow.exceptions.RestException:
            print(f"el registro '{NOMBRE}' no existía; nada que borrar")
        return 0

    versiones = cliente.search_model_versions(f"name='{NOMBRE}'")
    borradas = []
    for v in versiones:
        if not objetivo or v.version in objetivo:
            cliente.delete_model_version(name=NOMBRE, version=v.version)
            borradas.append(v.version)
    restantes = [v.version for v in
                 cliente.search_model_versions(f"name='{NOMBRE}'")]
    print(f"borradas: {borradas or 'ninguna'}; restantes: {restantes or 'ninguna'}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
