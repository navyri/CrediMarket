"""Configuración del servicio Préstamos (dueño del modelo de riesgo, §8)."""
from pydantic_settings import BaseSettings, SettingsConfigDict


class Ajustes(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    servicio_nombre: str = "prestamos"
    database_url: str = (
        "postgresql+psycopg://svc_prestamos:CAMBIAR_pre_local@localhost:5434/credimarket"
    )

    broker_url: str = "amqp://credimarket:CAMBIAR_rabbit_local@localhost:5672/%2Fcredimarket"
    exchange: str = "credimarket.topic"
    exchange_muerto: str = "credimarket.dlx"
    cola_comandos: str = "prestamos.comandos"
    cola_reintento: str = "prestamos.retry"
    cola_dlq: str = "prestamos.dlq"
    ttl_reintento_ms: int = 5000
    max_intentos: int = 3
    prefetch: int = 10
    intervalo_outbox_seg: int = 1
    # §8.D: cada cuánto se relee `activo.json` (una promoción/rollback fuera
    # de banda se refleja sin reiniciar el servicio).
    intervalo_recarga_modelo_seg: int = 10

    jwt_secret: str = "CAMBIAR_jwt_local_largo_32+"
    jwt_algorithm: str = "HS256"
    cors_origins: str = "http://localhost:5173"

    # Servicios vecinos (solo API; jamás se tocan sus tablas, §3).
    url_clientes: str = "http://clientes:8002"
    url_productos: str = "http://productos:8001"
    url_mlflow: str = "http://mlflow:5000"

    # Modelo activo (§8.D): carpeta con activo.json + <version>/modelo.joblib.
    # En Compose se monta como volumen para que la promoción/rollback persistan.
    modelo_dir: str = "/modelos"

    # Tasa oficial del programa (constante del histórico: 0.0180 mensual).
    # El cliente NUNCA envía precio, monto ni tasa (§4): la cotización sale de
    # Productos y la cuota se calcula aquí con esta tasa.
    tasa_mensual_oficial: float = 0.018

    # Regla de control previa al modelo (documentada en decisiones):
    # si las obligaciones alcanzan o superan los ingresos, se rechaza por regla.
    ratio_deuda_ingreso_max: float = 1.0


ajustes = Ajustes()
