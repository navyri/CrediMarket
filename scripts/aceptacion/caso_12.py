"""Caso §12.12 — Importar CSV dos veces.

Evidencia esperada: la 2.ª importación no inserta ni actualiza (idempotente),
con resumen de contadores y errores por fila; el directorio no duplica clientes.
"""
import io
import sys
import uuid
from pathlib import Path

import requests

sys.path.insert(0, str(Path(__file__).resolve().parent))
from _comun import (URL_CLIENTES, admin_token, auth, evidencia, salir)

CASO = 12
REQUISITO = "§12.12 Importar CSV dos veces"
ESPERADO = "0 insertados/actualizados en la 2.ª importación; sin duplicar clientes."


def _csv() -> bytes:
    """CSV adaptado del histórico (§9) con 3 filas válidas y 1 inválida."""
    suf = uuid.uuid4().hex[:8]
    filas = [
        "documento_identidad,nombre,email,ingresos_mensuales_cop,"
        "obligaciones_mensuales_cop,tipo_empleo,antiguedad_laboral_meses,"
        "meses_historial_crediticio,creditos_previos,atrasos_previos_30d,"
        "porcentaje_pago_puntual",
    ]
    for i in range(3):
        filas.append(
            f"ACEP-CSV-{suf}-{i},Cliente CSV {suf}-{i},csv-{suf}-{i}@demo.local,"
            f"3000000,400000,dependiente,24,36,1,0,92")
    filas.append(f"ACEP-CSV-{suf}-X,,sin-nombre-{suf}@demo.local,,,,,,,")   # inválida
    return "\n".join(filas).encode("utf-8")


def main() -> dict:
    token = admin_token()
    contenido = _csv()

    def importar() -> dict:
        r = requests.post(f"{URL_CLIENTES}/clientes/import",
                          headers=auth(token),
                          files={"file": ("clientes_aceptacion.csv", contenido,
                                          "text/csv")}, timeout=60)
        assert r.status_code == 200, f"{r.status_code}: {r.text}"
        return r.json()

    # Total de clientes antes de importar (para demostrar que no se duplican).
    antes = requests.get(f"{URL_CLIENTES}/clientes?pagina=1&tamano=1",
                         headers=auth(token), timeout=15).json()["total"]

    primera = importar()
    assert primera["insertados"] == 3, primera
    assert primera["rechazadas"] == 1, primera
    assert any("nombre" in e["motivo"] for e in primera["errores"]), \
        "sin motivo por fila para la fila inválida"

    # 2.ª importación del MISMO archivo: idempotente.
    segunda = importar()
    assert segunda["insertados"] == 0 and segunda["actualizados"] == 0, segunda
    assert segunda["sin_cambios"] == 3, segunda
    assert segunda["rechazadas"] == 1, segunda

    despues = requests.get(f"{URL_CLIENTES}/clientes?pagina=1&tamano=1",
                           headers=auth(token), timeout=15).json()["total"]
    assert despues == antes + 3, \
        f"clientes duplicados: {antes} → {despues} (esperado +3)"

    return evidencia(
        CASO, REQUISITO, ESPERADO,
        f"1.ª importación → {primera['insertados']} insertadas + "
        f"{primera['rechazadas']} rechazadas con motivo por fila; 2.ª → "
        f"0 insertadas/0 actualizadas/{segunda['sin_cambios']} sin cambios; "
        f"directorio {antes} → {despues} clientes (+3, sin duplicados)",
        ok=True,
        detalle={"primera": primera, "segunda": segunda,
                 "clientes_antes": antes, "clientes_despues": despues})


if __name__ == "__main__":
    salir(main())
