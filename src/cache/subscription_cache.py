import json
from uuid import UUID
import uuid
from src.queue.redis_conn import redis_conn_global
from src.db.session import AsyncSessionLocal
from src.models.subscription import Subscription
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select

redis_conn = redis_conn_global
CACHE_PREFIX = "subscription:"

def _make_key(subscription_id: str) -> str:
    return f"{CACHE_PREFIX}{subscription_id}"

def cache_subscription(sub: Subscription) -> None:
    """
    Store the subscription's core fields in Redis under a JSON string.
    """
    key = _make_key(str(sub.id))
    data = {
        "id": str(sub.id),
        "target_url": sub.target_url,
        "secret": sub.secret,
        "events": sub.events or [],
    }
    try:
        redis_conn.set(key, json.dumps(data))
    except Exception:
        # Silently ignore caching failures
        pass

async def get_subscription(subscription_id: UUID | str, db: AsyncSession = None) -> dict | None:
    """
    Return the subscription data dict from Redis if present; otherwise
    load from Postgres, cache it, and return. Returns None if no such
    subscription exists. Cache failures are silently ignored.
    
    Args:
        subscription_id: The UUID of the subscription to get
        db: Optional async SQLAlchemy session to use. If None, creates a new one.
    """
    sid = str(subscription_id)
    key = _make_key(sid)

    # 1) Try cache
    try:
        raw = redis_conn.get(key)
        if raw:
            try:
                return json.loads(raw)
            except json.JSONDecodeError:
                # corrupted cache entry; fall back to DB
                pass
    except Exception:
        # Redis unavailable or error → cache miss
        pass

    # 2) Cache miss or error → load from DB
    session_created = False
    if db is None:
        db = AsyncSessionLocal()
        session_created = True
    
    try:
        result = await db.execute(
            select(Subscription).where(Subscription.id == uuid.UUID(sid))
        )
        sub = result.scalar_one_or_none()
        if not sub:
            return None
        data = {
            "id": str(sub.id),
            "target_url": sub.target_url,
            "secret": sub.secret,
            "events": sub.events or [],
        }
        # Try to update cache (best‐effort)
        try:
            redis_conn.set(key, json.dumps(data))
        except Exception:
            pass
        return data
    finally:
        if session_created:
            await db.close()

def invalidate_subscription(subscription_id: UUID | str) -> None:
    """
    Remove a subscription's cache entry (e.g. on delete).
    """
    key = _make_key(str(subscription_id))
    try:
        redis_conn.delete(key)
    except Exception:
        pass

def get_subscription_sync(subscription_id: UUID | str) -> dict | None:
    """
    Synchronous wrapper for get_subscription.
    Only checks cache, does not fall back to database.
    Use this when you only want cache lookup without DB fallback.
    """
    import asyncio
    
    sid = str(subscription_id)
    key = _make_key(sid)

    # Only try cache, no DB fallback
    try:
        raw = redis_conn.get(key)
        if raw:
            try:
                return json.loads(raw)
            except json.JSONDecodeError:
                pass
    except Exception:
        pass
    
    return None