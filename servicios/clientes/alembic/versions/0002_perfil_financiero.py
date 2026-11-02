"""añade el perfil financiero del cliente (dueño de sus datos)

El histórico `prestamos_entrenamiento.csv` tiene `cliente_id` único por fila:
el perfil financiero pertenece al CLIENTE, y el servicio Clientes es su dueño
(P2-7). Préstamos lo lee por API para armar el vector de variables del modelo
(§4: cada servicio dueño de sus datos; comunicación solo por API).

Revision ID: 0002_perfil_financiero
Revises: 0001_clientes
Create Date: 2026-11-01
"""
from alembic import op
import sqlalchemy as sa

revision = "0002_perfil_financiero"
down_revision = "0001_clientes"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("cliente", sa.Column("ingresos_mensuales_cop",
                                       sa.Numeric(14, 2), nullable=True),
                  schema="clientes")
    op.add_column("cliente", sa.Column("obligaciones_mensuales_cop",
                                       sa.Numeric(14, 2), nullable=True),
                  schema="clientes")
    op.add_column("cliente", sa.Column("tipo_empleo", sa.String(length=40),
                                       nullable=True), schema="clientes")
    op.add_column("cliente", sa.Column("antiguedad_laboral_meses",
                                       sa.Float(), nullable=True),
                  schema="clientes")
    op.add_column("cliente", sa.Column("meses_historial_crediticio",
                                       sa.Float(), nullable=True),
                  schema="clientes")
    op.add_column("cliente", sa.Column("creditos_previos", sa.Integer(),
                                       nullable=True), schema="clientes")
    op.add_column("cliente", sa.Column("atrasos_previos_30d", sa.Integer(),
                                       nullable=True), schema="clientes")
    op.add_column("cliente", sa.Column("porcentaje_pago_puntual",
                                       sa.Float(), nullable=True),
                  schema="clientes")


def downgrade() -> None:
    op.drop_column("cliente", "porcentaje_pago_puntual", schema="clientes")
    op.drop_column("cliente", "atrasos_previos_30d", schema="clientes")
    op.drop_column("cliente", "creditos_previos", schema="clientes")
    op.drop_column("cliente", "meses_historial_crediticio", schema="clientes")
    op.drop_column("cliente", "antiguedad_laboral_meses", schema="clientes")
    op.drop_column("cliente", "tipo_empleo", schema="clientes")
    op.drop_column("cliente", "obligaciones_mensuales_cop", schema="clientes")
    op.drop_column("cliente", "ingresos_mensuales_cop", schema="clientes")
