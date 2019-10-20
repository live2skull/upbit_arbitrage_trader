from threading import Thread
import math

from .apis import UpbitAPIClient
from .transaction import Wallet, Transaction, TRX_BUY, TRX_SELL
from .orderbook import ASK_PRICES, ASK_AMOUNTS, BID_PRICES, BID_AMOUNTS
from .calculator import get_market_buy_price, get_limit_buy_volume_price, get_limit_sell_volume_price

from ...misc import create_logger

log = create_logger(name='UpbitContractor', level=0)



class FastContraction:

    api = None # type: UpbitAPIClient
    wallet = None # type: Wallet

    """
    #1. 데이터 순서대로 거래하게 된다.
    
    """

    def update_wallet(self):
        #     {
        #         "currency": "KRW",
        #         "balance": "0.31662263",
        #         "locked": "151752.994578",
        #         "avg_buy_price": "0",
        #         "avg_buy_price_modified": true,
        #         "unit_currency": "KRW"
        #     },

        status = self.api.get_user_balance()

        for stat in status:
            coin = stat['currency']
            balance = float(stat['balance'])
            locked = float(stat['locked'])

            if not locked == 0:
                log.warning("%s currently contracting!" % coin)
                continue

            self.wallet.set(coin, balance)


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


    def contract(self, transaction: Transaction, volume=None, price=None, maximum_contract=None, allow_market_order=True):

        # 매수 / 매도에 따라서 필요한 금액을 선정해야 합니다.
        self.update_wallet()

        market = transaction.market
        side = 'bid' if transaction.transaction_type is TRX_BUY else 'ask'
        ord_type = self.get_ord_type(transaction) if allow_market_order else 'limit'
        volume = float(0.0)
        price = float(0.0)

        # 시장가 주문 사용
        if transaction.is_krw and allow_market_order:

            # 시장가 매도 시 필수
            _volume = float(0.0) \
                if transaction.transaction_type is TRX_BUY else \
                volume if volume else self.get_sell_market_volume(transaction)

            # 시장가 매수 시 필수
            _price = float(0.0) \
                if transaction.transaction_type is TRX_SELL else \
                price if price else self.get_buy_market_price(transaction)

            volume += _volume
            price += _price

        else:

            units = transaction.orderbook.units

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


    def start_contract(self, transactions: list, maximum_contract: float):
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

        for tr in transactions[1:]:
            self.contract(tr)

        balance_end = self.wallet.get(coin_start)

        log.info("contract finished! [%s] :: profit=%s bal_start=%s bal_end=%s" % (
            coin_start, balance_end - balance_start, balance_start, balance_end
        ))

        return balance_start, balance_end


    def __init__(self):
        self.api = UpbitAPIClient()
        self.wallet = Wallet()