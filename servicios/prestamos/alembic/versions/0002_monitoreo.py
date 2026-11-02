"""crea la tabla metrica_inferencia (monitoreo de desempeño, §15.2)

Una fila por decisión de riesgo (solicitud o inferencia aislada) con latencia,
probabilidad, umbral y el vector de variables: es el insumo de
`GET /monitoreo/estado` (tasas, latencias y deriva PSI).

Revision ID: 0002_monitoreo
Revises: 0001_prestamos
Create Date: 2026-11-01
"""
from alembic import op
import sqlalchemy as sa

revision = "0002_monitoreo"
down_revision = "0001_prestamos"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "metrica_inferencia",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("origen", sa.String(length=20), nullable=False),
        sa.Column("prestamo_id", sa.String(length=36), nullable=True),
        sa.Column("modelo_version", sa.String(length=20), nullable=False),
        sa.Column("probabilidad", sa.Float(), nullable=False),
        sa.Column("umbral", sa.Float(), nullable=False),
        sa.Column("aplico_regla", sa.Boolean(), nullable=False),
        sa.Column("latencia_ms", sa.Float(), nullable=False),
        sa.Column("variables", sa.JSON(), nullable=False),
        sa.Column("registrado_en", sa.DateTime(timezone=True), nullable=False),
        sa.PrimaryKeyConstraint("id"),
        schema="prestamos",
    )
    op.create_index("ix_metrica_registrado_en", "metrica_inferencia",
                    ["registrado_en"], schema="prestamos")


def downgrade() -> None:
    op.drop_index("ix_metrica_registrado_en", table_name="metrica_inferencia",
                  schema="prestamos")
    op.drop_table("metrica_inferencia", schema="prestamos")
