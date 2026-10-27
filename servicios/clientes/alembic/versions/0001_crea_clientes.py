"""crea las tablas cliente y usuario (esquema clientes)

Revision ID: 0001_clientes
Revises:
Create Date: 2026-10-27
"""
from alembic import op
import sqlalchemy as sa

revision = "0001_clientes"
down_revision = None
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "cliente",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("documento_identidad", sa.String(length=30), nullable=False),
        sa.Column("nombre", sa.String(length=160), nullable=False),
        sa.Column("email", sa.String(length=160), nullable=False),
        sa.Column("telefono", sa.String(length=30), nullable=True),
        sa.Column("ciudad", sa.String(length=80), nullable=True),
        sa.Column("activo", sa.Boolean(), nullable=False),
        sa.Column("creado_en", sa.DateTime(timezone=True), nullable=False),
        sa.Column("actualizado_en", sa.DateTime(timezone=True), nullable=False),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("documento_identidad", name="uq_cliente_documento"),
        sa.UniqueConstraint("email"),
        schema="clientes",
    )
    op.create_index("ix_cliente_documento_identidad", "cliente",
                    ["documento_identidad"], schema="clientes")

    op.create_table(
        "usuario",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("email", sa.String(length=160), nullable=False),
        sa.Column("password_hash", sa.String(length=200), nullable=False),
        sa.Column("rol", sa.String(length=20), nullable=False),
        sa.Column("cliente_id", sa.String(length=36), nullable=True),
        sa.Column("creado_en", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["cliente_id"], ["clientes.cliente.id"],
                                ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("email"),
        schema="clientes",
    )


def downgrade() -> None:
    op.drop_table("usuario", schema="clientes")
    op.drop_index("ix_cliente_documento_identidad", table_name="cliente",
                  schema="clientes")
    op.drop_table("cliente", schema="clientes")
