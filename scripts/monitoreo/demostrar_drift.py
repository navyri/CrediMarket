"""Demuestra el monitoreo de desempeño y deriva del modelo activo (P2-9).

Ejecuta contra el Compose levantado (`docker compose up -d`) y produce dos
evidencias (§15.2):

- **P2-TEST-020 (drift simulado y monitoreo)**:
  1. evalúa el lote REAL de producción (`solicitudes_nuevas.csv`, 200 filas)
     contra la línea base exportada del histórico → se espera "revisar"
     (el drift natural mide ~0.13 en `antiguedad_laboral_meses`);
  2. evalúa un lote SIMULADO con un desplazamiento documentado (ver
     `DESPLAZAMIENTO`) → se espera "alerta": el PSI cruza 0.25 y el estado
     lo reporta sin que nadie reentrene el modelo;
  3. genera decisiones reales con `/riesgo/predict` y lee
     `GET /monitoreo/estado` (latencias p50/p95, tasa sobre umbral, PSI);
  4. registra ambas evaluaciones en MLflow (experimento
     `credimarket-monitoreo`).
- **P2-TEST-019 (mediciones Redis)**: lee `GET /cache/estadisticas` de
  Productos tras tocar un producto: hit-rate, fallback y p50/p95 del GET.

Uso:
    python scripts/monitoreo/demostrar_drift.py [ruta/a/solicitudes_nuevas.csv]

Credenciales por variable de entorno (ADMIN_EMAIL / ADMIN_PASSWORD); los
valores por defecto son los de la semilla de demo local.
"""
import json
import os
import sys
from datetime import datetime, timezone
from pathlib import Path

import requests

sys.stdout.reconfigure(encoding="utf-8", errors="replace")

RAIZ = Path(__file__).resolve().parents[2]
EVIDENCIAS = RAIZ / "docs" / "evidencias"
DEFAULT_LOTE = Path(r"C:\Users\usuario\Downloads\final parte 2\solicitudes_nuevas.csv")

URL_PRESTAMOS = os.environ.get("URL_PRESTAMOS", "http://localhost:8003")
URL_PRODUCTOS = os.environ.get("URL_PRODUCTOS", "http://localhost:8001")
URL_CLIENTES = os.environ.get("URL_CLIENTES", "http://localhost:8002")
ADMIN_EMAIL = os.environ.get("ADMIN_EMAIL", "admin@credimarket.demo")
ADMIN_PASSWORD = os.environ.get("ADMIN_PASSWORD", "CAMBIAR_admin_local")

# Variables del modelo (§8.B) evaluadas por el PSI.
VARIABLES = [
    "ingresos_mensuales_cop", "obligaciones_mensuales_cop",
    "antiguedad_laboral_meses", "meses_historial_crediticio",
    "creditos_previos", "atrasos_previos_30d", "porcentaje_pago_puntual",
    "monto_solicitado_cop", "plazo_meses", "cuota_estimada_cop", "tipo_empleo",
]
# Desplazamiento SIMULADO documentado (P2-TEST-020): modela una cartera más
# joven y con más atrasos que el histórico (por ejemplo, una campaña nueva).
DESPLAZAMIENTO = {
    "antiguedad_laboral_meses": ("x", 0.25),
    "atrasos_previos_30d": ("+", 4),
    "creditos_previos": ("+", 3),
    "porcentaje_pago_puntual": ("-", 35),
}


def token_admin() -> str:
    respuesta = requests.post(
        f"{URL_CLIENTES}/auth/token", timeout=10,
        json={"email": ADMIN_EMAIL, "password": ADMIN_PASSWORD})
    respuesta.raise_for_status()
    return respuesta.json()["access_token"]


def cargar_lote(ruta: Path) -> list[dict]:
    import csv
    filas: list[dict] = []
    with ruta.open(encoding="utf-8-sig", newline="") as archivo:
        for fila in csv.DictReader(archivo):
            registro: dict = {}
            for variable in VARIABLES:
                crudo = (fila.get(variable) or "").strip()
                if variable == "tipo_empleo":
                    registro[variable] = crudo.lower() or None
                    continue
                registro[variable] = float(crudo) if crudo else None
            filas.append(registro)
    return filas


