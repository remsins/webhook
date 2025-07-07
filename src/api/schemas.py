from typing import List, Optional
from uuid import UUID
from datetime import datetime
from pydantic import BaseModel, AnyHttpUrl


class SubscriptionBase(BaseModel):
    target_url: AnyHttpUrl
    secret: Optional[str] = None
    events: Optional[List[str]] = None

class SubscriptionCreate(SubscriptionBase):
    pass

class SubscriptionUpdate(BaseModel):
    target_url: Optional[AnyHttpUrl] = None
    secret: Optional[str] = None
    events: Optional[List[str]] = None

class SubscriptionOut(SubscriptionBase):
    id: UUID

    class Config:
        from_attributes = True

class DeliveryAttempt(BaseModel):
    id: UUID
    webhook_id: UUID
    subscription_id: UUID
    target_url: AnyHttpUrl
    timestamp: datetime
    attempt_number: int
    outcome: str
    status_code: Optional[int] = None
    error: Optional[str] = None

    class Config:
        from_attributes = True

class StatusResponse(BaseModel):
    webhook_id: UUID
    subscription_id: UUID
    total_attempts: int
    final_outcome: str
    last_attempt_at: datetime
    last_status_code: Optional[int] = None
    error: Optional[str] = None
    recent_attempts: List[DeliveryAttempt]

    class Config:
        from_attributes = True