from threading import Thread, Lock
from time import sleep
import math

from .apis import UpbitAPIClient
from .transaction import Wallet, Transaction, TRX_BUY, TRX_SELL
from .orderbook import ASK_PRICES, ASK_AMOUNTS, BID_PRICES, BID_AMOUNTS
from .calculator import get_market_buy_price, get_limit_buy_volume_price, get_limit_sell_volume_price

from ...misc import create_logger

log = create_logger(name='UpbitContractor', level=0)

CONTRACT_WAIT_SEC = 0.2
CONTRACT_WAIT_COUNT = 5


class FastContraction:

    _is_running = None # type: bool
    _lock = None # type: Lock

    api = None # type: UpbitAPIClient
    wallet = None # type: Wallet
    wallet_status = None # type: dict

    """
    #1. 데이터 순서대로 거래하게 된다.
    
    """

    def update_wallet_state_val(self):
        self.wallet_status = self.api.get_user_balance()

    def update_wallet(self):

        self.update_wallet_state_val()

        for stat in self.wallet_status:
            coin = stat['currency']
            balance = float(stat['balance'])
            # locked = float(stat['locked'])

            # if not locked == 0:
                # log.warning("%s currently contracting!" % coin)
                # 컨트렉팅인지 판단 여부 / 대기 여부는  wait_for_finish_contract 에서 확인
                # continue

            self.wallet.set(coin, balance)
            
    def wait_for_finish_contract(self, transaction: Transaction):

        ## TODO: obj -> ... 데이터를 LINQ 처럼 검색할 수는 없을까?
        ## TODO: wallet status 추적 필요할듯.

        required_coin = transaction.coin_contract
        self.update_wallet_state_val()

        def is_contracting():
            for stat in self.wallet_status:
                if stat['currency'] == required_coin:
                    return not float(stat['locked']) == 0

            # KRW-SOLVE -> 매도까지 됬는데?
            # 완료되면 잔금이 없을 경우 사라졌을 수 있다는것임. 실패한 것이 아님!
            # raise ValueError(
            #     "거래에 필요한 화폐가 존재하지 않습니다. (%s / %s)" % (transaction.market, transaction.coin_contract)
            # )
            return False # ??!!

        count = 0

        while is_contracting():
            count += 1
            if count == CONTRACT_WAIT_COUNT:
                raise TimeoutError("거래가 지정된 시간 안에 종료되지 않았습니다. (%s)" % transaction.market)

            sleep(CONTRACT_WAIT_COUNT)
            self.update_wallet_state_val()



    ## 매도호가 간 간격이 넓어 시장가 주문 시 손실이 발생할 수 있습니다. 잠시 후 다시 이용하시거나, 지정가 주문을 이용해 주세요.
    ## -> 수수료 계산 오류
    
    ## 현재 해당 마켓에서 지원하지 않는 주문입니다. 주문 조건을 다시 확인해주시기 바랍니다.
    ## -> KRW마켓에서만 시장가 주문이 가능
    
    # buy_price / sell_volume 동일하나, 시장가 거래가 지원되지 않을 경우 필요함.

    def get_krw_buy_option(self, value):
        # KRW마켓 -> 시장가만 사용할 것임.
        # 단, 원화로 구매할 경우에는 해당 원화는 소숫점 지원이 되지 않는다.
        return math.trunc(value)


    def get_krw_sell_option(self, value):
        return value


    def get_buy_market_price(self, transaction: Transaction):
        _price = get_market_buy_price(
            self.wallet.get(transaction.coin_contract), transaction.fee
        )

        ## 무조건 넣으면 되는것이아니라 여기서 수수료를 제외하고 주문하여야한다.
        price = self.get_krw_buy_option(_price) if transaction.is_krw else _price
        return price


    def get_sell_market_volume(self, transaction: Transaction):
        _price = self.wallet.get(transaction.coin_contract)
        
        ## 판매할 때는 해당 대금이 
        price = self.get_krw_sell_option(_price) if transaction.is_krw else _price
        return price


    def get_ord_type(self, transaction: Transaction):
        # 원화 마켓에서는 시장가 주문이 가능합니다.
        if transaction.is_krw:
            return 'price' if transaction.transaction_type is TRX_BUY else 'market'
        else:
            return 'limit'


    def contract(self, transaction: Transaction, vol=None, pri=None, maximum_contract=None, allow_market_order=True):

        ## TODO: volume / price (forced) usage?

        # 매수 / 매도에 따라서 필요한 금액을 선정해야 합니다.
        # 거래해야 하는 화폐가 locked인 경우 -> 아직 거래중임. 
        self.update_wallet()
        self.wait_for_finish_contract(transaction) # 이미 거래중인지 체크

        market = transaction.market
        side = 'bid' if transaction.transaction_type is TRX_BUY else 'ask'
        ord_type = self.get_ord_type(transaction) if allow_market_order else 'limit'
        volume = float(0.0)
        price = float(0.0)


        # 최대 가격 적용 / 구매일 경우 -> 기저화폐의 크기를 wallet에서 강제변환
        # 최소 가격 적용 / 판매일 경우 -> 해당코인의 크기를 wallet에서 강제변환
        # 두 경우 다 상관없이 coin_contract의 크기를 조정합니다.
        if maximum_contract:
            if self.wallet.get(transaction.coin_contract) > maximum_contract:
                self.wallet.set(transaction.coin_contract, float(maximum_contract))


        # 시장가 주문 사용
        if transaction.is_krw and allow_market_order:

            # 시장가 매도 시 필수
            _volume = float(0.0) \
                if transaction.transaction_type is TRX_BUY else \
                volume if vol else self.get_sell_market_volume(transaction)

            # 시장가 매수 시 필수
            _price = float(0.0) \
                if transaction.transaction_type is TRX_SELL else \
                price if pri else self.get_buy_market_price(transaction)

            volume += _volume
            price += _price


        # 지정가 주문 사용
        else:

            units = transaction.orderbook.units

            # 구매에서 문제가 발생하곤 한다.
            _volume, _price = get_limit_buy_volume_price( # 구매할 경우 알맞은 코인 갯수와 가격이 필요.
                    balance=self.wallet.get(transaction.coin_base),
                    fee=transaction.fee,
                    ask_prices=units[ASK_PRICES],
                    ask_amounts=units[ASK_AMOUNTS],
                    isKRW=transaction.is_krw)\
                if transaction.transaction_type is TRX_BUY else \
                get_limit_sell_volume_price( # 판매할 경우 가격만 주면된다. ->  해당 함수에서 계산됨.
                    amount=self.wallet.get(transaction.coin_target),
                    fee=transaction.fee,
                    bid_prices=units[BID_PRICES],
                    bid_amounts=units[BID_AMOUNTS],
                    isKRW=transaction.is_krw
                )

            # 얼마만큼의 양을 판매?
            volume += _volume

            # 가격은?
            price += _price


        if volume == 0: volume = None
        if price == 0: price = None

        log.info("start contract: %s (%s / %s) vol=%s price=%s" % (
            market, side, ord_type, volume, price
        ))

        ## TODO: unexceptable contract handling!
        ## TODO: error handling!
        return self.api.contract(market=market, side=side,
                          ord_type=ord_type, volume=volume, price=price)

        

    @property
    def is_contracting(self):
        with self._lock:
            return self._is_running

    def set_contracting(self, state):
        assert isinstance(state, bool)
        with self._lock:
            self._is_running = state


    def start_contract(self, transactions: list, maximum_contract: float):
        self.set_contracting(True)

        for tr in transactions:
            assert isinstance(tr, Transaction)

        tr_first = transactions[0]  # type: Transaction
        coin_start = tr_first.coin_contract

        self.update_wallet()

        balance_start = self.wallet.get(coin_start)

        log.info("contract start! [%s] :: bal_start=%s" % (
            coin_start, balance_start
        ))

        self.contract(transactions[0], maximum_contract=maximum_contract)
        self.update_wallet()
        self.wait_for_finish_contract(transactions[0]) # 해당 거래가 종료되었는지 체크

        for tr in transactions[1:]: # type: Transaction
            self.contract(tr)
            self.update_wallet()
            self.wait_for_finish_contract(tr) # 해당 거래가 종료되었는지 체크

        balance_end = self.wallet.get(coin_start)

        log.info("contract finished! [%s] :: profit=%s bal_start=%s bal_end=%s" % (
            coin_start, balance_end - balance_start, balance_start, balance_end
        ))

        self.set_contracting(False)

        return balance_start, balance_end


    def __init__(self):
        self.api = UpbitAPIClient()
        self.wallet = Wallet()
        self._lock = Lock()