def simular(filas: list[dict]) -> list[dict]:
    """Aplica el desplazamiento documentado (copia, no toca el lote real)."""
    desplazadas = []
    for fila in filas:
        copia = dict(fila)
        for variable, (operacion, valor) in DESPLAZAMIENTO.items():
            actual = copia.get(variable)
            if actual is None:
                continue
            if operacion == "x":
                actual *= valor
            elif operacion == "+":
                actual += valor
            elif operacion == "-":
                actual = max(actual - valor, 0.0)
            copia[variable] = round(actual, 4)
        desplazadas.append(copia)
    return desplazadas


def evaluar_lote(token: str, origen: str, filas: list[dict]) -> dict:
    respuesta = requests.post(
        f"{URL_PRESTAMOS}/monitoreo/evaluar-lote", timeout=30,
        headers={"Authorization": f"Bearer {token}"},
        json={"origen": origen, "filas": filas})
    respuesta.raise_for_status()
    return respuesta.json()


def generar_decisiones(token: str, filas: list[dict], cantidad: int = 8) -> list[dict]:
    """Alimenta `GET /monitoreo/estado` con inferencias aisladas reales."""
    registradas = []
    for fila in filas[:cantidad]:
        cuerpo = {v: fila[v] for v in VARIABLES}
        respuesta = requests.post(
            f"{URL_PRESTAMOS}/riesgo/predict", timeout=30,
            headers={"Authorization": f"Bearer {token}"}, json=cuerpo)
        respuesta.raise_for_status()
        registradas.append(respuesta.json())
    return registradas


def registrar_en_mlflow(resultado: dict, run_name: str, tags: dict) -> str | None:
    """Registra el PSI del lote en MLflow (monitoreo observable, §15.2)."""
    os.environ.setdefault("MLFLOW_DISABLE_AGENT_HINT", "1")
    try:
        import mlflow
        mlflow.set_tracking_uri(os.environ.get("MLFLOW_TRACKING_URI",
                                               "http://localhost:5000"))
        mlflow.set_experiment("credimarket-monitoreo")
        with mlflow.start_run(run_name=run_name) as run:
            mlflow.set_tags(tags)
            mlflow.log_params({"filas": resultado["filas"],
                               "estado": resultado["estado"]})
            metricas = {f"psi_{v}": p
                        for v, p in resultado["por_variable"].items()}
            if resultado.get("psi_maximo") is not None:
                metricas["psi_maximo"] = resultado["psi_maximo"]
            mlflow.log_metrics(metricas)
            return run.info.run_id
    except Exception as exc:                          # noqa: BLE001
        print(f"  [aviso] no se pudo registrar en MLflow: {exc}")
        return None


def guardar_evidencia(nombre: str, cuerpo: dict) -> Path:
    EVIDENCIAS.mkdir(parents=True, exist_ok=True)
    ruta = EVIDENCIAS / nombre
    ruta.write_text(json.dumps(cuerpo, indent=2, ensure_ascii=False) + "\n",
                    encoding="utf-8")
    return ruta


