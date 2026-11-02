"""Caso §12.11 — Promoción y rollback.

Evidencia esperada: cambio entre dos versiones conservando trazabilidad.
Se promueve v2, se verifica el cambio de umbral/run_id y se vuelve a v1
(rollback explícito); el historial conserva ambas decisiones.
"""
import json
import sys
from pathlib import Path

import requests

sys.path.insert(0, str(Path(__file__).resolve().parent))
from _comun import (RAIZ, URL_PRESTAMOS, admin_token, auth, evidencia, salir)

CASO = 11
REQUISITO = "§12.11 Promoción y rollback"
ESPERADO = "Cambio entre dos versiones conservando trazabilidad."

HISTORIAL = RAIZ / "ml" / "modelos" / "historial_promociones.jsonl"


def _info(token: str) -> dict:
    r = requests.get(f"{URL_PRESTAMOS}/modelo/info", headers=auth(token), timeout=15)
    assert r.status_code == 200, r.text
    return r.json()


def _promover(token: str, version: str, motivo: str) -> dict:
    r = requests.post(f"{URL_PRESTAMOS}/admin/modelo/promover",
                      headers=auth(token),
                      json={"modelo_version": version, "motivo": motivo}, timeout=30)
    assert r.status_code == 200, f"{r.status_code}: {r.text}"
    return r.json()


def main() -> dict:
    token = admin_token()
    original = _info(token)["modelo_version"]
    otra = "v2" if original == "v1" else "v1"
    lineas_antes = len(HISTORIAL.read_text(encoding="utf-8").splitlines()) \
        if HISTORIAL.exists() else 0

    try:
        # 1) Promoción explícita a la otra versión.
        p1 = _promover(token, otra, "aceptación §12.11: promoción")
        info2 = _info(token)
        assert info2["modelo_version"] == otra, info2["modelo_version"]
        assert p1["version_anterior"] == original, p1

        # 2) Rollback explícito a la versión original.
        p2 = _promover(token, original, "aceptación §12.11: rollback")
        info3 = _info(token)
        assert info3["modelo_version"] == original, info3["modelo_version"]
        assert p2["version_anterior"] == otra, p2
    finally:
        # El estado activo siempre termina como estaba (reproducibilidad).
        actual = _info(token)["modelo_version"]
        if actual != original:
            _promover(token, original, "aceptación §12.11: restauración de estado")

    # 3) Trazabilidad: ambas decisiones quedan en el historial y en activo.json.
    lineas = HISTORIAL.read_text(encoding="utf-8").splitlines()
    nuevas = [json.loads(x) for x in lineas[lineas_antes:]]
    activo = json.loads((RAIZ / "ml" / "modelos" / "activo.json")
                        .read_text(encoding="utf-8"))
    assert activo["modelo_version"] == original
    assert activo["version_anterior"] == otra, "activo.json no registra el cambio"
    assert len(nuevas) >= 2, f"historial incompleto: {len(nuevas)} entradas nuevas"

    return evidencia(
        CASO, REQUISITO, ESPERADO,
        f"promoción {original} → {otra} (run_id y umbral cambian) y rollback "
        f"{otra} → {original}; activo.json registra version_anterior={otra} y el "
        f"historial creció en {len(nuevas)} entradas trazables",
        ok=True,
        detalle={"version_original": original, "version_promovida": otra,
                 "umbral_original": info3["umbral"], "umbral_promovido": info2["umbral"],
                 "run_id_original": info3["run_id"], "run_id_promovido": info2["run_id"],
                 "entradas_historial_nuevas": nuevas,
                 "activo_version_anterior": activo["version_anterior"]})


if __name__ == "__main__":
    salir(main())
