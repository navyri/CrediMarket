"""crea las tablas de inventario (esquema inventario)

Revision ID: 0001_inventario
Revises:
Create Date: 2026-10-27
"""
from alembic import op
import sqlalchemy as sa

revision = "0001_inventario"
down_revision = None
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "existencia",
        sa.Column("producto_id", sa.String(length=36), nullable=False),
        sa.Column("total", sa.Integer(), nullable=False),
        sa.Column("reservada", sa.Integer(), nullable=False),
        sa.Column("actualizado_en", sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint("reservada >= 0", name="ck_existencia_reservada_no_negativa"),
        sa.CheckConstraint("total >= reservada", name="ck_existencia_total_no_menor"),
        sa.PrimaryKeyConstraint("producto_id"),
        schema="inventario",
    )

    op.create_table(
        "reserva",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("prestamo_id", sa.String(length=36), nullable=False),
        sa.Column("producto_id", sa.String(length=36), nullable=False),
        sa.Column("cantidad", sa.Integer(), nullable=False),
        sa.Column("estado", sa.String(length=20), nullable=False),
        sa.Column("vence_en", sa.DateTime(timezone=True), nullable=False),
        sa.Column("creada_en", sa.DateTime(timezone=True), nullable=False),
        sa.Column("actualizada_en", sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint("cantidad > 0", name="ck_reserva_cantidad_positiva"),
        sa.PrimaryKeyConstraint("id"),
        schema="inventario",
    )
    op.create_index("ix_reserva_prestamo_id", "reserva", ["prestamo_id"],
                    schema="inventario")
    op.create_index("ix_reserva_producto_id", "reserva", ["producto_id"],
                    schema="inventario")

    op.create_table(
        "movimiento",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("tipo", sa.String(length=20), nullable=False),
        sa.Column("producto_id", sa.String(length=36), nullable=False),
        sa.Column("cantidad", sa.Integer(), nullable=False),
        sa.Column("referencia", sa.String(length=36), nullable=True),
        sa.Column("detalle", sa.Text(), nullable=True),
        sa.Column("creado_en", sa.DateTime(timezone=True), nullable=False),
        sa.PrimaryKeyConstraint("id"),
        schema="inventario",
    )
    op.create_index("ix_movimiento_producto_id", "movimiento", ["producto_id"],
                    schema="inventario")

    op.create_table(
        "evento_procesado",
        sa.Column("event_id", sa.String(length=36), nullable=False),
        sa.Column("tipo", sa.String(length=80), nullable=False),
        sa.Column("prestamo_id", sa.String(length=36), nullable=True),
        sa.Column("procesado_en", sa.DateTime(timezone=True), nullable=False),
        sa.PrimaryKeyConstraint("event_id"),
        schema="inventario",
    )

    op.create_table(
        "outbox",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("routing_key", sa.String(length=120), nullable=False),
        sa.Column("mensaje", sa.JSON(), nullable=False),
        sa.Column("creado_en", sa.DateTime(timezone=True), nullable=False),
        sa.Column("publicado_en", sa.DateTime(timezone=True), nullable=True),
        sa.PrimaryKeyConstraint("id"),
        schema="inventario",
    )


def downgrade() -> None:
    op.drop_table("outbox", schema="inventario")
    op.drop_table("evento_procesado", schema="inventario")
    op.drop_index("ix_movimiento_producto_id", table_name="movimiento",
                  schema="inventario")
    op.drop_table("movimiento", schema="inventario")
    op.drop_index("ix_reserva_producto_id", table_name="reserva", schema="inventario")
    op.drop_index("ix_reserva_prestamo_id", table_name="reserva", schema="inventario")
    op.drop_table("reserva", schema="inventario")
    op.drop_table("existencia", schema="inventario")
