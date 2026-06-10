import logging
import os
from logging.config import fileConfig

from sqlalchemy import engine_from_config, pool

from alembic import context

config = context.config

if config.config_file_name is not None:
    fileConfig(config.config_file_name)

logger = logging.getLogger("alembic.env")

from backend.db.models import Base

target_metadata = Base.metadata


def _resolve_database_url() -> str:
    """Resolve the database URL in priority order:
      1. DATABASE_URL environment variable
      2. .env file / pydantic-settings Settings (backend/config.py)
      3. sqlalchemy.url from alembic.ini
    Logs which source was used.
    """
    # 1. Environment variable (set directly in the process environment)
    env_url = os.environ.get("DATABASE_URL", "").strip()
    if env_url:
        logger.info("alembic: using DATABASE_URL from environment variable")
        return env_url

    # 2. .env file / pydantic-settings (loads .env from the project root)
    try:
        from backend.config import settings
        settings_url = settings.database_url.strip()
        # Only use this source if it differs from the alembic.ini default —
        # i.e. it was actually set somewhere (env file, env var already consumed
        # by pydantic-settings, etc.).  We distinguish "came from .env / real
        # config" from "fell through to pydantic default" by checking whether
        # DATABASE_URL appears in .env or was injected into os.environ before
        # pydantic-settings ran.  A simpler heuristic: if settings_url is not
        # the bare pydantic default AND not the alembic.ini value, prefer it.
        ini_url = (config.get_main_option("sqlalchemy.url") or "").strip()
        if settings_url and settings_url != ini_url:
            logger.info("alembic: using database URL from backend/config.py (pydantic-settings / .env)")
            return settings_url
        # settings gave the same value as alembic.ini — fall through so we
        # still log the right source.
        if settings_url:
            logger.info("alembic: using database URL from alembic.ini (matches backend/config.py default)")
            return settings_url
    except Exception as exc:
        logger.warning("alembic: could not import backend.config.settings (%s); falling back to alembic.ini", exc)

    # 3. alembic.ini sqlalchemy.url
    ini_url = (config.get_main_option("sqlalchemy.url") or "").strip()
    if ini_url:
        logger.info("alembic: using database URL from alembic.ini")
        return ini_url

    raise RuntimeError(
        "No database URL found. Set DATABASE_URL env var, add it to .env, "
        "or set sqlalchemy.url in alembic.ini."
    )


_db_url = _resolve_database_url()
config.set_main_option("sqlalchemy.url", _db_url)


def run_migrations_offline() -> None:
    url = config.get_main_option("sqlalchemy.url")
    context.configure(
        url=url,
        target_metadata=target_metadata,
        literal_binds=True,
        dialect_opts={"paramstyle": "named"},
    )
    with context.begin_transaction():
        context.run_migrations()


def run_migrations_online() -> None:
    connectable = engine_from_config(
        config.get_section(config.config_ini_section, {}),
        prefix="sqlalchemy.",
        poolclass=pool.NullPool,
    )
    with connectable.connect() as connection:
        context.configure(connection=connection, target_metadata=target_metadata)
        with context.begin_transaction():
            context.run_migrations()


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
