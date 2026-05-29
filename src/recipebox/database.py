import asyncpg

from .config import settings

pool: asyncpg.Pool | None = None


async def init_pool():
    global pool
    pool = await asyncpg.create_pool(settings.database_url)


async def close_pool():
    if pool is not None:
        await pool.close()
