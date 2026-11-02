"""Configuración del servicio Productos (variables de entorno, ver .env.example)."""
from pydantic_settings import BaseSettings, SettingsConfigDict


class Ajustes(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    servicio_nombre: str = "productos"
    database_url: str = "postgresql+psycopg://svc_productos:CAMBIAR_prod_local@localhost:5434/credimarket"
    redis_url: str = "redis://redis:6379/0"
    redis_password: str = "CAMBIAR_redis_local"

    jwt_secret: str = "CAMBIAR_jwt_local_largo_32+"
    jwt_algorithm: str = "HS256"

    cors_origins: str = "http://localhost:5173"

    # Cache-aside (§6): TTL de lecturas de producto y límite del fallback.
    cache_ttl_seg: int = 60
    cache_prefijo: str = "productos"
    cache_version: str = "v1"
    fallback_ttl_seg: int = 5          # caché en memoria cuando Redis no responde
    cache_fail_fast_seg: int = 5       # cortacircuitos: no tocar Redis tras un fallo
    fallback_max_entradas: int = 256

    url_clientes: str = "http://clientes:8002"


ajustes = Ajustes()
