"""Configuración del servicio Inventario."""
from pydantic_settings import BaseSettings, SettingsConfigDict


class Ajustes(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    servicio_nombre: str = "inventario"
    database_url: str = (
        "postgresql+psycopg://svc_inventario:CAMBIAR_inv_local@localhost:5434/credimarket"
    )

    broker_url: str = "amqp://credimarket:CAMBIAR_rabbit_local@localhost:5672/%2Fcredimarket"
    exchange: str = "credimarket.topic"
    exchange_muerto: str = "credimarket.dlx"
    cola_comandos: str = "inventario.comandos"
    cola_reintento: str = "inventario.retry"
    cola_dlq: str = "inventario.dlq"
    ttl_reintento_ms: int = 5000
    max_intentos: int = 3
    prefetch: int = 10

    jwt_secret: str = "CAMBIAR_jwt_local_largo_32+"
    jwt_algorithm: str = "HS256"
    cors_origins: str = "http://localhost:5173"

    # Vencimiento de reservas (§4, máquina de estados §4).
    reserva_vencimiento_seg: int = 600
    intervalo_vencimiento_seg: int = 15
    intervalo_outbox_seg: int = 1


ajustes = Ajustes()
