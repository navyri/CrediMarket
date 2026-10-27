"""crea la tabla producto (esquema productos)

Revision ID: 0001_producto
Revises:
Create Date: 2026-10-27
"""
from alembic import op
import sqlalchemy as sa

revision = "0001_producto"
down_revision = None
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "producto",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("sku", sa.String(length=40), nullable=False),
        sa.Column("nombre", sa.String(length=200), nullable=False),
        sa.Column("categoria", sa.String(length=80), nullable=False),
        sa.Column("descripcion", sa.Text(), nullable=True),
        sa.Column("precio_cop", sa.Numeric(14, 2), nullable=False),
        sa.Column("activo", sa.Boolean(), nullable=False),
        sa.Column("version", sa.Integer(), nullable=False),
        sa.Column("creado_en", sa.DateTime(timezone=True), nullable=False),
        sa.Column("actualizado_en", sa.DateTime(timezone=True), nullable=False),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("sku"),
        schema="productos",
    )
    op.create_index("ix_producto_sku", "producto", ["sku"], schema="productos")
    op.create_index("ix_producto_categoria", "producto", ["categoria"], schema="productos")


def downgrade() -> None:
    op.drop_index("ix_producto_categoria", table_name="producto", schema="productos")
    op.drop_index("ix_producto_sku", table_name="producto", schema="productos")
    op.drop_table("producto", schema="productos")
