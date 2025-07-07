import uuid
import pytest
import json # Import json

# Import cache functions and redis_conn fixture
from src.cache.subscription_cache import cache_subscription, _make_key
from src.models.subscription import Subscription # Import Subscription model    

async def test_create_subscription_invalid_url(client):
    """Test creating subscription with malformed URL."""
    payload = {"target_url": "not-a-valid-url"}
    r = await client.post("/subscriptions/", json=payload)
    assert r.status_code == 422
    assert "detail" in r.json()
    assert isinstance(r.json()["detail"], list)
    assert "valid url" in r.json()["detail"][0]["msg"].lower()

async def test_get_subscription_invalid_uuid(client):
    """Test GET with a non-UUID string."""
    r = await client.get("/subscriptions/not-a-uuid")
    assert r.status_code == 422
    assert "valid uuid" in r.json()["detail"][0]["msg"].lower()

async def test_get_subscription_not_found(client):
    """Test GET with a valid UUID that doesn't exist."""
    non_existent_id = uuid.uuid4()
    r = await client.get(f"/subscriptions/{non_existent_id}")
    assert r.status_code == 404
    assert "Subscription not found" in r.json()["detail"]

async def test_patch_subscription_not_found(client):
    """Test PATCH with a valid UUID that doesn't exist."""
    non_existent_id = uuid.uuid4()
    payload = {"target_url": "http://doesnt-matter.com"}
    r = await client.patch(f"/subscriptions/{non_existent_id}", json=payload)
    assert r.status_code == 404
    assert "Subscription not found" in r.json()["detail"]

async def test_delete_subscription_not_found(client):
    """Test DELETE with a valid UUID that doesn't exist."""
    non_existent_id = uuid.uuid4()
    r = await client.delete(f"/subscriptions/{non_existent_id}")
    assert r.status_code == 404
    assert "Subscription not found" in r.json()["detail"]

# --- Ingest Endpoint Errors ---

async def test_ingest_sub_not_found(client):
    """Test POST /ingest with a valid UUID that doesn't exist."""
    non_existent_id = uuid.uuid4()
    payload = {"data": 123}
    r = await client.post(f"/ingest/{non_existent_id}", json=payload)
    assert r.status_code == 404
    assert "Subscription not found" in r.json()["detail"]

async def test_ingest_invalid_uuid(client):
    """Test POST /ingest with a non-UUID string."""
    payload = {"data": 123}
    r = await client.post("/ingest/not-a-uuid", json=payload)
    assert r.status_code == 422
    assert "valid uuid" in r.json()["detail"][0]["msg"].lower()


async def test_ingest_invalid_json_body(client, redis_conn): # Use redis_conn fixture
    """Test POST /ingest with non-JSON data."""
    # 1) Manually prepare subscription data and cache it
    sub_id = uuid.uuid4()
    sub_data = {
        "id": str(sub_id),
        "target_url": "http://valid-sub.com",
        "secret": None,
        "events": [],
    }
    cache_key = _make_key(str(sub_id))
    redis_conn.set(cache_key, json.dumps(sub_data)) # Use test's redis_conn

    # 2) Send invalid JSON body
    r = await client.post(
        f"/ingest/{sub_id}",
        content="this is not json",            # Raw invalid JSON
        headers={"Content-Type": "application/json"},
    )
    assert r.status_code == 400              # JSON decode error
    assert "detail" in r.json()
    assert "invalid json body" in r.json()["detail"].lower()