from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from typing import List
from uuid import UUID

from src.db.session import AsyncSessionLocal
from src.models.subscription import Subscription
from src.api.schemas import (
    SubscriptionCreate,
    SubscriptionOut,
    SubscriptionUpdate,
)
from src.cache.subscription_cache import (
    cache_subscription,
    invalidate_subscription,
    get_subscription
)

router = APIRouter()

async def get_async_db():
    async with AsyncSessionLocal() as session:
        yield session

@router.post(
    "/",
    response_model=SubscriptionOut,
    status_code=status.HTTP_201_CREATED,
)
async def create_subscription(
    subscription_in: SubscriptionCreate,
    db: AsyncSession = Depends(get_async_db),
):
    # Convert Pydantic model to dict
    sub_data = subscription_in.dict()

    # Convert AnyHttpUrl to string before creating SQLAlchemy model 
    if sub_data.get("target_url"):
        sub_data["target_url"] = str(sub_data["target_url"])

    # Create SQLAlchemy model instance
    sub = Subscription(**sub_data)

    db.add(sub)
    await db.commit()
    await db.refresh(sub)

    # Cache the new subscription
    cache_subscription(sub)

    return sub

@router.get("/{subscription_id}", response_model=SubscriptionOut)
async def read_subscription(
    subscription_id: UUID,
    db: AsyncSession = Depends(get_async_db),
):
    # Cache-first lookup (automatically falls back to database)
    sub_data = await get_subscription(subscription_id, db)
    if not sub_data:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Subscription not found",
        )
    
    return sub_data

@router.get("/", response_model=List[SubscriptionOut])
async def list_subscriptions( # Not looking at cache here since it might not always have all subscriptions
    skip: int = 0,
    limit: int = 100,
    db: AsyncSession = Depends(get_async_db),
):
    result = await db.execute(
        select(Subscription)
        .offset(skip)
        .limit(limit)
    )
    return result.scalars().all()

@router.patch("/{subscription_id}", response_model=SubscriptionOut)
async def update_subscription(
    subscription_id: UUID,
    subscription_in: SubscriptionUpdate,
    db: AsyncSession = Depends(get_async_db),
):
    result = await db.execute(
        select(Subscription)
        .where(Subscription.id == subscription_id)
    )
    sub = result.scalar_one_or_none()

    if not sub:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Subscription not found",
        )

    # Get update data, excluding unset fields
    update_data = subscription_in.dict(exclude_unset=True)

    for field, value in update_data.items():
        # Convert AnyHttpUrl to string if target_url is being updated
        if field == "target_url" and value is not None:
            setattr(sub, field, str(value))
        else:
            setattr(sub, field, value) # Set other fields normally

    await db.commit()
    await db.refresh(sub)

    # Update cache
    cache_subscription(sub)

    return sub

@router.delete(
    "/{subscription_id}",
    status_code=status.HTTP_204_NO_CONTENT,
)
async def delete_subscription(
    subscription_id: UUID,
    db: AsyncSession = Depends(get_async_db),
):
    result = await db.execute(
        select(Subscription)
        .where(Subscription.id == subscription_id)
    )
    sub = result.scalar_one_or_none()
    
    if not sub:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Subscription not found",
        )
    
    await db.delete(sub)
    await db.commit()

    # Invalidate cache
    invalidate_subscription(subscription_id)

    # No return needed for 204
    return