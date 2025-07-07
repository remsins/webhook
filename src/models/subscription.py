import uuid
from sqlalchemy import Column, Text
from sqlalchemy.dialects.postgresql import UUID, ARRAY
from src.db.session import Base

class Subscription(Base):
    __tablename__ = "subscriptions"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    target_url = Column(Text, nullable=False)
    secret = Column(Text, nullable=True)
    events = Column(ARRAY(Text), nullable=True)