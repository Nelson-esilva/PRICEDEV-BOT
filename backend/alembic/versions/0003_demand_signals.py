"""Demand signals, click channel, Telegram tracked links and affiliate conversions; additive and idempotent."""
from alembic import op
from sqlalchemy import inspect, text
from app.core.db import OPPORTUNITY_DEMAND_EXTRAS, PUBLISHED_EXTRAS
from app.models.entities import AffiliateConversion, TrackedLink

revision = "0003_demand_signals"
down_revision = "0002_public_discovery"
branch_labels = None
depends_on = None


def _add(connection, table, columns):
    existing = {c["name"] for c in inspect(connection).get_columns(table)}
    for name, ddl in columns.items():
        if name not in existing:
            connection.execute(text(f"ALTER TABLE {table} ADD COLUMN {name} {ddl}"))


def upgrade():
    connection = op.get_bind()
    AffiliateConversion.__table__.create(connection, checkfirst=True)
    TrackedLink.__table__.create(connection, checkfirst=True)
    _add(connection, "published_deals", PUBLISHED_EXTRAS)
    _add(connection, "opportunities", OPPORTUNITY_DEMAND_EXTRAS)
    _add(connection, "deal_clicks", {"channel": "VARCHAR(16) NOT NULL DEFAULT 'site'"})


def downgrade():
    connection = op.get_bind()
    AffiliateConversion.__table__.drop(connection, checkfirst=True)
    TrackedLink.__table__.drop(connection, checkfirst=True)
    with op.batch_alter_table("deal_clicks") as batch:
        batch.drop_column("channel")
    with op.batch_alter_table("opportunities") as batch:
        for name in OPPORTUNITY_DEMAND_EXTRAS:
            batch.drop_column(name)
    with op.batch_alter_table("published_deals") as batch:
        for name in ("price_max", "sales_count", "rating", "best_seller", "free_shipping",
                     "orders_30d", "clicks_7d", "demand_score", "price_condition", "regular_price", "gallery",
                     "rank_position", "rank_category", "rank_category_id", "trending"):
            batch.drop_column(name)
