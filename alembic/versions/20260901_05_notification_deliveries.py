"""Create durable, stage-aware notification delivery records."""

from alembic import op
import sqlalchemy as sa


revision = "20260901_05"
down_revision = "20260901_04"
branch_labels = None
depends_on = None


def upgrade() -> None:
    if "notification_deliveries" in sa.inspect(op.get_bind()).get_table_names():
        return
    op.create_table(
        "notification_deliveries",
        sa.Column("id", sa.Integer, primary_key=True),
        sa.Column("alert_event_id", sa.Integer, sa.ForeignKey("alert_events.id"), nullable=False),
        sa.Column("binding_id", sa.Integer, sa.ForeignKey("notification_bindings.id"), nullable=False),
        sa.Column("provider", sa.String(32), nullable=False),
        sa.Column("stage", sa.String(32), nullable=False),
        sa.Column("status", sa.String(16), nullable=False),
        sa.Column("created_at", sa.DateTime, nullable=False),
        sa.Column("sent_at", sa.DateTime),
        sa.Column("error_message", sa.String(256)),
        sa.UniqueConstraint("alert_event_id", "binding_id", "provider", "stage", name="uq_notification_delivery_stage"),
    )
    op.create_index("ix_notification_deliveries_event_id", "notification_deliveries", ["alert_event_id"])
    op.create_index("ix_notification_deliveries_binding_id", "notification_deliveries", ["binding_id"])


def downgrade() -> None:
    op.drop_table("notification_deliveries")
