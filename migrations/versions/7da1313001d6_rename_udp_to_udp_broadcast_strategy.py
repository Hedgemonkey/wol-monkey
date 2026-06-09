"""rename_udp_to_udp_broadcast_strategy

Revision ID: 7da1313001d6
Revises: 09d75b0dfde5
Create Date: 2026-06-09 04:31:07.961450

"""

from collections.abc import Sequence

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "7da1313001d6"
down_revision: str | Sequence[str] | None = "09d75b0dfde5"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Rename wake strategy value 'udp' → 'udp_broadcast' in data columns."""
    op.execute("UPDATE machines SET wake_strategy = 'udp_broadcast' WHERE wake_strategy = 'udp'")
    op.execute("UPDATE wake_attempts SET strategy = 'udp_broadcast' WHERE strategy = 'udp'")
    op.execute(
        "UPDATE settings SET value = '\"udp_broadcast\"' WHERE key = 'default_wake_strategy' AND value = '\"udp\"'"
    )


def downgrade() -> None:
    """Revert wake strategy value 'udp_broadcast' → 'udp'."""
    op.execute("UPDATE machines SET wake_strategy = 'udp' WHERE wake_strategy = 'udp_broadcast'")
    op.execute("UPDATE wake_attempts SET strategy = 'udp' WHERE strategy = 'udp_broadcast'")
    op.execute(
        "UPDATE settings SET value = '\"udp\"' WHERE key = 'default_wake_strategy' AND value = '\"udp_broadcast\"'"
    )
