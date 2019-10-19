'''
! cctx를 사용하면 거래소에 관계없이 동일한 인터페이스로 사용할 수 있음.
-> 프로젝트 1차 작성 / 추후 업그레이드 시 활용할것.
'''

import os
import jwt
import uuid
import hashlib
import logging
from requests import Session, get, post
from requests_toolbelt.adapters import source
from time import sleep
import parse
import redis
from urllib.parse import urlencode

from ...misc import get_timestamp, create_logger,\
    create_redis_pool, create_pika_connection, keys2floats

from ...config import THROTTLE_API_DEFAULT_TIME, \
    THROTTLE_REMAIN_MIN_TIME ,THROTTLE_REMAIN_SEC_TIME


# TODO: check api key is invalid
access_key = os.environ['UPBIT_OPEN_API_ACCESS_KEY']
secret_key = os.environ['UPBIT_OPEN_API_SECRET_KEY']


URL_ORDERBOOK = 'https://api.upbit.com/v1/orderbook'
URL_ALL_MARKET = 'https://api.upbit.com/v1/market/all'
URL_MARKET_CHANCE = 'https://api.upbit.com/v1/orders/chance'
URL_ACCOUNT = 'https://api.upbit.com/v1/accounts'

# https://stackoverflow.com/questions/28773033/python-requests-how-to-bind-to-different-source-ip-for-each-request

class UpbitAPIClient(Session):

    logger = None
    remainings = {}

    def __init__(self, source_address: str=None):
        Session.__init__(self)
        self.logger = create_logger('UpbitAPIClient')

        if source_address:
            self.logger.info("mounted at source address: %s" % source_address)
            new_source = source.SourceAddressAdapter(source_address)
            self.mount('http://', new_source)
            self.mount('https://', new_source)

    def build_auth_header(self, query, uuid4):
        query_string = urlencode(query).encode()

        payload = {
            'access_key': access_key,
            'nonce': str(uuid4)
        }

        if len(query.keys()) is not 0:
            m = hashlib.sha512()
            m.update(query_string)
            query_hash = m.hexdigest()
            payload['query_hash'] = query_hash
            payload['query_hash_alg'] = 'SHA512'


        jwt_token = jwt.encode(payload, secret_key).decode('utf-8')
        authorize_token = 'Bearer {}'.format(jwt_token)
        headers = {"Authorization": authorize_token}

        return headers


    def get(self, group, url, params={}, auth=False, **kwargs):
        self.check_and_wait(group)
        if auth:
            _uuid = uuid.uuid4()
            headers = self.build_auth_header(params, _uuid)
            resp = Session.get(self, url=url, params=params, headers=headers, **kwargs)
        else:
            resp = Session.get(self, url=url, params=params, **kwargs)
        return self.finalize(resp)

    def post(self, group, url, params={}, data=None, auth=False, **kwargs):
        self.check_and_wait(group)
        if auth:
            _uuid = uuid.uuid4()
            headers = self.build_auth_header(params, _uuid)
            resp = Session.post(self, url=url, params=params, data=data, headers=headers, **kwargs)
        else:
            resp = Session.post(self, url=url, params=params, data=data, **kwargs)
        return self.finalize(resp)

    def set_initial_remain(self, group):
        self.remainings.setdefault(group, {'min': None, 'sec': None, 'timestamp': None})

    def check_and_wait(self, group, throttle=True):
        # 우선 초 단위의 remain만 핸들링
        self.set_initial_remain(group)
        remain = self.remainings[group]

        # 처음 요청하는 경우 별도로 확인할 필요 없음.
        if remain['timestamp'] is None:
            remain['timestamp'] = get_timestamp()
            return

        # TODO: 스로들링 모듈로 별도 분리?
        # 현재 이전 타임스탬프를 가지고 있음.
        # 현재 타임스탬프와 이전 타임스탬프를 비교해서 계산.
        if throttle:
            tick = get_timestamp() - remain['timestamp'] # 마지막 요청 후 지난 시간
            sl = THROTTLE_API_DEFAULT_TIME - tick

            if sl > 0:
                self.logger.debug("Throttling %s ms" % sl)
                sleep(sl * 0.001) #  millisecond to second

        ## 본 대응법이 오류가 발생하므로 가상 request가 많은 orderbook을 기준으로
        ## 50ms 정도 스토틀링을 추가하였음.
        ## orderobok데이터가 바뀌는 걸 보면 해당 이벤트 발생시마다 바로 반영되는 것이 아니라
        ## 대략 100~200ms 분기별로 데이텨 변경 건이 접수가 되고 있음!
        if remain['min'] is 0:
            self.logger.warn('no remaining in sec! (%s) awaiting %s ms!' % (
                group, THROTTLE_REMAIN_MIN_TIME * 1000
            ))
            while get_timestamp() < remain['timestamp'] + THROTTLE_REMAIN_MIN_TIME:
                sleep(0.05)

        if remain['sec'] is 0:
            self.logger.warn('no remaining in sec! (%s) awaiting %s ms!' % (
                group, THROTTLE_REMAIN_SEC_TIME * 1000
            ))
            while get_timestamp() < remain['timestamp'] + THROTTLE_REMAIN_SEC_TIME:
                sleep(0.05)

    def finalize(self, resp):
        #1. check remaining info!
        _remain_header = resp.headers['Remaining-Req']
        group, min, sec = parse.parse(
            'group={}; min={}; sec={}', _remain_header
        )
        self.set_initial_remain(group)
        remain = self.remainings[group]
        remain['timestamp'] = get_timestamp()
        remain['min'] = int(min)
        remain['sec'] = int(sec)

        self.logger.debug("remaining req: group=%s min=%s sec=%s" % (
            group, min, sec
        ))

        #2. check error info!
        resp_obj = resp.json()
        if type(resp_obj) is dict and 'error' in resp_obj.keys():
            message = resp_obj['error']['message']

            # stack info?
            logging.critical('message: %s' % (
                message
            ))
            raise Exception(message)
        return resp_obj

    #### --- api declaration (provided default)

    def get_orderbook(self, markets):
        if type(markets) is list:
            markets = ",".join(markets)
        return self.get(group='orderbook', url=URL_ORDERBOOK, params={'markets': markets})

    def get_market_status(self, market):
        return self.get(group='orders', url=URL_MARKET_CHANCE, params={'market': market}, auth=True)

    # https://wikidocs.net/64
    def get_all_markets(self):
        return list(map(
            lambda x: x['market'],
            self.get(group="market", url=URL_ALL_MARKET)))


    ### api delcaration (mixed)
    def get_available_markets(self):
        markets = self.get_all_markets()
        results = []

        for market in markets:
            ifo = self.get_market_status(market)
            if ifo['market']['state'] == 'active':
                results.append(market)

        return results

    def get_user_balance(self):
        return self.get(group='account', url=URL_ACCOUNT, auth=True)


    def contract(self):
        pass


    def contract_buy(self):
        pass


    def contract_sell(self):
        pass






