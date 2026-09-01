"""Replace the unowned collection-settings singleton with user-scoped settings."""

from alembic import op
import sqlalchemy as sa


revision = "20260901_02"
down_revision = "20260901_01"
branch_labels = None
depends_on = None


def upgrade() -> None:
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    tables = set(inspector.get_table_names())

    if "collection_settings" in tables:
        columns = {column["name"] for column in inspector.get_columns("collection_settings")}
        if "user_id" not in columns:
            op.rename_table("collection_settings", "collection_settings_legacy_unassigned")
            tables.remove("collection_settings")

    if "collection_settings" not in tables:
        op.create_table(
            "collection_settings",
            sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True, nullable=False),
            sa.Column("user_id", sa.Integer(), sa.ForeignKey("users.id"), nullable=False),
            sa.Column("area_id", sa.String(length=32)),
            sa.Column("area_name", sa.String(length=255)),
            sa.Column("building_id", sa.String(length=128)),
            sa.Column("building_name", sa.String(length=255)),
            sa.Column("floor_id", sa.String(length=128)),
            sa.Column("floor_name", sa.String(length=255)),
            sa.Column("room_id", sa.String(length=128)),
            sa.Column("room_name", sa.String(length=255)),
            sa.Column("enabled", sa.Boolean(), nullable=False, server_default=sa.true()),
            sa.Column("status", sa.String(length=32), nullable=False, server_default="never_run"),
            sa.Column("message", sa.String(length=512)),
            sa.Column("last_attempt_time", sa.DateTime()),
            sa.Column("last_success_time", sa.DateTime()),
            sa.Column("last_source_time", sa.DateTime()),
            sa.UniqueConstraint("user_id", name="uq_collection_settings_user_id"),
        )
        op.create_index("ix_collection_settings_user_id", "collection_settings", ["user_id"])


def downgrade() -> None:
    # A legacy row has no trustworthy owner, so this migration is intentionally non-destructive.
    raise NotImplementedError("collection settings ownership migration is irreversible")
