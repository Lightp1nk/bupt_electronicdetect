"""Mark the pre-Alembic schema as the migration baseline."""

from alembic import op


revision = "20260901_01"
down_revision = None
branch_labels = None
depends_on = None


def upgrade() -> None:
    # Existing project tables are bootstrapped by SQLAlchemy metadata.
    pass


def downgrade() -> None:
    pass
