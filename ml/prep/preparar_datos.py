"""P2-5 · Preparación de datos para el modelo de `incumplimiento_90d`.

Reglas aplicadas (§8.A–§8.B):
- el preprocesamiento se ajusta SOLO con el conjunto de entrenamiento (la
  imputación y la codificación viven dentro del `Pipeline`, y aquí únicamente
  se fijan las particiones);
- las columnas de identificadores (`solicitud_id`, `cliente_id`), la etiqueta
  y `tasa_mensual_simulada` (constante en todo el histórico) quedan fuera de
  las variables predictorias;
- división estratificada 60/20/20 con semilla fija (RANDOM_SEED=42).

Uso:
    python ml/prep/preparar_datos.py [--entrada ruta/al/prestamos_entrenamiento.csv]
                                      [--salida ml/datos]

Sin `--entrada` el script localiza el CSV (variable de entorno
`CREDIMARKET_CSV_ENTRENAMIENTO`, raíz del clon, `ml/datos/` o `datos_fuente/`);
si no lo encuentra explica cómo pasarlo (§13.7).
"""
import argparse
import hashlib
import json
import sys
from pathlib import Path

import pandas as pd

RAIZ = Path(__file__).resolve().parents[2]
SALIDA_DEFECTO = RAIZ / "ml" / "datos"

# El CSV crudo no se versiona (§13.2: datos fuera del repo, hash documentados).
# La ruta por defecto NO puede estar atada a una máquina concreta, así que se
# buscan candidatas en orden y, si ninguna existe, se pide `--entrada`.
# Orden: variable de entorno → raíz del clon → ml/datos → datos_fuente.
CANDIDATAS_ENTRADA = (
    None,                                        # CREDIMARKET_CSV_ENTRENAMIENTO
    RAIZ / "prestamos_entrenamiento.csv",
    RAIZ / "ml" / "datos" / "prestamos_entrenamiento.csv",
    RAIZ / "datos_fuente" / "prestamos_entrenamiento.csv",
)
NOMBRE_CSV = "prestamos_entrenamiento.csv"


def buscar_entrada(explicita: Path | None) -> Path:
    """Resuelve el histórico: lo que venga en `--entrada` manda; si no, la
    primera candidata existente. Con nada disponible, sale con instrucciones
    claras (reproducción §13.7: sin datos no hay modelo)."""
    if explicita is not None:
        return explicita
    import os
    env = os.environ.get("CREDIMARKET_CSV_ENTRENAMIENTO")
    if env:
        return Path(env)
    for candidata in CANDIDATAS_ENTRADA[1:]:
        if candidata.exists():
            return candidata
    raise SystemExit(
        f"No se encontró {NOMBRE_CSV}.\n"
        f"  · el CSV crudo no se versiona en git (solo su hash SHA-256);\n"
        f"  · pásalo con:  python ml/prep/preparar_datos.py --entrada \"ruta/al/{NOMBRE_CSV}\"\n"
        f"  · o define:    CREDIMARKET_CSV_ENTRENAMIENTO=ruta/al/{NOMBRE_CSV}\n"
        f"  · o cópialo a: {RAIZ / NOMBRE_CSV}"
    )

OBJETIVO = "incumplimiento_90d"
EXCLUIDAS = ["solicitud_id", "cliente_id", OBJETIVO, "tasa_mensual_simulada"]
SEMILLA = 42
PROPORCIONES = {"entrenamiento": 0.6, "validacion": 0.2, "prueba": 0.2}


def sha256(ruta: Path) -> str:
    resumen = hashlib.sha256()
    with ruta.open("rb") as archivo:
        for bloque in iter(lambda: archivo.read(1 << 20), b""):
            resumen.update(bloque)
    return resumen.hexdigest()


def preparar(entrada: Path, salida: Path) -> dict:
    if not entrada.exists():
        raise SystemExit(f"no existe el archivo de entrenamiento: {entrada}")

    df = pd.read_csv(entrada)
    faltantes = {OBJETIVO, *EXCLUIDAS} - set(df.columns)
    if faltantes:
        raise SystemExit(f"faltan columnas requeridas: {sorted(faltantes)}")

    n_antes = len(df)
    df = df.drop_duplicates()
    df = df[df[OBJETIVO].isin([0, 1])]
    descartadas_filas = n_antes - len(df)

    variables = [c for c in df.columns if c not in EXCLUIDAS]
    constantes = [c for c in variables if df[c].nunique(dropna=False) <= 1]
    # Las variables sin variación no aportan y se retiran del modelado.
    variables_modelo = [c for c in variables if c not in constantes]

    train, val, test = _dividir_estratificado(df)

    salida.mkdir(parents=True, exist_ok=True)
    train.to_csv(salida / "entrenamiento.csv", index=False)
    val.to_csv(salida / "validacion.csv", index=False)
    test.to_csv(salida / "prueba.csv", index=False)

    ficha = {
        "fuente": entrada.name,   # sin ruta absoluta (no expone la máquina)
        "sha256_fuente": sha256(entrada),
        "filas_origen": n_antes,
        "filas_descartadas": descartadas_filas,
        "objetivo": OBJETIVO,
        "excluidas": EXCLUIDAS,
        "variables_constantemente_descartadas": constantes,
        "variables_modelo": variables_modelo,
        "proporciones": PROPORCIONES,
        "semilla": SEMILLA,
        "conteos": {
            "entrenamiento": len(train),
            "validacion": len(val),
            "prueba": len(test),
        },
        "tasa_positivos": {
            "total": float(df[OBJETIVO].mean()),
            "entrenamiento": float(train[OBJETIVO].mean()),
            "validacion": float(val[OBJETIVO].mean()),
            "prueba": float(test[OBJETIVO].mean()),
        },
        "nulos_por_columna": {k: int(v) for k, v in df.isna().sum().items() if v},
        "semilla_estratificacion": SEMILLA,
    }
    (salida / "ficha_datos.json").write_text(
        json.dumps(ficha, indent=2, ensure_ascii=False), encoding="utf-8")
    return ficha


def _dividir_estratificados_sin_fuga(df: pd.DataFrame) -> tuple[pd.DataFrame, ...]:
    """División por capas: primero 80/20 (prueba), luego 75/25 (validación)."""
    prueba = df.groupby(OBJETIVO, group_keys=False).sample(
        frac=PROPORCIONES["prueba"], random_state=SEMILLA)
    resto = df.drop(prueba.index)
    validacion = resto.groupby(OBJETIVO, group_keys=False).sample(
        frac=PROPORCIONES["validacion"] / (1 - PROPORCIONES["prueba"]),
        random_state=SEMILLA)
    entrenamiento = resto.drop(validacion.index)
    return entrenamiento, validacion, prueba


_dividir_estratificado = _dividir_estratificados_sin_fuga


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--entrada", type=Path, default=None,
                        help=f"ruta al {NOMBRE_CSV} (si se omite, se busca "
                             "automáticamente o en CREDIMARKET_CSV_ENTRENAMIENTO)")
    parser.add_argument("--salida", type=Path, default=SALIDA_DEFECTO)
    args = parser.parse_args()

    entrada = buscar_entrada(args.entrada)
    ficha = preparar(entrada, args.salida)
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    print(json.dumps(ficha, indent=2, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
