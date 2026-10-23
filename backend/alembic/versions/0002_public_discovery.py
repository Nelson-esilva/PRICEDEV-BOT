"""Additive public discovery schema; compatible with legacy create_all databases."""
from alembic import op
from sqlalchemy import inspect, text
from app.models.entities import PublicPromotion

revision = "0002_public_discovery"
down_revision = "0001_initial"
branch_labels = None
depends_on = None


def upgrade():
    connection = op.get_bind()
    PublicPromotion.__table__.create(connection, checkfirst=True)
    columns = {c["name"] for c in inspect(connection).get_columns("published_deals")}
    for name, ddl in {
        "discount_pct": "NUMERIC(8,2)", "discount_basis": "VARCHAR(32)",
        "acceptance_score": "INTEGER NOT NULL DEFAULT 0",
    }.items():
        if name not in columns:
            connection.execute(text(f"ALTER TABLE published_deals ADD COLUMN {name} {ddl}"))


def downgrade():
    connection = op.get_bind()
    PublicPromotion.__table__.drop(connection, checkfirst=True)
    with op.batch_alter_table("published_deals") as batch:
        batch.drop_column("discount_pct")
        batch.drop_column("discount_basis")
        batch.drop_column("acceptance_score")
