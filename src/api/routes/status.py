from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import func
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from uuid import UUID
from typing import List

from src.db.session import AsyncSessionLocal
from src.models.delivery_log import DeliveryLog
from src.api.schemas import DeliveryAttempt, StatusResponse

router = APIRouter()

async def get_async_db():
    async with AsyncSessionLocal() as session:
        yield session

@router.get(
    "/status/{webhook_id}",
    response_model=StatusResponse,
    summary="Get delivery status and recent attempts for a webhook",
)
async def get_webhook_status(
    webhook_id: UUID,
    db: AsyncSession = Depends(get_async_db),
):
    # 1) total count
    total = await db.scalar(
        select(func.count(DeliveryLog.id))
        .where(DeliveryLog.webhook_id == webhook_id)
    )
    if total == 0:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="No delivery logs for given webhook_id",
        )

    # 2) recent attempts (most recent first, up to 20)
    logs = await db.execute(
        select(DeliveryLog)
        .where(DeliveryLog.webhook_id == webhook_id)
        .order_by(DeliveryLog.timestamp.desc())
        .limit(20)
    )
    logs = logs.scalars().all()

    last = logs[0]
    return {
        "webhook_id": webhook_id,
        "subscription_id": last.subscription_id,
        "total_attempts": total,
        "final_outcome": last.outcome,
        "last_attempt_at": last.timestamp,
        "last_status_code": last.status_code,
        "error": last.error,
        "recent_attempts": logs,
    }

@router.get(
    "/subscriptions/{subscription_id}/attempts",
    response_model=List[DeliveryAttempt],
    summary="List recent delivery attempts for a subscription",
)
async def list_subscription_attempts(
    subscription_id: UUID,
    limit: int = 20,
    db: AsyncSession = Depends(get_async_db),
):
    logs = await db.execute(
        select(DeliveryLog)
        .where(DeliveryLog.subscription_id == subscription_id)
        .order_by(DeliveryLog.timestamp.desc())
        .limit(limit)
    )
    return logs.scalars().all()