"""crea las tablas prestamo, solicitud_idempotente, evento_procesado y outbox
(esquema prestamos)

Revision ID: 0001_prestamos
Revises:
Create Date: 2026-11-01
"""
from alembic import op
import sqlalchemy as sa

revision = "0001_prestamos"
down_revision = None
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "prestamo",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("cliente_id", sa.String(length=36), nullable=False),
        sa.Column("producto_id", sa.String(length=36), nullable=False),
        sa.Column("cantidad", sa.Integer(), nullable=False),
        sa.Column("plazo_meses", sa.Integer(), nullable=False),
        sa.Column("precio_unitario_cop", sa.Numeric(14, 2), nullable=False),
        sa.Column("precio_producto_version", sa.Integer(), nullable=False),
        sa.Column("monto_total_cop", sa.Numeric(14, 2), nullable=False),
        sa.Column("cuota_mensual_cop", sa.Numeric(14, 2), nullable=False),
        sa.Column("tasa_mensual", sa.Float(), nullable=False),
        sa.Column("probabilidad_incumplimiento", sa.Float(), nullable=False),
        sa.Column("umbral", sa.Float(), nullable=False),
        sa.Column("modelo_version", sa.String(length=20), nullable=False),
        sa.Column("run_id", sa.String(length=40), nullable=True),
        sa.Column("estado", sa.String(length=30), nullable=False),
        sa.Column("motivo", sa.Text(), nullable=True),
        sa.Column("reserva_id", sa.String(length=36), nullable=True),
        sa.Column("cancelacion_solicitada_en", sa.DateTime(timezone=True),
                  nullable=True),
        sa.Column("creado_en", sa.DateTime(timezone=True), nullable=False),
        sa.Column("actualizado_en", sa.DateTime(timezone=True), nullable=False),
        sa.Column("decidido_en", sa.DateTime(timezone=True), nullable=False),
        sa.PrimaryKeyConstraint("id"),
        schema="prestamos",
    )
    op.create_index("ix_prestamo_cliente_id", "prestamo", ["cliente_id"],
                    schema="prestamos")
    op.create_index("ix_prestamo_estado", "prestamo", ["estado"],
                    schema="prestamos")

    op.create_table(
        "solicitud_idempotente",
        sa.Column("idempotency_key", sa.String(length=80), nullable=False),
        sa.Column("huella_cuerpo", sa.String(length=64), nullable=False),
        sa.Column("prestamo_id", sa.String(length=36), nullable=True),
        sa.Column("respuesta", sa.JSON(), nullable=False),
        sa.Column("status_code", sa.Integer(), nullable=False),
        sa.Column("creada_en", sa.DateTime(timezone=True), nullable=False),
        sa.PrimaryKeyConstraint("idempotency_key"),
        schema="prestamos",
    )

    op.create_table(
        "evento_procesado",
        sa.Column("event_id", sa.String(length=36), nullable=False),
        sa.Column("tipo", sa.String(length=80), nullable=False),
        sa.Column("prestamo_id", sa.String(length=36), nullable=True),
        sa.Column("procesado_en", sa.DateTime(timezone=True), nullable=False),
        sa.PrimaryKeyConstraint("event_id"),
        schema="prestamos",
    )

    op.create_table(
        "outbox",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("routing_key", sa.String(length=120), nullable=False),
        sa.Column("mensaje", sa.JSON(), nullable=False),
        sa.Column("creado_en", sa.DateTime(timezone=True), nullable=False),
        sa.Column("publicado_en", sa.DateTime(timezone=True), nullable=True),
        sa.PrimaryKeyConstraint("id"),
        schema="prestamos",
    )


def downgrade() -> None:
    op.drop_table("outbox", schema="prestamos")
    op.drop_table("evento_procesado", schema="prestamos")
    op.drop_table("solicitud_idempotente", schema="prestamos")
    op.drop_index("ix_prestamo_estado", table_name="prestamo", schema="prestamos")
    op.drop_index("ix_prestamo_cliente_id", table_name="prestamo",
                  schema="prestamos")
    op.drop_table("prestamo", schema="prestamos")
