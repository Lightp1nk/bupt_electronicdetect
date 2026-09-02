"""Create verified chat identities and hashed pending binding codes."""

from alembic import op
import sqlalchemy as sa


revision = "20260902_06"
down_revision = "20260901_05"
branch_labels = None
depends_on = None


def upgrade() -> None:
    tables = sa.inspect(op.get_bind()).get_table_names()
    if "chat_identities" not in tables:
        op.create_table(
            "chat_identities",
            sa.Column("id", sa.Integer, primary_key=True),
            sa.Column("user_id", sa.Integer, sa.ForeignKey("users.id"), nullable=False),
            sa.Column("platform", sa.String(32), nullable=False),
            sa.Column("external_id", sa.String(64), nullable=False),
            sa.Column("verified_at", sa.DateTime, nullable=False),
            sa.Column("created_at", sa.DateTime, nullable=False),
            sa.Column("updated_at", sa.DateTime, nullable=False),
            sa.UniqueConstraint("platform", "external_id", name="uq_chat_identity_external"),
            sa.UniqueConstraint("user_id", "platform", name="uq_chat_identity_user_platform"),
        )
        op.create_index("ix_chat_identities_user_id", "chat_identities", ["user_id"])
    if "pending_chat_bindings" not in tables:
        op.create_table(
            "pending_chat_bindings",
            sa.Column("id", sa.Integer, primary_key=True),
            sa.Column("user_id", sa.Integer, sa.ForeignKey("users.id"), nullable=False),
            sa.Column("platform", sa.String(32), nullable=False),
            sa.Column("code_hash", sa.String(64), nullable=False),
            sa.Column("status", sa.String(16), nullable=False),
            sa.Column("expires_at", sa.DateTime, nullable=False),
            sa.Column("used_at", sa.DateTime),
            sa.Column("created_at", sa.DateTime, nullable=False),
            sa.UniqueConstraint("code_hash", name="uq_pending_chat_binding_code_hash"),
        )
        op.create_index("ix_pending_chat_bindings_user_id", "pending_chat_bindings", ["user_id"])
        op.create_index("ix_pending_chat_bindings_code_hash", "pending_chat_bindings", ["code_hash"])
        op.create_index("ix_pending_chat_bindings_expires_at", "pending_chat_bindings", ["expires_at"])


def downgrade() -> None:
    op.drop_table("pending_chat_bindings")
    op.drop_table("chat_identities")
