import uuid
from datetime import datetime, timedelta
import pytest
from unittest.mock import MagicMock, AsyncMock
import asyncio

import httpx
from sqlalchemy import select

from src.workers.delivery_worker import (
    process_delivery,
    process_delivery_sync,
    MAX_ATTEMPTS,
    BACKOFF_SCHEDULE,
)
from src.models.subscription import Subscription
from src.models.delivery_log import DeliveryLog
from src.cache.subscription_cache import cache_subscription
from src.queue.redis_conn import delivery_queue

# --- Test Data ---
TEST_URL = "http://test-target.local"
TEST_PAYLOAD = {"message": "hello"}
TEST_EVENT_TYPE = "test.event"
TEST_SIGNATURE = "sha256=test"

@pytest.fixture
async def test_sub(async_db_session):
    """Creates a subscription and caches it for worker tests."""
    sub = Subscription(target_url=TEST_URL, secret="test_secret")
    async_db_session.add(sub)
    await async_db_session.commit() # Commit here as worker runs in separate 'transaction'
    await async_db_session.refresh(sub)
    cache_subscription(sub) # Ensure it's in cache for the worker
    return sub

@pytest.mark.asyncio
async def test_process_delivery_success(
    test_sub, async_db_session, mocker # Use async session
):
    """Test successful delivery on the first attempt."""
    webhook_id = uuid.uuid4()
    subscription_id = test_sub.id

    # Mock AsyncSessionLocal to return our test session
    mock_session_context = AsyncMock()
    mock_session_context.__aenter__.return_value = async_db_session
    mock_session_context.__aexit__.return_value = None
    mocker.patch("src.workers.delivery_worker.AsyncSessionLocal", return_value=mock_session_context)

    # Mock httpx.AsyncClient instead of requests.post
    mock_response = MagicMock()
    mock_response.status_code = 200
    mock_client = AsyncMock()
    mock_client.post.return_value = mock_response
    
    # Mock the context manager
    mock_async_client = AsyncMock()
    mock_async_client.__aenter__.return_value = mock_client
    mock_async_client.__aexit__.return_value = None
    mocker.patch("httpx.AsyncClient", return_value=mock_async_client)

    # Mock the enqueue_in method (it shouldn't be called on success)
    mock_enqueue_in = mocker.patch(
        "src.workers.delivery_worker.delivery_queue.enqueue_in"
    )

    # Execute the worker function
    await process_delivery(
        subscription_id=subscription_id,
        payload=TEST_PAYLOAD,
        event_type=TEST_EVENT_TYPE,
        signature=TEST_SIGNATURE,
        webhook_id=webhook_id,
        attempt=1,
    )

    # Assertions
    # 1. httpx.AsyncClient.post was called correctly
    mock_client.post.assert_called_once_with(
        TEST_URL,
        json=TEST_PAYLOAD,
        headers={
            "Content-Type": "application/json",
            "X-Event-Type": TEST_EVENT_TYPE,
            "X-Signature": TEST_SIGNATURE,
        },
    )

    # 2. No retry was scheduled
    mock_enqueue_in.assert_not_called()

    # 3. Success log entry was created
    result = await async_db_session.execute(
        select(DeliveryLog).where(DeliveryLog.webhook_id == webhook_id)
    )
    log = result.scalar_one()
    assert log.subscription_id == subscription_id
    assert log.attempt_number == 1
    assert log.outcome == "Success"
    assert log.status_code == 200
    assert log.error is None

