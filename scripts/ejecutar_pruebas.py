"""Ejecuta las pruebas de cada servicio en procesos separados.

Motivo: los cuatro microservicios comparten el nombre de paquete `app`; si
pytest recorre dos servicios en el mismo proceso, el primero en importar gana.
Cada servicio se prueba aislado (igual que corre en su propio contenedor).

Uso:  python scripts/ejecutar_pruebas.py [--solo-unidad]
"""
import argparse
import subprocess
import sys
from pathlib import Path

RAIZ = Path(__file__).resolve().parents[1]

CONJUNTOS = [
    ("productos · unitarias (mocks declarados)", ["servicios/productos/tests/test_productos_unit.py"]),
    ("productos · integración (PG + Redis reales)", ["servicios/productos/tests/integracion"]),
    ("clientes · unitarias (mocks declarados)", ["servicios/clientes/tests/test_clientes_unit.py"]),
    ("clientes · integración (PG real)", ["servicios/clientes/tests/integracion"]),
    ("inventario · unitarias (mocks declarados)", ["servicios/inventario/tests/test_inventario_unit.py"]),
    ("inventario · integración (RabbitMQ + PG reales)", ["servicios/inventario/tests/integracion"]),
    ("prestamos · unitarias (mocks declarados)", ["servicios/prestamos/tests/test_prestamos_unit.py"]),
    ("prestamos · monitoreo unitarias (PSI, línea base, latencias)", ["servicios/prestamos/tests/test_prestamos_monitoreo_unit.py"]),
    ("prestamos · integración (RabbitMQ + PG + modelo real)", ["servicios/prestamos/tests/integracion"]),
]


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--solo-unidad", action="store_true",
                        help="omite las pruebas que requieren docker compose up -d")
    args = parser.parse_args()

    resultados = []
    for nombre, destinos in CONJUNTOS:
        if args.solo_unidad and "integración" in nombre:
            continue
        cmd = [sys.executable, "-m", "pytest", "-q", *destinos]
        print(f"\n=== {nombre} ===", flush=True)
        proc = subprocess.run(cmd, cwd=RAIZ)
        resultados.append((nombre, proc.returncode))

    print("\n=== resumen ===")
    fallos = 0
    for nombre, codigo in resultados:
        estado = "OK" if codigo == 0 else f"FALLO ({codigo})"
        print(f"  [{estado}] {nombre}")
        fallos += 1 if codigo else 0
    return 1 if fallos else 0


if __name__ == "__main__":
    raise SystemExit(main())
