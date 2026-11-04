"""§13.7 · Reproducción desde un clon limpio.

Un `git clone` NO trae el CSV crudo ni los binarios `*.joblib` (ambos están en
`.gitignore`: los datos no se publican y los artefactos se regeneran con la
misma semilla). Sin estos pasos, el servicio Préstamos arranca sin modelo y
`GET /ready` responde 503, por lo que los casos de aceptación 10, 11 y 16 no
pueden correr.

Este script deja el proyecto listo para la demo:

  1. comprueba que MLflow responde (infraestructura del Compose);
  2. localiza el histórico y crea las particiones (`ml/datos/*.csv`);
  3. entrena **v1** y **v2** con semilla 42 (corridas registradas en MLflow);
  4. promueve **v1** como versión activa (misma que la del proyecto entregado);
  5. verifica el artefacto y, si Préstamos está levantado, `GET /ready`.

Uso (con el Compose ya levantado y el CSV a mano):

    docker compose up -d
    python scripts/preparar_desde_clon.py --csv "ruta/al/prestamos_entrenamiento.csv"

La ruta del CSV también se puede dar con la variable de entorno
`CREDIMARKET_CSV_ENTRENAMIENTO` (ver `ml/prep/preparar_datos.py`).
"""
import argparse
import json
import subprocess
import sys
import time
import urllib.error
import urllib.request
from pathlib import Path

RAIZ = Path(__file__).resolve().parents[1]
MLFLOW = "http://localhost:5000"
PRESTAMOS_READY = "http://localhost:8003/ready"


def paso(titulo: str) -> None:
    print(f"\n=== {titulo}", flush=True)


def correr(cmd: list[str]) -> None:
    print(f"$ {' '.join(cmd)}", flush=True)
    resultado = subprocess.run(cmd, cwd=RAIZ)
    if resultado.returncode != 0:
        raise SystemExit(f"falló el comando (exit {resultado.returncode}): "
                         f"{' '.join(cmd)}")


def esperar(url: str, segundos: int, descripcion: str) -> None:
    """Espera acotada a que un servicio responda (sin reintentos infinitos)."""
    limite = time.time() + segundos
    ultimo = None
    while time.time() < limite:
        try:
            with urllib.request.urlopen(url, timeout=5) as respuesta:
                if respuesta.status < 500:
                    print(f"  {descripcion} → {respuesta.status} ({url})")
                    return
        except (urllib.error.URLError, OSError) as error:
            ultimo = error
        time.sleep(3)
    raise SystemExit(f"esperó {segundos}s sin respuesta de {url}: {ultimo}")


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--csv", type=Path, default=None,
                        help="ruta a prestamos_entrenamiento.csv")
    parser.add_argument("--sin-v2", action="store_true",
                        help="entrena solo v1 (omite el caso 11, que sí usa v2)")
    parser.add_argument("--sin-mlflow", action="store_true",
                        help="entrena sin registrar en MLflow (no recomendado)")
    args = parser.parse_args()

    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")

    paso("1/5 · infraestructura")
    esperar(MLFLOW, 120, "MLflow")
    print("  MLflow responde; si es la primera vez, la BD de experimentos "
          "empieza vacía (volumen mlflowdata).")

    paso("2/5 · particiones de datos")
    cmd_prep = [sys.executable, "ml/prep/preparar_datos.py"]
    if args.csv:
        cmd_prep += ["--entrada", str(args.csv)]
    correr(cmd_prep)

    paso("3/5 · entrenamiento (semilla 42, v1 y v2)")
    cmd_train = [sys.executable, "ml/train/entrenar.py", "--modelo-version", "v1"]
    if args.sin_mlflow:
        cmd_train.append("--sin-mlflow")
    correr(cmd_train)
    if not args.sin_v2:
        cmd_v2 = [sys.executable, "ml/train/entrenar.py", "--modelo-version", "v2"]
        if args.sin_mlflow:
            cmd_v2.append("--sin-mlflow")
        correr(cmd_v2)

    paso("4/5 · promoción explícita de v1 a versión activa")
    correr([sys.executable, "ml/export/administrar_activo.py", "promover", "v1",
            "--motivo", "bootstrap desde clon limpio (§13.7)"])

    paso("5/5 · verificación")
    artefacto = RAIZ / "ml" / "modelos" / "v1" / "modelo.joblib"
    activo = RAIZ / "ml" / "modelos" / "activo.json"
    if not artefacto.exists():
        raise SystemExit(f"no existe el artefacto: {artefacto}")
    ficha = json.loads(activo.read_text(encoding="utf-8"))
    print(f"  artefacto: {artefacto.relative_to(RAIZ)} "
          f"({artefacto.stat().st_size} bytes)")
    print(f"  activo: versión {ficha['modelo_version']} · run "
          f"{ficha['run_id'][:8]}… · umbral {ficha['umbral']}")

    try:
        with urllib.request.urlopen(PRESTAMOS_READY, timeout=5) as respuesta:
            print(f"  GET /ready → {respuesta.status} · {respuesta.read().decode()[:120]}")
    except (urllib.error.URLError, OSError) as error:
        print(f"  (Préstamos no responde todavía en :8003 — {error}; "
              f"arráncalo con `docker compose up -d prestamos`)")

    print("\nListo. Siguiente paso: python scripts/aceptacion/ejecutar_todas.py")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