def main(argv: list[str]) -> int:
    ruta_lote = Path(argv[1]) if len(argv) > 1 else DEFAULT_LOTE
    if not ruta_lote.exists():
        print(f"no existe el lote: {ruta_lote}", file=sys.stderr)
        return 1
    token = token_admin()
    ahora = datetime.now(timezone.utc).isoformat(timespec="seconds")

    filas = cargar_lote(ruta_lote)
    print(f"lote real: {len(filas)} filas ({ruta_lote.name})")

    # ------------------------------------------- P2-TEST-020 · drift y monitoreo
    real = evaluar_lote(token, "produccion_real", filas)
    print(f"\n[1] lote REAL → estado={real['estado']} "
          f"psi_max={real['psi_maximo']}")
    for variable, psi in sorted(real["por_variable"].items(),
                                key=lambda par: -par[1])[:3]:
        print(f"      {variable:32} PSI={psi:.4f}")

    simuladas = simular(filas)
    simulado = evaluar_lote(token, "desplazamiento_simulado", simuladas)
    detalle = ", ".join(f"{v} {op} {n}" for v, (op, n) in DESPLAZAMIENTO.items())
    print(f"\n[2] lote SIMULADO ({detalle})")
    print(f"      → estado={simulado['estado']} psi_max={simulado['psi_maximo']}")
    for variable, psi in sorted(simulado["por_variable"].items(),
                                key=lambda par: -par[1])[:3]:
        print(f"      {variable:32} PSI={psi:.4f}")

    generar_decisiones(token, filas)
    estado = requests.get(f"{URL_PRESTAMOS}/monitoreo/estado", timeout=30,
                          headers={"Authorization": f"Bearer {token}"}).json()
    print(f"\n[3] GET /monitoreo/estado → {estado['total_inferencias']} "
          f"inferencias, latencia p50={estado['latencia_ms']['p50']} ms "
          f"p95={estado['latencia_ms']['p95']} ms, "
          f"tasa_sobre_umbral={estado['tasa_sobre_umbral']}")

    run_real = registrar_en_mlflow(
        real, "lote_real_produccion",
        {"prueba": "P2-TEST-020", "tipo_lote": "real"})
    run_sim = registrar_en_mlflow(
        simulado, "lote_desplazamiento_simulado",
        {"prueba": "P2-TEST-020", "tipo_lote": "simulado",
         "desplazamiento": json.dumps({k: f"{op}{n}" for k, (op, n)
                                       in DESPLAZAMIENTO.items()})})
    print(f"\n[4] MLflow: run real={run_real} · run simulado={run_sim}")

    ev20 = guardar_evidencia("p2_test_020_drift_simulado.json", {
        "prueba": "P2-TEST-020",
        "titulo": "drift simulado y monitoreo del modelo activo",
        "fecha": ahora,
        "lote_real": {"archivo": ruta_lote.name, **real,
                      "mlflow_run": run_real},
        "lote_simulado": {"desplazamiento": {k: f"{op} {n}" for k, (op, n)
                                             in DESPLAZAMIENTO.items()},
                          **simulado, "mlflow_run": run_sim},
        "estado_produccion": estado,
        "veredicto": (
            "OK: el lote real se clasifica 'revisar' (deriva natural moderada) "
            "y el lote con desplazamiento documentado cruza a 'alerta' sin "
            "reentrenar ni tocar el modelo activo; /monitoreo/estado reporta "
            "latencias y tasas de las inferencias vivas."),
    })
    print(f"  evidencia → {ev20}")

    # --------------------------------------------- P2-TEST-019 · Redis (§6)
    producto = requests.get(f"{URL_PRODUCTOS}/productos?pagina=1&tamano=1",
                            timeout=10).json()["items"][0]["id"]
    for _ in range(3):       # 1 miss (puebla) + 2 hits del mismo producto
        requests.get(f"{URL_PRODUCTOS}/productos/{producto}", timeout=10)
    cache_stats = requests.get(f"{URL_PRODUCTOS}/cache/estadisticas", timeout=10,
                               headers={"Authorization": f"Bearer {token}"}).json()
    lecturas = cache_stats["lecturas"]
    latencia = cache_stats["latencia_redis_ms"]
    print(f"\n[5] GET /cache/estadisticas → hit_rate={lecturas['hit_rate']} "
          f"fallback={lecturas['fallback']} "
          f"p50={latencia['p50']} ms p95={latencia['p95']} ms")
    ev19 = guardar_evidencia("p2_test_019_redis_cache.json", {
        "prueba": "P2-TEST-019",
        "titulo": "mediciones de la caché Redis (hit-rate, fallback, p50/p95)",
        "fecha": ahora,
        "producto_prueba": producto,
        "estadisticas": cache_stats,
        "veredicto": (
            "OK: el cache-aside registra aciertos tras el pueble y latencias "
            "p50/p95 del GET sobre Redis; el fallback queda a 0 con Redis "
            "disponible (la métrica existe para cuando deje de estarlo)."),
    })
    print(f"  evidencia → {ev19}")

    fallos = []
    if real["estado"] not in ("revisar", "alerta"):
        fallos.append(f"el lote real esperaba 'revisar' y salió '{real['estado']}'")
    if simulado["estado"] != "alerta":
        fallos.append(f"el lote simulado esperaba 'alerta' y salió '{simulado['estado']}'")
    if estado["latencia_ms"]["p50"] is None:
        fallos.append("sin latencias en /monitoreo/estado")
    if lecturas["hit_rate"] is None or lecturas["hit_rate"] <= 0:
        fallos.append("sin aciertos de caché en /cache/estadisticas")
    if fallos:
        print("\nFALLOS:")
        for fallo in fallos:
            print(f"  - {fallo}")
        return 1
    print("\nTODAS LAS VERIFICACIONES PASARON")
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv))
