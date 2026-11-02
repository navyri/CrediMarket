"""Esquemas Pydantic del servicio Préstamos (§4: el cliente no envía precio)."""
from datetime import datetime
from decimal import Decimal

from pydantic import BaseModel, ConfigDict, Field


class SolicitudCreacion(BaseModel):
    # §4: el cliente NUNCA envía precio, monto ni tasa; los campos extra se
    # rechazan (no se ignoran en silencio) para que el contrato sea explícito.
    model_config = ConfigDict(extra="forbid")

    cliente_id: str = Field(min_length=1, max_length=36)
    producto_id: str = Field(min_length=1, max_length=36)
    cantidad: int = Field(gt=0, le=1000)
    plazo_meses: int = Field(ge=1, le=60)


class PrestamoLectura(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    cliente_id: str
    producto_id: str
    cantidad: int
    plazo_meses: int
    precio_unitario_cop: Decimal
    precio_producto_version: int
    monto_total_cop: Decimal
    cuota_mensual_cop: Decimal
    tasa_mensual: float
    probabilidad_incumplimiento: float
    umbral: float
    modelo_version: str
    estado: str
    motivo: str | None
    reserva_id: str | None
    creado_en: datetime
    decidido_en: datetime


class PrestamoLista(BaseModel):
    total: int
    pagina: int
    tamano: int
    items: list[PrestamoLectura]


class RiesgoSolicitud(BaseModel):
    """Inferencia aislada (§8.E): no reserva inventario ni crea préstamo."""

    ingresos_mensuales_cop: Decimal = Field(gt=0)
    obligaciones_mensuales_cop: Decimal = Field(ge=0)
    monto_solicitado_cop: Decimal = Field(gt=0)
    plazo_meses: int = Field(ge=1, le=60)
    tipo_empleo: str = Field(max_length=40)
    antiguedad_laboral_meses: float = Field(ge=0)
    meses_historial_crediticio: float = Field(ge=0)
    creditos_previos: int = Field(ge=0)
    atrasos_previos_30d: int = Field(ge=0)
    porcentaje_pago_puntual: float | None = Field(default=None, ge=0, le=100)


class RiesgoDecision(BaseModel):
    probabilidad_incumplimiento: float
    umbral: float
    decision: str                 # FAVORABLE | DESFAVORABLE
    modelo_version: str
    run_id: str | None
    regla_aplicada: str | None = None


class ModeloInfo(BaseModel):
    modelo_version: str
    run_id: str | None
    umbral: float
    variables: list[str]
    fecha_promocion: str
    mlflow_url: str
    candidato: str | None = None
    roc_auc_validacion: float | None = None
    metricas_prueba: dict | None = None


class PromocionSolicitud(BaseModel):
    modelo_version: str = Field(pattern=r"^v[12]$")
    motivo: str = Field(default="promocion explicita", max_length=200)


class PromocionResultado(BaseModel):
    modelo_version: str
    umbral: float
    run_id: str | None
    activo_desde: str
    version_anterior: str | None
    motivo: str
