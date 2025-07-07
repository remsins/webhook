import uuid
from datetime import datetime, timedelta
import pytest

from src.models.subscription import Subscription
from src.models.delivery_log import DeliveryLog

@pytest.fixture
async def setup_logs(async_db_session):
    # Create subscription
    sub_id = uuid.uuid4()
    sub = Subscription(id=sub_id, target_url="http://status-test.local")
    async_db_session.add(sub)
    
    # Create webhook IDs
    wh_id_success = uuid.uuid4()
    wh_id_fail = uuid.uuid4()
    
    now = datetime.utcnow()
    
    logs = [
        DeliveryLog(
            webhook_id=wh_id_fail,
            subscription_id=sub_id,
            target_url=sub.target_url,
            timestamp=now,  # NEWEST timestamp
            attempt_number=3,
            outcome="Failure",
            status_code=503,
            error="Timeout"
        ),
        DeliveryLog(
            webhook_id=wh_id_fail,
            subscription_id=sub_id, 
            target_url=sub.target_url,
            timestamp=now - timedelta(minutes=1),
            attempt_number=2,
            outcome="Failed Attempt",
            status_code=503,
            error="Timeout"
        ),
        DeliveryLog(
            webhook_id=wh_id_fail,
            subscription_id=sub_id,
            target_url=sub.target_url,
            timestamp=now - timedelta(minutes=2),
            attempt_number=1,
            outcome="Failed Attempt",
            status_code=500,
            error="Server Error"
        ),
        DeliveryLog(
            webhook_id=wh_id_success,
            subscription_id=sub_id,
            target_url=sub.target_url,
            timestamp=now - timedelta(minutes=5),  # OLDEST timestamp
            attempt_number=1,
            outcome="Success",
            status_code=200,
            error=None
        )
    ]
    async_db_session.add_all(logs)
    await async_db_session.commit()
    
    return {"sub_id": sub_id, "wh_id_success": wh_id_success, "wh_id_fail": wh_id_fail}


async def test_get_webhook_status_success(client, setup_logs):
    """Test getting status for a webhook that succeeded."""
    wh_id = setup_logs["wh_id_success"]
    sub_id = setup_logs["sub_id"]

    r = await client.get(f"/status/{wh_id}")
    assert r.status_code == 200
    data = r.json()

    assert data["webhook_id"] == str(wh_id)
    assert data["subscription_id"] == str(sub_id)
    assert data["total_attempts"] == 1
    assert data["final_outcome"] == "Success"
    assert data["last_status_code"] == 200
    assert data["error"] is None
    assert len(data["recent_attempts"]) == 1
    assert data["recent_attempts"][0]["outcome"] == "Success"

async def test_get_webhook_status_failure(client, setup_logs):
    """Test getting status for a webhook that ultimately failed."""
    wh_id = setup_logs["wh_id_fail"]
    sub_id = setup_logs["sub_id"]

    r = await client.get(f"/status/{wh_id}")
    assert r.status_code == 200
    data = r.json()

    assert data["webhook_id"] == str(wh_id)
    assert data["subscription_id"] == str(sub_id)
    assert data["total_attempts"] == 3
    # Note: Assumes the last log entry correctly reflects the final outcome.
    # The current status endpoint logic takes the outcome of the *most recent* log.
    assert data["final_outcome"] == "Failure"
    assert data["last_status_code"] == 503
    assert "Timeout" in data["error"]
    # API returns max 20 most recent, here we expect all 3
    assert len(data["recent_attempts"]) == 3
    # Check attempts are ordered newest first
    assert data["recent_attempts"][0]["attempt_number"] == 3
    assert data["recent_attempts"][1]["attempt_number"] == 2
    assert data["recent_attempts"][2]["attempt_number"] == 1

async def test_get_webhook_status_not_found(client):
    """Test getting status for a non-existent webhook ID."""
    non_existent_id = uuid.uuid4()
    r = await client.get(f"/status/{non_existent_id}")
    assert r.status_code == 404
    assert "No delivery logs" in r.json()["detail"]

async def test_list_subscription_attempts(client, setup_logs):
    """Test listing recent attempts for a subscription."""
    sub_id = setup_logs["sub_id"]

    r = await client.get(f"/subscriptions/{sub_id}/attempts?limit=10")
    assert r.status_code == 200
    data = r.json()

    # Should have all 4 logs created in the fixture
    assert len(data) == 4
    # Check they are ordered by timestamp desc (newest first)
    # Attempt 3 of wh_id_2 should be first
    assert data[0]["webhook_id"] == str(setup_logs["wh_id_fail"])
    assert data[0]["attempt_number"] == 3
    # Attempt 1 of wh_id_1 should be last
    assert data[3]["webhook_id"] == str(setup_logs["wh_id_success"])
    assert data[3]["attempt_number"] == 1

async def test_list_subscription_attempts_limit(client, setup_logs):
    """Test the limit parameter for subscription attempts."""
    sub_id = setup_logs["sub_id"]

    r = await client.get(f"/subscriptions/{sub_id}/attempts?limit=2")
    assert r.status_code == 200
    data = r.json()
    assert len(data) == 2
    # Should be the two most recent attempts (attempt 3 and 2 of wh_id_2)
    assert data[0]["attempt_number"] == 3
    assert data[1]["attempt_number"] == 2

async def test_list_subscription_attempts_no_logs(client, async_db_session):
    """Test listing attempts for a subscription with no logs."""
    # Create a subscription but no logs
    sub = Subscription(target_url="http://no-logs-here.com")
    async_db_session.add(sub)
    await async_db_session.commit()

    r = await client.get(f"/subscriptions/{sub.id}/attempts")
    assert r.status_code == 200
    assert r.json() == [] # Expect an empty list