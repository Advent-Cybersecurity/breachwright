from sqlalchemy.ext.asyncio import create_async_engine, async_sessionmaker, AsyncSession
from app.config import settings

engine = create_async_engine(
    settings.resolved_database_url,
    echo=False,
    # SQLite needs these for async
    **({} if "postgresql" in settings.resolved_database_url else {
        "connect_args": {"check_same_thread": False}
    })
)
async_session = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)


async def get_db() -> AsyncSession:
    async with async_session() as session:
        try:
            yield session
            await session.commit()
        except Exception:
            await session.rollback()
            raise
