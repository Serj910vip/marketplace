import asyncio
import uvicorn

from sqlalchemy import text

from app.database.session import engine
from app.database.base import Base

# IMPORT MODELS
from app.models.user import User


async def create_tables():
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)

if __name__ == "__main__":
    # asyncio.run(create_tables())
    uvicorn.run(
        "app.api.app:app",
        host="127.0.0.1",
        port=8000,
        reload=True
    )