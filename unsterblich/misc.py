import time
import logging
import os, sys
import redis

import pika

from requests import Session


def _get_default(os_env, recv):
    return recv if recv else os.getenv(os_env, None)


def get_timestamp():
    # 1566020586537
    # 1565988623993
    # pre, flt = str(time.time()).split('.')

    return int(time.time() * 1000)


def strs2floats(val: list, target: list):
    target.clear()
    for v in val: target.append(float(v))


def keys2floats(val: dict, target: dict):
    target.clear()
    for k, v in val.items(): target.setdefault(k.decode(), float(v))


def create_logger(name: str, level:int = None, format:str = None,
                  propagate=False):

    level = int(_get_default('LOGGING_LEVEL', level))
    format = _get_default('LOGGING_FORMAT', format)

    logger = logging.getLogger(name)
    logger.setLevel(level)
    logger.propagate = propagate

    formatter = logging.Formatter(format)
    stream_handler = logging.StreamHandler()
    stream_handler.setFormatter(formatter)
    logger.addHandler(stream_handler)

    return logger


def create_pika_connection(host=None, port=None, user=None, password=None,
                           virtual_host=None):

    host = _get_default('PIKA_HOST', host)
    port = _get_default('PIKA_PORT', port)
    user = _get_default('PIKA_USER', user)
    password = _get_default('PIKA_PASSWORD', password)
    virtual_host = _get_default('PIKA_VIRTUAL_HOST', virtual_host)

    conn = pika.BlockingConnection(
        pika.ConnectionParameters(
            host=host, port=port, virtual_host=virtual_host,
            credentials=pika.PlainCredentials(user, password),
            heartbeat=5
        )
    )
    return conn


def create_redis_pool(host=None, port=None, db=None):
    host = _get_default('REDIS_HOST', host)
    port = _get_default('REDIS_PORT', port)
    db = _get_default('REDIS_DB', db)

    return redis.ConnectionPool(host=host, port=port, db=db)


def create_web_session():
    sess = Session()
    del sess.headers['User-Agent']

    return sess



class PerformanceCounter:
    name = "Example"

    @staticmethod
    def static():
        print ("s static() called")
