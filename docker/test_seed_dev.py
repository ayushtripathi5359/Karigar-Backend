import asyncio
import os

import asyncpg


def _asyncpg_url(url: str) -> str:
    return url.replace("postgresql+asyncpg://", "postgresql://", 1)


async def main() -> None:
    database_url = _asyncpg_url(os.environ["DATABASE_URL"])
    sql = open("sql/seed_dev.sql", encoding="utf-8").read()
    conn = await asyncpg.connect(database_url)
    try:
        await conn.execute(sql)
    finally:
        await conn.close()


if __name__ == "__main__":
    asyncio.run(main())
