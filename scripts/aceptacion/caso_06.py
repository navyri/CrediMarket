"""Caso §12.6 — Caída del consumidor o del broker.

Evidencia esperada: recuperación sin perder solicitudes confirmadas ni duplicar
efectos. Se detiene RabbitMQ, se crea una solicitud (queda en outbox), se
levanta el broker y el préstamo llega a APROBADA con UNA sola reserva.
"""
import subprocess
import sys
import time
from pathlib import Path

import requests

sys.path.insert(0, str(Path(__file__).resolve().parent))
from _comun import (RAIZ, URL_INVENTARIO, admin_token, auth, crear_producto,
                    esperar_estado, evidencia, existencia, registrar_cliente,
                    solicitar, salir)

CASO = 6
REQUISITO = "§12.6 Caída del consumidor o del broker"
ESPERADO = "Recuperación sin perder solicitudes confirmadas ni duplicar efectos."


def _compose(*args: str) -> subprocess.CompletedProcess:
    return subprocess.run(["docker", "compose", *args], cwd=RAIZ,
                          capture_output=True, text=True, timeout=300)


def main() -> dict:
    cliente = registrar_cliente(bueno=True)
    producto = crear_producto(precio=175_000, stock=3)
    antes = existencia(producto)
    token_admin = admin_token()
    traza = []

    apagado = False
    try:
        # 1) Broker caído.
        _compose("stop", "rabbitmq")
        apagado = True
        time.sleep(3)

        # 2) La solicitud se ACEPTA (202) y persiste vía outbox, sin broker.
        r = solicitar(cliente["cliente_id"], producto, token=cliente["token"])
        assert r.status_code == 202, f"con broker caído debió aceptar: {r.status_code}"
        prestamo_id = r.json()["prestamo_id"]
        time.sleep(5)
        parcial = requests.get(f"http://localhost:8003/prestamos/{prestamo_id}",
                               headers=auth(token_admin), timeout=15).json()
        traza.append(parcial["estado"])
        assert parcial["estado"] == "PENDIENTE_INVENTARIO", \
            f"sin broker no pudo confirmarse: {parcial['estado']}"

        # 3) Recuperación: se levanta el broker y el relay/consumidor reanudan.
        _compose("start", "rabbitmq")
        apagado = False
        prestamo, traza_poll = esperar_estado(prestamo_id,
                                              estados={"APROBADA", "RECHAZADA",
                                                       "CANCELADA_SIN_STOCK"},
                                              timeout=120)
        traza += traza_poll
        assert prestamo["estado"] == "APROBADA", prestamo["estado"]

        # 4) Sin efectos duplicados: una sola reserva y stock coherente.
        reservas = requests.get(f"{URL_INVENTARIO}/reservas?limite=100",
                                headers=auth(token_admin), timeout=15).json()
        mias = [x for x in reservas if x["prestamo_id"] == prestamo_id]
        assert len(mias) == 1, f"efectos duplicados: {len(mias)} reservas"
        assert mias[0]["estado"] == "RESERVADA"
        stock = existencia(producto)
        assert stock["reservada"] == antes["reservada"] + 1, stock
        assert stock["disponible"] == antes["disponible"] - 1, stock

        return evidencia(
            CASO, REQUISITO, ESPERADO,
            f"broker detenido → solicitud 202 persistida en PENDIENTE_INVENTARIO; "
            f"al reiniciar RabbitMQ llegó a APROBADA con 1 sola reserva "
            f"({mias[0]['id'][:8]}…) y stock coherente (reservada "
            f"{antes['reservada']} → {stock['reservada']}); traza "
            f"{'→'.join(traza)}",
            ok=True,
            detalle={"prestamo_id": prestamo_id, "reserva_id": mias[0]["id"],
                     "traza_estados": traza, "stock_antes": antes,
                     "stock_despues": stock, "reservas_del_prestamo": len(mias)})
    finally:
        if apagado:   # la infraestructura siempre queda levantada
            _compose("start", "rabbitmq")


if __name__ == "__main__":
    salir(main())
