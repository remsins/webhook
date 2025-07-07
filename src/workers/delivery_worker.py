import logging
import os
import uuid
from datetime import datetime, timedelta
from typing import Optional, Dict, Any, Union
import httpx
from sqlalchemy.ext.asyncio import AsyncSession
import asyncio

from src.db.session import AsyncSessionLocal
from src.models.delivery_log import DeliveryLog
from src.models.subscription import Subscription
from src.queue.redis_conn import delivery_queue
from src.cache.subscription_cache import get_subscription

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

HTTP_TIMEOUT = int(os.getenv("HTTP_TIMEOUT", "5"))
MAX_ATTEMPTS = 5
BACKOFF_SCHEDULE = [10, 30, 60, 300, 900]  # seconds

def ensure_uuid(value: Union[str, uuid.UUID]) -> uuid.UUID:
    """Convert string to UUID if needed."""
    if isinstance(value, str):
        return uuid.UUID(value)
    return value
    
async def log_delivery_attempt(
    session: AsyncSession,
    webhook_id: Union[str, uuid.UUID],
    subscription_id: Union[str, uuid.UUID],
    target_url: str,
    timestamp: datetime,
    attempt_number: int,
    outcome: str,
    status_code: Optional[int] = None,
    error: Optional[str] = None,
):
    """Log a delivery attempt to the database."""
    log = DeliveryLog(
        webhook_id=ensure_uuid(webhook_id),
        subscription_id=ensure_uuid(subscription_id),
        target_url=target_url,
        timestamp=timestamp,
        attempt_number=attempt_number,
        outcome=outcome,
        status_code=status_code,
        error=error,
    )
    session.add(log)
    await session.commit()

async def process_delivery(
    subscription_id: Union[str, uuid.UUID],
    payload: Dict[str, Any],
    event_type: Optional[str],
    signature: Optional[str],
    webhook_id: Union[str, uuid.UUID],
    attempt: int,
):
    """
    1) Fetch subscription from Redis cache (fallback to DB automatically handled).
    2) Attempt HTTP POST to target_url.
    3) Log each attempt to Postgres.
    4) If attempt < MAX, reschedule with exponential backoff.
    """
    # Ensure we have string format for cache lookup
    sub_id_str = str(subscription_id)
    webhook_id_str = str(webhook_id)
    
    # Cache-first subscription lookup (automatically falls back to DB)
    sub_data = await get_subscription(sub_id_str)
    if not sub_data:
        logger.error(f"[Delivery] Sub {sub_id_str} not found, dropping job")
        return

    target = sub_data["target_url"]
    headers = {"Content-Type": "application/json"}
    if event_type:
        headers["X-Event-Type"] = event_type
    if signature:
        headers["X-Signature"] = signature

    async with AsyncSessionLocal() as session:
        try:
            status_code = None
            error_details = None
            outcome = None

            # Perform the POST using async HTTP client
            try:
                async with httpx.AsyncClient(timeout=HTTP_TIMEOUT) as client:
                    resp = await client.post(
                        target,
                        json=payload,
                        headers=headers,
                    )
                    status_code = resp.status_code
                    if 200 <= status_code < 300:
                        outcome = "Success"
                    else:
                        outcome = "Failed Attempt"
                        error_details = f"HTTP {status_code}"
                        logger.error(f"Delivery failed: {error_details}")

                        if attempt < MAX_ATTEMPTS:
                            await log_delivery_attempt(
                                session,
                                webhook_id,
                                subscription_id,
                                target,
                                datetime.utcnow(),
                                attempt,
                                outcome,
                                status_code,
                                error_details,
                            )

                            # Schedule next attempt
                            delay = BACKOFF_SCHEDULE[attempt - 1]
                            delivery_queue.enqueue_in(
                                timedelta(seconds=delay),
                                process_delivery_sync,
                                sub_id_str,  # Pass as string for consistency
                                payload,
                                event_type,
                                signature,
                                webhook_id_str,  # Pass as string for consistency
                                attempt + 1,
                            )
                            return

            except Exception as exc:
                # Recoverable failure: log & re-enqueue if attempts remain
                if attempt < MAX_ATTEMPTS:
                    outcome = "Failed Attempt"
                    error_details = str(exc)

                    # Persist this attempt
                    await log_delivery_attempt(
                        session,
                        webhook_id,
                        subscription_id,
                        target,
                        datetime.utcnow(),
                        attempt,
                        outcome,
                        status_code,
                        error_details,
                    )

                    # Schedule next attempt with backoff
                    delay = BACKOFF_SCHEDULE[attempt - 1]
                    delivery_queue.enqueue_in(
                        timedelta(seconds=delay),
                        process_delivery_sync,
                        sub_id_str,  # Pass as string for consistency
                        payload,
                        event_type,
                        signature,
                        webhook_id_str,  # Pass as string for consistency
                        attempt + 1,
                    )
                    return
                # else fall through to final failure

            # Final log (either success or last failure)
            if outcome is None:
                outcome = "Success"
            await log_delivery_attempt(
                session,
                webhook_id,
                subscription_id,
                target,
                datetime.utcnow(),
                attempt,
                outcome,
                status_code,
                error_details,
            )

        except Exception as e:
            logger.error(f"Error processing delivery: {str(e)}")
            raise

def process_delivery_sync(
    subscription_id: Union[str, uuid.UUID],
    payload: Dict[str, Any],
    event_type: Optional[str],
    signature: Optional[str],
    webhook_id: Union[str, uuid.UUID],
    attempt: int,
):
    """Synchronous wrapper for RQ worker compatibility."""
    try:
        # Create new event loop for the worker
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        loop.run_until_complete(
            process_delivery(
                subscription_id,
                payload,
                event_type,
                signature,
                webhook_id,
                attempt,
            )
        )
    finally:
        loop.close()