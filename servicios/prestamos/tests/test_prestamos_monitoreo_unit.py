"""Pruebas UNITARIAS del módulo de monitoreo de Préstamos (P2-9, §15.2).

Dobles declarados: las sesiones y la línea base son MOCKS/diccionarios
construidos a mano; nada de este archivo toca PostgreSQL, Redis ni el CSV.
"""
import sys
from decimal import Decimal
from pathlib import Path
from unittest.mock import MagicMock, patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app import monitoreo                             # noqa: E402
from app.models import MetricaInferencia              # noqa: E402

# Línea base mínima: 4 cuartiles iguales + categorías 50/50.
REFERENCIA = {
    "numericas": {
        "ingresos_mensuales_cop": {
            "bordes": [1000.0, 2000.0, 3000.0],
            "proporciones": [0.25, 0.25, 0.25, 0.25],
        },
    },
    "categoricas": {
        "tipo_empleo": {"proporciones": {"dependiente": 0.5,
                                         "independiente": 0.5}},
    },
}


def _lote_equilibrado(n: int = 40) -> list[dict]:
    """Filas con la MISMA distribución que la línea base → PSI = 0."""
    valores = [500.0, 1500.0, 2500.0, 4000.0]
    categorias = ["dependiente", "independiente"]
    return [{"ingresos_mensuales_cop": valores[i % 4],
             "tipo_empleo": categorias[i % 2]} for i in range(n)]


# ------------------------------------------------------------------------ PSI
def test_psi_cero_con_la_misma_distribucion_unit():
    resultado = monitoreo.psi_lote(REFERENCIA, _lote_equilibrado(40))
    assert resultado["psi_maximo"] == 0.0
    assert resultado["estado"] == "estable"
    assert resultado["filas"] == 40


def test_psi_detecta_desplazamiento_total_unit():
    """Todas las filas fuera de la distribución base → alerta (§15.2)."""
    desplazado = [{"ingresos_mensuales_cop": 9000.0,
                   "tipo_empleo": "dependiente"} for _ in range(40)]
    resultado = monitoreo.psi_lote(REFERENCIA, desplazado)
    assert resultado["estado"] == "alerta"
    assert resultado["psi_maximo"] >= monitoreo.UMBRAL_ALERTA
    assert "ingresos_mensuales_cop" in resultado["variables_con_alerta"]


def test_psi_categoria_vacia_no_inventa_una_categoria_unit():
    """Regresión: los vacíos van a `desconocido`; no se descartan ni crean NA.

    20 `dependiente` + 20 vacíos contra {dependiente .4, independiente .4,
    desconocido .2} → (0.5−0.4)·ln1.25 + (1e−6−0.4)·ln2.5e−6 +
    (0.5−0.2)·ln2.5 = 5.4569. Si los vacíos se descartaran saldría 8.15.
    """
    referencia = {"numericas": {},
                  "categoricas": {"tipo_empleo": {"proporciones": {
                      "dependiente": 0.4, "independiente": 0.4,
                      "desconocido": 0.2}}}}
    filas = ([{"tipo_empleo": "dependiente"}] * 20
             + [{"tipo_empleo": None}] * 20)
    resultado = monitoreo.psi_lote(referencia, filas)
    assert abs(resultado["por_variable"]["tipo_empleo"] - 5.4569) < 0.001


def test_lote_pequeno_se_clasifica_insuficiente_unit():
    """< 30 filas: el PSI se informa pero no se clasifica (ruido de corte)."""
    desplazado = [{"ingresos_mensuales_cop": 9000.0,
                   "tipo_empleo": "dependiente"} for _ in range(10)]
    resultado = monitoreo.psi_lote(REFERENCIA, desplazado)
    assert resultado["estado"] == "insuficiente"
    assert resultado["psi_maximo"] is not None      # el número se reporta


def test_lote_vacio_y_sin_referencia_unit():
    assert monitoreo.psi_lote(REFERENCIA, [])["estado"] == "sin_datos"
    assert monitoreo.psi_lote(None, _lote_equilibrado())["estado"] == "sin_referencia"


