"""Deriva un CSV de clientes desde el histórico `prestamos_entrenamiento.csv`.

§9 permite adaptar los campos del archivo histórico. Aquí `cliente_id` se
convierte en `documento_identidad` (P2-SUP-006) y los demás datos son de
demostración, sin información personal real.

Uso:
    python scripts/preparar_clientes_csv.py ruta/al/prestamos_entrenamiento.csv salida/clientes.csv
"""
import csv
import sys
from pathlib import Path

COLUMNAS_SALIDA = ["documento_identidad", "nombre", "email", "telefono", "ciudad", "activo"]


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
            escritor.writerow({
                "documento_identidad": documento,
                "nombre": f"Cliente {documento}",
                "email": f"{documento.lower()}@credimarket.demo",
                "telefono": "",
                "ciudad": "",
                "activo": "true",
            })
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
