import json
import uuid
import pytest
import asyncio

from src.cache.subscription_cache import (
    get_subscription,
    get_subscription_sync,
    invalidate_subscription,
    _make_key,
)
from src.models.subscription import Subscription # Needed for type hints if used

# Use client fixture for API interactions, redis_conn for direct checks
@pytest.mark.asyncio
async def test_cache_population_on_miss(client, async_db_session, redis_conn):
    """Verify cache is populated when fetching a sub not already cached."""
    # 1. Create subscription directly in DB (bypassing API cache logic)
    sub = Subscription(target_url="http://cache-miss-test.com")
    async_db_session.add(sub)
    await async_db_session.commit()
    await async_db_session.refresh(sub)
    sub_id = sub.id
    cache_key = _make_key(str(sub_id))

    # 2. Ensure cache is initially empty for this sub
    assert redis_conn.exists(cache_key) == 0

    # 3. Call the function that uses cache (get_subscription)
    retrieved_data = await get_subscription(sub_id, db=async_db_session)

    # 4. Verify data was retrieved
    assert retrieved_data is not None
    assert retrieved_data["target_url"] == sub.target_url

    # 5. Verify cache was populated
    assert redis_conn.exists(cache_key) == 1
    cached_raw = redis_conn.get(cache_key)
    cached_data = json.loads(cached_raw)
    assert cached_data["target_url"] == sub.target_url

async def test_cache_hit(client, redis_conn, mocker):
    """Verify DB is not hit when cache is warm."""
    # 1. Create subscription via API (which populates cache)
    payload = {"target_url": "http://cache-hit-test.com/"}
    r = await client.post("/subscriptions/", json=payload)
    assert r.status_code == 201
    sub_id = r.json()["id"]
    cache_key = _make_key(sub_id)

    # 2. Verify cache is populated
    assert redis_conn.exists(cache_key) == 1

    # 3. Use sync version for cache-only lookup (no DB fallback)
    retrieved_data = get_subscription_sync(sub_id)

    # 4. Verify data was retrieved (from cache)
    assert retrieved_data is not None
    assert retrieved_data["target_url"] == payload["target_url"]


async def test_cache_invalidation_on_update(client, redis_conn):
    """Verify cache is updated/invalidated when subscription is updated."""
    # 1. Create subscription via API
    payload = {"target_url": "http://cache-update-test.com/", "secret": "old"}
    r = await client.post("/subscriptions/", json=payload)
    assert r.status_code == 201
    sub_id = r.json()["id"]
    cache_key = _make_key(sub_id)

    # 2. Verify initial cache state
    cached_raw = redis_conn.get(cache_key)
    cached_data = json.loads(cached_raw)
    assert cached_data["target_url"] == payload["target_url"]
    assert cached_data["secret"] == payload["secret"]

    # 3. Update subscription via API
    update_payload = {"target_url": "http://new-url.org/", "secret": "new"}
    r = await client.patch(f"/subscriptions/{sub_id}", json=update_payload)
    assert r.status_code == 200

    # 4. Verify cache reflects the update
    cached_raw_updated = redis_conn.get(cache_key)
    assert cached_raw_updated is not None
    cached_data_updated = json.loads(cached_raw_updated)
    assert cached_data_updated["target_url"] == update_payload["target_url"]
    assert cached_data_updated["secret"] == update_payload["secret"]

    # 5. Verify get_subscription also returns updated data from cache
    retrieved_data = get_subscription_sync(sub_id)
    assert retrieved_data["target_url"] == update_payload["target_url"]
    assert retrieved_data["secret"] == update_payload["secret"]


async def test_cache_invalidation_on_delete(client, redis_conn):
    """Verify cache entry is removed when subscription is deleted."""
    # 1. Create subscription via API
    payload = {"target_url": "http://cache-delete-test.com/"}
    r = await client.post("/subscriptions/", json=payload)
    assert r.status_code == 201
    sub_id = r.json()["id"]
    cache_key = _make_key(sub_id)

    # 2. Verify cache exists
    assert redis_conn.exists(cache_key) == 1

    # 3. Delete subscription via API
    r = await client.delete(f"/subscriptions/{sub_id}")
    assert r.status_code == 204

    # 4. Verify cache entry is gone
    assert redis_conn.exists(cache_key) == 0

    # 5. Verify get_subscription_sync now returns None (cache only, no DB fallback)
    retrieved_data = get_subscription_sync(sub_id)
    assert retrieved_data is None

