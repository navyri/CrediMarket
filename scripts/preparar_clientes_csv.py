"""Deriva un CSV de clientes desde el histórico `prestamos_entrenamiento.csv`.

§9 permite adaptar los campos del archivo histórico. Aquí `cliente_id` se
convierte en `documento_identidad` (P2-SUP-006) y los demás datos son de
demostración, sin información personal real. Además, el perfil financiero del
cliente (P2-7) viaja en las mismas columnas del histórico: el cliente es el
dueño de esos datos y el servicio Clientes los almacena.

Uso:
    python scripts/preparar_clientes_csv.py ruta/al/prestamos_entrenamiento.csv salida/clientes.csv
"""
import csv
import sys
from pathlib import Path

COLUMNAS_PERFIL = [
    "ingresos_mensuales_cop", "obligaciones_mensuales_cop", "tipo_empleo",
    "antiguedad_laboral_meses", "meses_historial_crediticio",
    "creditos_previos", "atrasos_previos_30d", "porcentaje_pago_puntual",
]
COLUMNAS_SALIDA = ["documento_identidad", "nombre", "email", "telefono",
                   "ciudad", "activo", *COLUMNAS_PERFIL]


def derivar(entrada: Path, salida: Path) -> tuple[int, int]:
    vistos: set[str] = set()
    filas = 0
    with entrada.open(encoding="utf-8-sig", newline="") as origen, \
            salida.open("w", encoding="utf-8", newline="") as destino:
        escritor = csv.DictWriter(destino, fieldnames=COLUMNAS_SALIDA)
        escritor.writeheader()
        for fila in csv.DictReader(origen):
            documento = (fila.get("cliente_id") or "").strip()
            if not documento or documento in vistos:
                continue
            vistos.add(documento)
            registro = {
                "documento_identidad": documento,
                "nombre": f"Cliente {documento}",
                "email": f"{documento.lower()}@credimarket.demo",
                "telefono": "",
                "ciudad": "",
                "activo": "true",
            }
            # El perfil viaja tal cual del histórico (los vacíos quedan vacíos:
            # el servicio los convierte en None y el imputador los absorbe).
            for columna in COLUMNAS_PERFIL:
                registro[columna] = (fila.get(columna) or "").strip()
            escritor.writerow(registro)
            filas += 1
    return filas, len(vistos)


def main() -> int:
    if len(sys.argv) != 3:
        print(__doc__)
        return 2
    entrada, salida = Path(sys.argv[1]), Path(sys.argv[2])
    if not entrada.exists():
        print(f"no existe el archivo: {entrada}")
        return 1
    salida.parent.mkdir(parents=True, exist_ok=True)
    escritas, unicos = derivar(entrada, salida)
    print(f"{escritas} filas escritas ({unicos} clientes únicos) → {salida}")
    return 0


if __name__ == "__main__":
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    raise SystemExit(main())
