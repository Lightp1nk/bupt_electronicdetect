"""Move unowned alert configuration and episodes to user-scoped tables."""
from alembic import op
import sqlalchemy as sa

revision="20260901_03"; down_revision="20260901_02"; branch_labels=None; depends_on=None

def upgrade():
    bind=op.get_bind(); tables=set(sa.inspect(bind).get_table_names())
    for name in ("alert_settings","alert_events"):
        if name in tables and "user_id" not in {c["name"] for c in sa.inspect(bind).get_columns(name)}:
            op.rename_table(name,f"{name}_legacy_unassigned"); tables.remove(name)
    if "alert_settings" not in tables:
        op.create_table("alert_settings",sa.Column("id",sa.Integer,primary_key=True),sa.Column("user_id",sa.Integer,sa.ForeignKey("users.id"),nullable=False,unique=True),sa.Column("enabled",sa.Boolean,nullable=False,server_default=sa.true()),sa.Column("low_balance_enabled",sa.Boolean,nullable=False,server_default=sa.true()),sa.Column("balance_warning_threshold",sa.Float,nullable=False,server_default="20"),sa.Column("balance_critical_threshold",sa.Float,nullable=False,server_default="10"),sa.Column("low_remaining_days_enabled",sa.Boolean,nullable=False,server_default=sa.true()),sa.Column("remaining_days_warning_threshold",sa.Float,nullable=False,server_default="7"),sa.Column("remaining_days_critical_threshold",sa.Float,nullable=False,server_default="3"),sa.Column("created_at",sa.DateTime,nullable=False),sa.Column("updated_at",sa.DateTime,nullable=False))
    if "alert_events" not in tables:
        op.create_table("alert_events",sa.Column("id",sa.Integer,primary_key=True),sa.Column("user_id",sa.Integer,sa.ForeignKey("users.id"),nullable=False),sa.Column("area_id",sa.String(32),nullable=False),sa.Column("room_id",sa.String(128),nullable=False),sa.Column("building_name",sa.String(255)),sa.Column("floor_name",sa.String(255)),sa.Column("room_name",sa.String(255)),sa.Column("alert_type",sa.String(32),nullable=False),sa.Column("level",sa.String(16),nullable=False),sa.Column("status",sa.String(16),nullable=False),sa.Column("title",sa.String(128),nullable=False),sa.Column("message",sa.String(512),nullable=False),sa.Column("trigger_value",sa.Float,nullable=False),sa.Column("threshold_value",sa.Float,nullable=False),sa.Column("source_time",sa.DateTime),sa.Column("first_triggered_at",sa.DateTime,nullable=False),sa.Column("last_seen_at",sa.DateTime,nullable=False),sa.Column("resolved_at",sa.DateTime),sa.Column("created_at",sa.DateTime,nullable=False),sa.Column("updated_at",sa.DateTime,nullable=False))
        op.create_index("ix_alert_events_user_room_type_status","alert_events",["user_id","area_id","room_id","alert_type","status"])
        op.execute("CREATE UNIQUE INDEX uq_alert_events_active_episode ON alert_events (user_id, area_id, room_id, alert_type) WHERE status = 'active'")

def downgrade():
    for name in ("alert_settings","alert_events"):
        op.rename_table(name,f"{name}_user_scoped_backup")
    op.rename_table("alert_settings_legacy_unassigned","alert_settings")
    op.rename_table("alert_events_legacy_unassigned","alert_events")
