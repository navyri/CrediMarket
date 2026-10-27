"""Configuración del servicio Clientes."""
from pydantic_settings import BaseSettings, SettingsConfigDict


class Ajustes(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    servicio_nombre: str = "clientes"
    database_url: str = "postgresql+psycopg://svc_clientes:CAMBIAR_cli_local@localhost:5434/credimarket"

    jwt_secret: str = "CAMBIAR_jwt_local_largo_32+"
    jwt_algorithm: str = "HS256"
    jwt_exp_min: int = 30

    cors_origins: str = "http://localhost:5173"

    # Semilla de demo documentada en la guía (contraseñas viven en .env, nunca en el repo).
    admin_email: str = "admin@credimarket.demo"
    admin_password: str = "CAMBIAR_admin_local"


ajustes = Ajustes()
