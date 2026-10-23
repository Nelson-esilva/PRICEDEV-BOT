import asyncio
from logging.config import fileConfig

from alembic import context
from sqlalchemy import pool
from sqlalchemy.ext.asyncio import async_engine_from_config

from app.core.config import get_settings
from app.core.db import Base, normalize_database_url
from app import models  # noqa: F401

config = context.config
if config.config_file_name and config.get_section('loggers') is not None:
    fileConfig(config.config_file_name)

# Use the same SQLite/asyncpg connection as the API; never silently migrate
# the sample SQLite database when the application is configured for PostgreSQL.
config.set_main_option('sqlalchemy.url', normalize_database_url(get_settings().database_url).replace('%', '%%'))
target_metadata = Base.metadata


def run_migrations_offline():
    context.configure(url=config.get_main_option('sqlalchemy.url'), target_metadata=target_metadata, literal_binds=True)
    with context.begin_transaction():
        context.run_migrations()


def migrate(connection):
    context.configure(connection=connection, target_metadata=target_metadata, render_as_batch=connection.dialect.name == 'sqlite')
    with context.begin_transaction():
        context.run_migrations()


async def run_online():
    engine = async_engine_from_config(config.get_section(config.config_ini_section), prefix='sqlalchemy.', poolclass=pool.NullPool)
    async with engine.connect() as connection:
        await connection.run_sync(migrate)
    await engine.dispose()


if context.is_offline_mode():
    run_migrations_offline()
else:
    asyncio.run(run_online())