def test_clasificacion_de_umbrales_unit():
    assert monitoreo._clasificar(0.05) == "estable"
    assert monitoreo._clasificar(monitoreo.UMBRAL_REVISAR) == "revisar"
    assert monitoreo._clasificar(monitoreo.UMBRAL_ALERTA) == "alerta"
    assert monitoreo._clasificar(None) == "sin_datos"


# --------------------------------------------------------------- percentiles
def test_percentil_lineal_unit():
    valores = [1.0, 2.0, 3.0, 4.0, 10.0]
    assert monitoreo.percentil(valores, 0.5) == 3.0
    assert monitoreo.percentil(valores, 1.0) == 10.0
    assert monitoreo.percentil(valores, 0.0) == 1.0
    assert monitoreo.percentil([7.0], 0.9) == 7.0
    assert monitoreo.percentil([], 0.5) is None


# --------------------------------------------------------------- registro vivo
def test_registrar_no_hace_commit_y_convierte_decimal_unit():
    """La métrica se AÑADE a la transacción del préstamo (sin commit aquí)."""
    sesion = MagicMock()
    metrica = monitoreo.registrar(
        sesion, origen="solicitud", prestamo_id="PRE-1",
        variables={"ingresos_mensuales_cop": Decimal("2500000.50"),
                   "tipo_empleo": None, "_secreto": "no"},
        probabilidad=0.21, umbral=0.49, aplico_regla=False,
        latencia_ms=3.214159, modelo_version="v1")
    sesion.add.assert_called_once_with(metrica)
    sesion.commit.assert_not_called()
    assert metrica.variables == {"ingresos_mensuales_cop": 2500000.5,
                                 "tipo_empleo": None}
    assert metrica.latencia_ms == 3.214
    assert metrica.origen == "solicitud" and metrica.aplico_regla is False


# ------------------------------------------------------------------- estado
def _metrica(**extras) -> MetricaInferencia:
    base = dict(origen="inferencia", prestamo_id=None, modelo_version="v1",
                probabilidad=0.3, umbral=0.49, aplico_regla=False,
                latencia_ms=2.0,
                variables={"ingresos_mensuales_cop": 1500.0,
                           "tipo_empleo": "dependiente"})
    base.update(extras)
    return MetricaInferencia(**base)


def test_estado_sin_inferencias_unit():
    sesion = MagicMock()
    sesion.scalars.return_value.all.return_value = []
    with patch.object(monitoreo, "cargar_referencia", return_value=None):
        resultado = monitoreo.estado(sesion)
    assert resultado["total_inferencias"] == 0
    assert resultado["estado"] == "sin_datos"
    assert resultado["linea_base"] is None


def test_estado_resume_latencias_tasas_y_regla_unit():
    filas = [
        _metrica(latencia_ms=1.0, probabilidad=0.1),
        _metrica(latencia_ms=2.0, probabilidad=0.6, aplico_regla=False),
        _metrica(latencia_ms=10.0, probabilidad=1.0, aplico_regla=True,
                 modelo_version="v2"),
    ]
    sesion = MagicMock()
    sesion.scalars.return_value.all.return_value = filas
    with patch.object(monitoreo, "cargar_referencia", return_value=None):
        resultado = monitoreo.estado(sesion)
    assert resultado["ventana"] == 3
    assert resultado["modelo_version"] == "v1"        # la más reciente
    assert resultado["latencia_ms"]["p50"] == 2.0
    assert abs(resultado["latencia_ms"]["p95"] - 9.2) < 1e-9
    assert resultado["aplicaron_regla"] == 1
    assert abs(resultado["tasa_sobre_umbral"] - 2 / 3) < 1e-4   # (redondeo a 4)
    assert abs(resultado["probabilidad_media"] - 0.5667) < 1e-4   # (0.1+0.6+1.0)/3
    assert resultado["deriva"]["estado"] == "sin_referencia"
