import uuid
from datetime import datetime
from sqlalchemy import Column, Text, Integer, DateTime
from sqlalchemy.dialects.postgresql import UUID as PG_UUID
from src.db.session import Base


class DeliveryLog(Base):
    __tablename__ = "delivery_logs"

    id = Column(
        PG_UUID(as_uuid=True),
        primary_key=True,
        default=uuid.uuid4,
    )
    webhook_id = Column(
        PG_UUID(as_uuid=True),
        nullable=False,
        index=True,
    )
    subscription_id = Column(
        PG_UUID(as_uuid=True),
        nullable=False,
        index=True,
    )
    target_url = Column(Text, nullable=False)
    timestamp = Column(
        DateTime(timezone=False),
        default=datetime.utcnow,
        nullable=False,
    )
    attempt_number = Column(Integer, nullable=False)
    # "Success", "Failed Attempt", "Failure"
    outcome = Column(Text, nullable=False)
    status_code = Column(Integer, nullable=True)
    error = Column(Text, nullable=True)
