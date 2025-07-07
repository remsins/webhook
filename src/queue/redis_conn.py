import os
import redis
from rq import Queue

REDIS_URL = os.getenv("REDIS_URL")
if REDIS_URL is None:
    raise ValueError("REDIS_URL environment variable not set")

# Redis connection & RQ queue for delivery jobs
redis_conn_global = redis.from_url(REDIS_URL, decode_responses=True)
delivery_queue = Queue("deliveries", connection=redis_conn_global)

def get_redis() -> redis.Redis:
    """FastAPI dependency that provides a Redis connection."""
    # For now, return the globally configured connection
    return redis_conn_global