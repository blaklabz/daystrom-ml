"""Alembic environment for Daystrom's PostgreSQL schema."""
import os
from pathlib import Path
from logging.config import fileConfig
from alembic import context
from dotenv import load_dotenv
from sqlalchemy import engine_from_config, pool
from daystrom.models import Base

config = context.config
if config.config_file_name is not None:
    fileConfig(config.config_file_name)
load_dotenv(Path(__file__).resolve().parents[1] / '.env')
database_url = os.getenv('DAYSTROM_DATABASE_URL')
if not database_url:
    raise RuntimeError('DAYSTROM_DATABASE_URL is not configured')
config.set_main_option('sqlalchemy.url', database_url.replace('%', '%%'))
target_metadata = Base.metadata


def run_migrations_offline():
    context.configure(url=database_url, target_metadata=target_metadata, literal_binds=True, dialect_opts={'paramstyle': 'named'}, compare_type=True)
    with context.begin_transaction():
        context.run_migrations()


def run_migrations_online():
    connectable = engine_from_config(config.get_section(config.config_ini_section, {}), prefix='sqlalchemy.', poolclass=pool.NullPool)
    with connectable.connect() as connection:
        context.configure(connection=connection, target_metadata=target_metadata, compare_type=True)
        with context.begin_transaction():
            context.run_migrations()


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
