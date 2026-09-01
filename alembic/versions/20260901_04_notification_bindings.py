"""Create user notification targets."""
from alembic import op
import sqlalchemy as sa
revision="20260901_04"; down_revision="20260901_03"; branch_labels=None; depends_on=None
def upgrade():
    if "notification_bindings" in sa.inspect(op.get_bind()).get_table_names(): return
    op.create_table("notification_bindings",sa.Column("id",sa.Integer,primary_key=True),sa.Column("user_id",sa.Integer,sa.ForeignKey("users.id"),nullable=False),sa.Column("provider",sa.String(32),nullable=False),sa.Column("platform",sa.String(32),nullable=False),sa.Column("target_id",sa.String(64),nullable=False),sa.Column("enabled",sa.Boolean,nullable=False,server_default=sa.true()),sa.Column("created_at",sa.DateTime,nullable=False),sa.Column("updated_at",sa.DateTime,nullable=False),sa.UniqueConstraint("user_id","provider","platform",name="uq_notification_binding_target"))
    op.create_index("ix_notification_bindings_user_id","notification_bindings",["user_id"])
def downgrade(): op.drop_table("notification_bindings")
