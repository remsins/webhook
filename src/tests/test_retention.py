from datetime import datetime, timedelta
import uuid
import pytest

from src.models.delivery_log import DeliveryLog
from src.workers.log_retention import purge_old_logs

@pytest.mark.asyncio
async def test_purge_old_logs(async_db_session):
    # Insert one old and one recent log
    old_id = uuid.uuid4()  # Save IDs for later queries
    new_id = uuid.uuid4()
    
    old = DeliveryLog(
        id=old_id,  # Explicitly set ID
        webhook_id=uuid.uuid4(),
        subscription_id=uuid.uuid4(),
        target_url="http://old",
        timestamp=datetime.utcnow() - timedelta(hours=73),
        attempt_number=1,
        outcome="Failed"
    )
    new = DeliveryLog(
        id=new_id,  # Explicitly set ID
        webhook_id=uuid.uuid4(),
        subscription_id=uuid.uuid4(),
        target_url="http://new",
        timestamp=datetime.utcnow() - timedelta(hours=1),
        attempt_number=1,
        outcome="Success"
    )
    async_db_session.add_all([old, new])
    await async_db_session.flush()

    # Purge using the *same* async session
    deleted_count = await purge_old_logs(db=async_db_session)

    # Verify the right number of logs were deleted
    assert deleted_count == 1

    # Query for the specific logs we created
    from sqlalchemy import select
    
    old_result = await async_db_session.execute(
        select(DeliveryLog).where(DeliveryLog.id == old_id)
    )
    old_exists = old_result.scalar_one_or_none() is not None
    
    new_result = await async_db_session.execute(
        select(DeliveryLog).where(DeliveryLog.id == new_id)
    )
    new_exists = new_result.scalar_one_or_none() is not None

    # Assert that only the new log remains
    assert not old_exists, "Old log should have been deleted"
    assert new_exists, "New log should still exist"