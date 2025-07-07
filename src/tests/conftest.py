import os
import pytest
import redis
from rq import Queue
from dotenv import load_dotenv

load_dotenv()


@pytest.fixture(scope="session")
def db_engine(): # Depend on env vars being set
    """Creates the DB engine and tables."""
    from src.db.session import engine, Base

    Base.metadata.create_all(bind=engine)
    yield engine


@pytest.fixture(scope="session")
def test_redis_conn(): # Depend on the container fixture
    """Creates a Redis connection using environment REDIS_URL"""
    redis_url = os.getenv("REDIS_URL", "redis://localhost:6379/0")
    
    conn = redis.from_url(redis_url)
    try:
        conn.ping()
    except redis.exceptions.ConnectionError as e:
        pytest.fail(f"Redis connection failed: {e}")
    conn.flushall()
    return conn
    


@pytest.fixture(scope="session")
def test_delivery_queue(test_redis_conn):
    """Creates an RQ Queue using the test Redis connection."""
    queue = Queue("deliveries", connection=test_redis_conn)
    return queue


@pytest.fixture(scope="session", autouse=True)
def patch_redis_module(test_redis_conn, test_delivery_queue):
    """
    Patch both the queue module *and* the subscription_cache module
    so that all code uses the test Redis connection/queue.
    """
    # patch src.queue.redis_conn
    from src.queue import redis_conn as queue_module
    orig_queue_conn = queue_module.redis_conn_global
    orig_queue_queue = queue_module.delivery_queue
    queue_module.redis_conn_global = test_redis_conn
    queue_module.delivery_queue = test_delivery_queue

    # patch src.cache.subscription_cache
    from src.cache import subscription_cache as cache_module
    orig_cache_conn = cache_module.redis_conn
    cache_module.redis_conn = test_redis_conn

    yield

    # restore
    queue_module.redis_conn_global = orig_queue_conn
    queue_module.delivery_queue = orig_queue_queue
    cache_module.redis_conn = orig_cache_conn



@pytest.fixture(scope="function")
def db_session(db_engine):
    """Provides a transactional session for tests."""
    # Import SessionLocal here to ensure it uses the correct engine
    from src.db.session import SessionLocal
    from sqlalchemy.orm import sessionmaker

    connection = db_engine.connect()
    transaction = connection.begin()
    # Use sessionmaker configured with the correct engine via SessionLocal
    # Or re-create sessionmaker if SessionLocal itself needs rebinding
    TestingSessionLocal = sessionmaker(bind=connection)
    session = TestingSessionLocal()

    yield session

    session.close()
    transaction.rollback()
    connection.close()


@pytest.fixture(scope="function")
async def async_db_session(db_engine):
    """Provides an async transactional session for tests."""
    from src.db.session import AsyncSessionLocal
    from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine
    from sqlalchemy.orm import sessionmaker
    
    database_url = os.getenv("DATABASE_URL")
    if not database_url:
        pytest.fail("DATABASE_URL environment variable not set")
    
    # Convert to async URL format
    if database_url.startswith("postgresql://"):
        async_database_url = database_url.replace("postgresql://", "postgresql+asyncpg://")
    else:
        async_database_url = database_url
    
    # Create async engine
    async_engine = create_async_engine(async_database_url, echo=True)
    
    async with async_engine.begin() as connection:
        # Create a sessionmaker bound to this connection
        TestingAsyncSessionLocal = sessionmaker(
            bind=connection,
            class_=AsyncSession,
            expire_on_commit=False,
        )
        
        async with TestingAsyncSessionLocal() as session:
            yield session
            await session.rollback()
    
    await async_engine.dispose()


@pytest.fixture(scope="function")
def redis_conn():
    """Provides the session-patched redis connection."""
    from src.queue.redis_conn import redis_conn_global
    return redis_conn_global


@pytest.fixture(scope="function")
def delivery_queue():
    """Provides the session-patched delivery queue."""
    from src.queue.redis_conn import delivery_queue
    delivery_queue.empty()
    return delivery_queue


@pytest.fixture(scope="function")
async def client(async_db_session):
    """Provides an async HTTP client for testing with DB dependency override."""
    import httpx
    from src.api.main import app
    from src.api.routes.subscriptions import get_async_db as subs_get_async_db
    from src.api.routes.status import get_async_db as status_get_async_db

    async def override_get_async_db():
        yield async_db_session

    app.dependency_overrides[subs_get_async_db] = override_get_async_db
    app.dependency_overrides[status_get_async_db] = override_get_async_db

    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
        yield client

    app.dependency_overrides = {} 