import uuid
from uuid import UUID
from fastapi import APIRouter, Header, HTTPException, status, Request
from starlette.responses import JSONResponse
import json

from src.cache.subscription_cache import get_subscription
from src.queue.redis_conn import delivery_queue

router = APIRouter()

@router.post(
    "/ingest/{subscription_id}",
    status_code=status.HTTP_202_ACCEPTED,
    summary="Ingest a webhook and enqueue for delivery",
)
async def ingest_webhook(
    subscription_id: UUID,
    request: Request,
    x_event_type: str | None = Header(None),
    x_signature: str | None = Header(None),
):
    # 1) Cache-first lookup (falls back to DB if needed)
    sub_data = await get_subscription(subscription_id)
    if not sub_data:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Subscription not found",
        )

    # 2) Read payload
    try:
        payload = await request.json()
    except json.JSONDecodeError:
        # If request.json() fails, raise a 400 Bad Request
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Invalid JSON body received.",
        )

    # 3) Generate a webhook_id & enqueue first attempt
    webhook_id = uuid.uuid4()
    delivery_queue.enqueue(
        "src.workers.delivery_worker.process_delivery_sync",
        subscription_id,
        payload,
        x_event_type,
        x_signature,
        webhook_id,
        1,  # attempt number
    )

    # 4) Return 202 + webhook_id for status checks
    return JSONResponse(
        status_code=status.HTTP_202_ACCEPTED,
        content={"webhook_id": str(webhook_id)},
    )
