#!/usr/bin/env python
# __author__ = "Ronie Martinez"
# __copyright__ = "Copyright 2019, Ronie Martinez"
# __credits__ = ["Ronie Martinez"]
# __license__ = "MIT"
# __maintainer__ = "Ronie Martinez"
# __email__ = "ronmarti18@gmail.com"
import logging
import os

from redis import StrictRedis

logger = logging.getLogger(__name__)
redis_client = None


def get_redis_client():
    global redis_client
    if not redis_client:
        for _ in range(3):
            try:
                redis_client = StrictRedis(
                    host=os.getenv('REDIS_HOST'),
                    port=os.getenv('REDIS_PORT'),
                    db=os.getenv('REDIS_DB'),
                    password=os.getenv('REDIS_PASSWORD'),
                    encoding='utf-8'
                )
                assert redis_client.ping()
                break
            except Exception as e:
                logger.exception(e)
    return redis_client
