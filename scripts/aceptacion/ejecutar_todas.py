"""Orquestador de las 16 pruebas de aceptación de §12.

Corre `caso_01.py` … `caso_16.py` en orden (los casos 6, 8 y 16 detienen y
levantan infraestructura, por eso son SECUENCIALES), recoge cada evidencia
`docs/evidencias/aceptacion/caso_NN.json` y escribe `resultados.json`.

Uso:  python scripts/aceptacion/ejecutar_todas.py
Salida: 0 si las 16 pasan; 1 en caso contrario.
"""
import json
import subprocess
import sys
import time
from pathlib import Path

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")

RAIZ = Path(__file__).resolve().parents[2]
ACEPTACION = Path(__file__).resolve().parent
EVIDENCIAS = RAIZ / "docs" / "evidencias" / "aceptacion"
PY = sys.executable or "python"

CASOS = {
    1: "Riesgo favorable con existencias",
    2: "Solicitud rechazada",
    3: "Riesgo favorable sin existencias",
    4: "Dos solicitudes por la última unidad",
    5: "Misma petición y mismo evento repetidos",
    6: "Caída del consumidor o del broker",
    7: "Cancelación y evento tardío",
    8: "Redis vacío, expirado o caído",
    9: "Precio modificado",
    10: "Modelo exportado vs. API",
    11: "Promoción y rollback",
    12: "Importar CSV dos veces",
    13: "Préstamos ajenos",
    14: "Flujo desde frontend",
    15: "Pendiente y actualización asíncrona",
    16: "Formulario inválido / sesión vencida / API caída",
}


def main() -> int:
    resultados = []
    inicio_total = time.time()
    print("=" * 78)
    print("Pruebas de aceptación §12 — CrediMarket (P2)")
    print("=" * 78)

    for n, titulo in CASOS.items():
        script = ACEPTACION / f"caso_{n:02d}.py"
        evidencia = EVIDENCIAS / f"caso_{n:02d}.json"
        evidencia.unlink(missing_ok=True)      # no vale evidencia de un pase anterior
        inicio = time.time()
        print(f"\n--- Caso {n:02d}: {titulo}")
        try:
            proc = subprocess.run([PY, str(script)], cwd=RAIZ,
                                  capture_output=True, text=True,
                                  encoding="utf-8", errors="replace",
                                  timeout=600)
            salida = (proc.stdout or "") + (proc.stderr or "")
            codigo = proc.returncode
        except subprocess.TimeoutExpired:
            salida, codigo = "TIMEOUT (600 s)", 124
        duracion = round(time.time() - inicio, 1)

        evid = None
        if evidencia.exists():
            try:
                evid = json.loads(evidencia.read_text(encoding="utf-8"))
            except (OSError, json.JSONDecodeError):
                evid = None
        ok = codigo == 0 and evid is not None and evid.get("estado") == "OK"
        resultados.append({
            "caso": n, "id": f"P2-TEST-{n:03d}", "titulo": titulo,
            "estado": "OK" if ok else "FALLO", "duracion_s": duracion,
            "exit_code": codigo,
            "observado": (evid or {}).get("observado", salida.strip()[-600:]),
            "evidencia": str(evidencia.relative_to(RAIZ)) if evidencia.exists() else None,
        })
        for linea in salida.strip().splitlines():
            print(f"    {linea}")
        print(f"    → {'OK' if ok else 'FALLO'} ({duracion}s)")

    ok_total = sum(1 for r in resultados if r["estado"] == "OK")
    resumen = {
        "total": len(resultados), "ok": ok_total,
        "fallos": len(resultados) - ok_total,
        "duracion_total_s": round(time.time() - inicio_total, 1),
        "ejecutado_en": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        "resultados": resultados,
    }
    ruta = EVIDENCIAS / "resultados.json"
    ruta.write_text(json.dumps(resumen, ensure_ascii=False, indent=2),
                    encoding="utf-8")

    print("\n" + "=" * 78)
    print(f"RESULTADO: {ok_total}/{len(resultados)} casos OK  "
          f"({resumen['duracion_total_s']}s)")
    print(f"Evidencias: {ruta.relative_to(RAIZ)}")
    for r in resultados:
        marca = "✓" if r["estado"] == "OK" else "✗"
        print(f"  {marca} {r['id']} · {r['titulo']}")
    print("=" * 78)
    return 0 if ok_total == len(resultados) else 1


if __name__ == "__main__":
    sys.exit(main())
