"""Database initialization and session handling."""

from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession, async_sessionmaker
from scraper.config import settings
from scraper.storage.models import Base

engine = create_async_engine(settings.database_url, echo=False)
AsyncSessionLocal = async_sessionmaker(
    engine, class_=AsyncSession, expire_on_commit=False
)


async def init_db():
    """Create all database tables if they do not exist."""
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