## TODO: 각 object에 대해 독립적으로 업데이트 등을 작성하여야 함.

MARKETS_ALL = 'markets'
MARKETS_BASE = 'markets_base'
FEE = 'fee'

class UpbitLocalClient(UpbitAPIClient):
    r = None # type: Redis
    force_update = None # type: bool

    def __init__(self):
        super(UpbitLocalClient, self).__init__()
        pool = create_redis_pool()
        self.r = redis.StrictRedis(connection_pool=pool)
        self.update = False

    @property
    def all_markets(self):
        # 먼저 redis에서 데이터 가져오기
        # 데이터 없거나 force_update 켜져있으면 가져와서 업데이트 자동으로 수행

        # map -> 해당 데이터를 리스트로 반환
        markets = list(map(lambda x: x.decode(), self.r.lrange(MARKETS_ALL, 0, -1)))

        if len(markets) is 0 or self.force_update:
            markets = super().get_all_markets()
            self.r.lpush(MARKETS_ALL, *markets)
            return markets

        # 데이터가 있고 force_update 상태가 아니면 바로 리턴시키면 된다.
        return markets

    @all_markets.setter
    def all_markets(self, value):
        # 캐싱된 데이터를 삭제합니다.
        self.r.delete(MARKETS_ALL)
        self.r.lpush(MARKETS_ALL, *value)


    @property
    def base_markets(self):
        # redis.exceptions.ResponseError: WRONGTYPE Operation against a key holding the wrong kind of value
        # 키가 없는 경우에 위 에러가 발생할 수 있음
        markets = list(map(lambda x: x.decode(), self.r.lrange(MARKETS_BASE, 0, -1)))
        return markets



    @property
    def fee(self):
        fees = self.r.hgetall(FEE); ret = {}
        if len(fees) is None:
            pass # TODO: warning - handling exception support
        keys2floats(fees, ret)
        return ret




'''
TODO:
class 화 하여 작성 -> Remaning 에 대한 대처가 필요함.
'''

'''
TODO

! gracefully shutdown?
! 한꺼번에 전체 마켓에 대한 정보 로드가 불가능함. 기저통화별로 나누어서 데몬을 구동할 것.

: each function 퍼포먼스 분석 :: static class 작성 중
: 로깅 구체화

: profit 계산식 알고리즘에 따라서 orderbook.units 반환 구성을 파악.  =
: 계산식 사전 정의

'''


def _finalize(resp):
    resp_obj = resp.json()

    if type(resp_obj) is dict and 'error' in resp_obj.keys():
        message = resp_obj['error']['message']

        # stack info?
        logging.critical('message: %s' % (
            message
        ))
        raise Exception(message)

    return resp_obj


def get_orderbook(markets, sess:Session=None):
    _func = get if sess is None else sess.get

    if type(markets) is list:
        markets = ",".join(markets)
    resp = _func(url=URL_ORDERBOOK, params={'markets': markets})

    print(resp.headers)

    return _finalize(resp)


def get_all_market(sess:Session=None):
    _func = get if sess is None else sess.get
    resp = _func(url=URL_ALL_MARKET)

    return _finalize(resp)