@pytest.mark.asyncio
async def test_process_delivery_retry_on_http_failure(
    test_sub, async_db_session, delivery_queue, mocker
):
    """Test failure (non-2xx) leading to a retry."""
    webhook_id = uuid.uuid4()
    subscription_id = test_sub.id
    initial_attempt = 1

    # Mock AsyncSessionLocal to return our test session
    mock_session_context = AsyncMock()
    mock_session_context.__aenter__.return_value = async_db_session
    mock_session_context.__aexit__.return_value = None
    mocker.patch("src.workers.delivery_worker.AsyncSessionLocal", return_value=mock_session_context)

    # Mock httpx to return a server error
    mock_response = MagicMock()
    mock_response.status_code = 503
    mock_client = AsyncMock()
    mock_client.post.return_value = mock_response
    
    mock_async_client = AsyncMock()
    mock_async_client.__aenter__.return_value = mock_client
    mock_async_client.__aexit__.return_value = None
    mocker.patch("httpx.AsyncClient", return_value=mock_async_client)

    # Mock the enqueue_in method to capture arguments
    mock_enqueue_in = mocker.patch(
        "src.workers.delivery_worker.delivery_queue.enqueue_in"
    )

    # Execute the worker function for the first attempt
    await process_delivery(
        subscription_id=subscription_id,
        payload=TEST_PAYLOAD,
        event_type=TEST_EVENT_TYPE,
        signature=TEST_SIGNATURE,
        webhook_id=webhook_id,
        attempt=initial_attempt,
    )

    # Assertions
    # 1. httpx post was called
    mock_client.post.assert_called_once()

    # 2. Retry was scheduled with correct parameters
    expected_delay = timedelta(seconds=BACKOFF_SCHEDULE[initial_attempt - 1])
    mock_enqueue_in.assert_called_once_with(
        expected_delay,
        process_delivery_sync, # Should call sync wrapper
        str(subscription_id), # Should be string
        TEST_PAYLOAD,
        TEST_EVENT_TYPE,
        TEST_SIGNATURE,
        str(webhook_id), # Should be string
        initial_attempt + 1,
    )

    # 3. "Failed Attempt" log entry was created
    result = await async_db_session.execute(
        select(DeliveryLog).where(DeliveryLog.webhook_id == webhook_id)
    )
    log = result.scalar_one()
    assert log.subscription_id == subscription_id
    assert log.attempt_number == initial_attempt
    assert log.outcome == "Failed Attempt"
    assert log.status_code == 503
    assert "HTTP 503" in log.error

@pytest.mark.asyncio
async def test_process_delivery_retry_on_timeout(
    test_sub, async_db_session, delivery_queue, mocker
):
    """Test failure (timeout) leading to a retry."""
    webhook_id = uuid.uuid4()
    subscription_id = test_sub.id
    initial_attempt = 2 # Simulate a later attempt

    # Mock AsyncSessionLocal to return our test session
    mock_session_context = AsyncMock()
    mock_session_context.__aenter__.return_value = async_db_session
    mock_session_context.__aexit__.return_value = None
    mocker.patch("src.workers.delivery_worker.AsyncSessionLocal", return_value=mock_session_context)

    # Mock httpx to raise a timeout exception
    mock_client = AsyncMock()
    mock_client.post.side_effect = httpx.TimeoutException("Connection timed out")
    
    mock_async_client = AsyncMock()
    mock_async_client.__aenter__.return_value = mock_client
    mock_async_client.__aexit__.return_value = None
    mocker.patch("httpx.AsyncClient", return_value=mock_async_client)

    mock_enqueue_in = mocker.patch(
        "src.workers.delivery_worker.delivery_queue.enqueue_in"
    )

    # Execute the worker function
    await process_delivery(
        subscription_id=subscription_id,
        payload=TEST_PAYLOAD,
        event_type=TEST_EVENT_TYPE,
        signature=TEST_SIGNATURE,
        webhook_id=webhook_id,
        attempt=initial_attempt,
    )

    # Assertions
    # 1. httpx post was called
    mock_client.post.assert_called_once()

    # 2. Retry was scheduled
    expected_delay = timedelta(seconds=BACKOFF_SCHEDULE[initial_attempt - 1])
    mock_enqueue_in.assert_called_once_with(
        expected_delay,
        process_delivery_sync,
        str(subscription_id),
        TEST_PAYLOAD,
        TEST_EVENT_TYPE,
        TEST_SIGNATURE,
        str(webhook_id),
        initial_attempt + 1,
    )

    # 3. "Failed Attempt" log entry was created for timeout
    result = await async_db_session.execute(
        select(DeliveryLog).where(DeliveryLog.webhook_id == webhook_id)
    )
    log = result.scalar_one()
    assert log.subscription_id == subscription_id
    assert log.attempt_number == initial_attempt
    assert log.outcome == "Failed Attempt"
    assert log.status_code is None # No status code on timeout
    assert "Connection timed out" in log.error

def test_process_delivery_sync_wrapper(mocker):
    """Test the synchronous wrapper function."""
    webhook_id = uuid.uuid4()
    subscription_id = uuid.uuid4()  # Just use a generated UUID

    # Mock the async function
    mock_async_process = mocker.patch(
        "src.workers.delivery_worker.process_delivery", 
        new_callable=AsyncMock
    )

    # Call the sync wrapper
    process_delivery_sync(
        subscription_id=subscription_id,
        payload=TEST_PAYLOAD,
        event_type=TEST_EVENT_TYPE,
        signature=TEST_SIGNATURE,
        webhook_id=webhook_id,
        attempt=1,
    )

    # Verify the async function was called
    mock_async_process.assert_called_once_with(
        subscription_id,
        TEST_PAYLOAD,
        TEST_EVENT_TYPE,
        TEST_SIGNATURE,
        webhook_id,
        1,
    )