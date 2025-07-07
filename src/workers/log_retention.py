import logging
from datetime import datetime, timedelta
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, delete
from src.db.session import AsyncSessionLocal
from src.models.delivery_log import DeliveryLog

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

async def purge_old_logs(db: AsyncSession | None = None):
    """
    Delete delivery logs older than 72 hours.
    Run this once an hour (via cron, RQ scheduler, or docker-compose cron service).

    Args:
        db: Optional async SQLAlchemy session to use. If None, creates a new one.
    """
    session_created = False
    if db is None:
        db = AsyncSessionLocal()
        session_created = True

    try:
        cutoff = datetime.utcnow() - timedelta(hours=72)
        
        # Use async delete operation
        stmt = delete(DeliveryLog).where(DeliveryLog.timestamp < cutoff)
        result = await db.execute(stmt)
        deleted_count = result.rowcount

        # Only commit if we created the session within this function
        if session_created:
            await db.commit()

        logger.info(f"Purged {deleted_count} delivery log(s) before {cutoff.isoformat()}")
        return deleted_count
        
    except Exception:
        # Rollback if we created the session and an error occurred
        if session_created:
            await db.rollback()
        logger.exception("Error during log purge.")
        raise # Re-raise the exception
    finally:
        # Only close if we created the session within this function
        if session_created:
            await db.close()

def purge_old_logs_sync():
    """
    Synchronous wrapper for RQ worker compatibility.
    This allows the async purge function to be called from RQ workers.
    """
    import asyncio
    try:
        # Create new event loop for the worker
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        result = loop.run_until_complete(purge_old_logs())
        return result
    finally:
        loop.close()