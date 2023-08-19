import os

from redis import ConnectionPool
from redis import Redis

redis_pool = ConnectionPool.from_url(os.environ["REDIS_DSN"])
redis = Redis(connection_pool=redis_pool)


def telegram(event, context):
    redis.ping()

    return {
        "statusCode": 200,
    }
