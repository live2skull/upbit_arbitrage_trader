from sys import argv, stdout
import signal, os

import logging
from threading import Thread

from requests import Session
import redis
import pika

from dotenv import load_dotenv


from .apis import UpbitAPIClient
from ...misc import create_logger, create_redis_pool\
    , create_pika_connection,  get_timestamp, strs2floats
from ...config import TIMEOUT_REDIS_LOCK


# KRW-BTC_orderbook__lock

# https://redis.io/commands/rpush -> documentation!
# https://www.joinc.co.kr/w/man/12/REDIS/IntroDataType
# https://docs.python.org/2/library/timeit.html | performance checking

PIKA_EXCHANGE = 'orderbook'
PIKA_EXCHANGE_TYPE = 'topic'
PIKA_BASIC_PROPERTY = pika.spec.BasicProperties(delivery_mode=1)

ASK_PRICES = 'ask_prices'
ASK_AMOUNTS = 'ask_amounts'
BID_PRICES = 'bid_prices'
BID_AMOUNTS = 'bid_amounts'

LAST_UPDATE_TIME = 'last_update_time'
LAST_REQUEST_TIME = 'last_request_time'



## ex) KRW-BTC_orderbook_... 형태임
## 이를 orderbook_KRW-BTC_bid_prices 와 같은 형태로 작성.

class Orderbook:

    logger = None
    r = None  # type: redis.Redis

    # ex) KRW-BTC_orderbook
    r_name = ""  # type: str
    # ex) KRW-BTC_orderbook__lock
    r_lock = ""  # type: str
    r_lock_obj = None

    market = None  # type: str
    is_daemon = None # type: bool

    last_update_time = None  # type: long
    last_request_time = None  # type: long

    # for support caching
    _units = None # type: dict


    @property
    def is_units_available(self):
        units = self.units

        for k, v in units.items():
            if len(v) is 0:
                return False
        return True

    @property
    def units(self):
        # 데이터 입력시에는 str (byte) 형태로 저장되므로 반환시에는 float으로 변환 후 처리.

        with self.r_lock_obj:
            last_updated = int(self.r.get("%s_%s" % (self.r_name, LAST_UPDATE_TIME)))
            if last_updated is None:
                self.logger.critical("orderbook 데이터가 존재하지 않음.")
                return None
            if last_updated > self.last_update_time:
                strs2floats(
                    self.r.lrange("%s_%s" % (self.r_name, ASK_PRICES), 0, -1),
                    self._units[ASK_PRICES]
                )
                strs2floats(
                    self.r.lrange("%s_%s" % (self.r_name , ASK_AMOUNTS), 0, -1),
                    self._units[ASK_AMOUNTS]
                )
                strs2floats(
                    self.r.lrange("%s_%s" % (self.r_name , BID_PRICES), 0, -1),
                    self._units[BID_PRICES]
                )
                strs2floats(
                    self.r.lrange("%s_%s" % (self.r_name , BID_AMOUNTS), 0, -1),
                    self._units[BID_AMOUNTS]
                )

                # 데이터가 변경되는 상황은 없으니, 별도의 copy를 하지 않아도 무방합니다.
                return self._units

            else:
                return self._units


    def _update_timestamp(self):
        self.r.set("%s_%s" % (self.r_name, LAST_REQUEST_TIME), self.last_request_time)
        self.r.set("%s_%s" % (self.r_name, LAST_UPDATE_TIME), self.last_update_time)

    def _update_orderbook(self, units):
        self.r.delete("%s_%s" % (self.r_name , ASK_PRICES))
        self.r.delete("%s_%s" % (self.r_name , ASK_AMOUNTS))
        self.r.delete("%s_%s" % (self.r_name , BID_PRICES))
        self.r.delete("%s_%s" % (self.r_name , BID_AMOUNTS))

        bid_prices = []; bid_sizes = []
        ask_prices = []; ask_sizes = []

        for u in units:
            bid_prices.append(u['bid_price'])
            bid_sizes.append(u['bid_size'])
            ask_prices.append(u['ask_price'])
            ask_sizes.append(u['ask_size'])

        self.r.rpush("%s_%s" % (self.r_name , ASK_PRICES), *ask_prices)
        self.r.rpush("%s_%s" % (self.r_name , ASK_AMOUNTS), *ask_sizes)
        self.r.rpush("%s_%s" % (self.r_name , BID_PRICES), *bid_prices)
        self.r.rpush("%s_%s" % (self.r_name , BID_AMOUNTS), *bid_sizes)

    def update(self, timestamp, units):
        self.last_request_time = get_timestamp()

        if timestamp <= self.last_update_time:
            # last_request_time 은 별도로 접근할때 충돌 위험이 크지 않으므로 별도로 lock하지 않습니다.
            self.r.set("%s_%s" % (self.r_name, LAST_REQUEST_TIME), self.last_request_time)
            # with self.r.lock(self.r_lock, blocking_timeout=TIMEOUT_REDIS_LOCK) as lock:
            #     self._update_timestamp()
            return False

        else:
            with self.r_lock_obj:
                self._update_timestamp()
                self._update_orderbook(units)

            ## TODO: add initialized flag
            if self.last_update_time is 0:
                # 초기화 동작은 업데이트로 전파하지 않음.
                # -> 업데이트로 전파하지 않았을 뿐
                # 호가 데이터 정보는 조회할 수 있다.
                self.last_update_time = timestamp
                return False
            else:
                self.last_update_time = timestamp
                self.logger.info('orderbook updated.')
                return True

    ## support *redis* memory sharing!
    def __init__(self, market: str, pool=None):
        self.market = market
        self.last_request_time = 0
        self.last_update_time = 0


        self.r_name = "orderbook_%s" % self.market
        self.r_lock = "%s__lock" % self.r_name

        self.is_daemon = pool is not None

        # 일반 테스트 모드에서 실행할 경우 자동으로 커넥션을 만듭니다.
        self.r = redis.Redis(connection_pool=pool if pool else create_redis_pool())
        self.r_lock_obj = self.r.lock(self.r_lock, blocking_timeout=TIMEOUT_REDIS_LOCK)
        # self.r.delete(self.r_lock)

        self.logger = create_logger(self.r_name)
        # 유닛 데이터를 초기화합니다.
        self._units = {
            BID_AMOUNTS: [], BID_PRICES: [], ASK_AMOUNTS: [], ASK_PRICES: []
        }

    def __del__(self):
        if self.is_daemon:
            try: self.r.delete(self.r_lock)
            except: pass


class OrderbookDaemon(Thread):
    logger = None

    is_running = None  # type: bool
    upbit_client = None # type: UpbitAPIClient
    redis_pool = None  # type: redis.ConnectionPool
    pika_conn = None
    pika_channel = None  # type: BlockingChannel

    market_base = None # type: str
    markets = None # type: dict
    markets_str = None # type: str

    def __init__(self, market_base:str, markets: list, source_address: str=None):
        ## TODO: 데몬이 사전에 실행되고 있는가?

        Thread.__init__(self)
        self.is_running = False
        self.markets_str = markets
        self.market_base = market_base
        self.markets = dict()

        self.upbit_client = UpbitAPIClient(source_address=source_address)
        self.redis_pool = create_redis_pool()
        self.pika_conn = create_pika_connection()
        self.pika_channel = self.pika_conn.channel()

        self.pika_channel.exchange_declare(PIKA_EXCHANGE, exchange_type=PIKA_EXCHANGE_TYPE)

        # initializing orderbook
        # def __init__(self, market: str, pool):
        # 이렇게 하면 각각의 orderbook 객체별로 하나의 커넥션을 이용해 redis를 이용할 수 있습니다.
        for market in markets:
            self.markets.setdefault(market, Orderbook(market, self.redis_pool))

        # 로깅 옵션을 설정합니다.
        self.logger = create_logger("%s_orderbook_daemon" % self.market_base)


    # overwrite
    def run(self):
        self.logger.info("%s 마켓 호가 데몬이 시작되었습니다. (총 %s개 로드)" % (
            self.market_base, len(self.markets)
        ))

        self.is_running = True
        self.loop()

    # overwrite
    def join(self, timeout=None):
        self.is_running = False
        Thread.join(self, timeout)

    def loop(self):
        while self.is_running:
            resp = self.upbit_client.get_orderbook(self.markets_str)

            for ifo in resp:
                market = ifo['market']
                timestamp = ifo['timestamp']
                units = ifo['orderbook_units']

                updated = self.markets[market].update(timestamp, units)
                if updated:
                    self.pika_channel.basic_publish(
                        exchange=PIKA_EXCHANGE, routing_key=market,
                        body=str(timestamp),
                        properties=PIKA_BASIC_PROPERTY
                    )

            # market 별로 데이터 추출해서 orderbook에 넣어줍니다.

    def send_update_event(self, market):
        # TODO: using rabbitmq messenger!
        pass
