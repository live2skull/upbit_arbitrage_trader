from threading import Thread
import math

from .apis import UpbitAPIClient
from .transaction import Wallet, Transaction, TRX_BUY, TRX_SELL
from .calculator import get_market_buy_price

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


    ## TODO: 매도호가 간 간격이 넓어 시장가 주문 시 손실이 발생할 수 있습니다. 잠시 후 다시 이용하시거나, 지정가 주문을 이용해 주세요.
    # buy_price / sell_volume 동일하나, 시장가 거래가 지원되지 않을 경우 필요함.

    def get_krw_buy_option(self, value):
        # KRW마켓 -> 시장가만 사용할 것임.
        # 단, 원화로 구매할 경우에는 해당 원화는 소숫점 지원이 되지 않는다.
        return math.trunc(value)

    def get_krw_sell_option(self, value):
        return value

    def get_buy_price(self, transaction: Transaction):
        _price = get_market_buy_price(
            self.wallet.get(transaction.coin_contract), transaction.fee
        )

        ## 무조건 넣으면 되는것이아니라 여기서 수수료를 제외하고 주문하여야한다.
        price = self.get_krw_buy_option(_price) if transaction.is_krw else _price
        return price

    def get_sell_volume(self, transaction: Transaction):
        _price = self.wallet.get(transaction.coin_contract)
        
        ## 판매할 때는 해당 대금이 
        price = self.get_krw_sell_option(_price) if transaction.is_krw else _price
        return price

    def contract(self, transaction: Transaction, volume=None, price=None):

        # 매수 / 매도에 따라서 필요한 금액을 선정해야 합니다.
        self.update_wallet()

        market = transaction.market
        side = 'bid' if transaction.transaction_type is TRX_BUY else 'ask'
        ord_type = 'price' if transaction.transaction_type is TRX_BUY else 'market'

        # 시장가 매도 시 필수
        volume = None \
            if transaction.transaction_type is TRX_BUY else \
            volume if volume else self.get_sell_volume(transaction)
        
        # 시장가 매수 시 필수
        price = None \
            if transaction.transaction_type is TRX_SELL else \
            price if price else self.get_buy_price(transaction)

        log.info("start contract: %s (%s / %s) vol=%s price=%s" % (
            market, side, ord_type, volume, price
        ))

        ## TODO: error handling!
        return self.api.contract(market=market, side=side,
                          ord_type=ord_type, volume=volume, price=price)



    def start_contract(self, transactions: list):
        for tr in transactions:
            assert isinstance(tr, Transaction)

        for tr in transactions:
            self.contract(tr)

    def __init__(self):
        self.api = UpbitAPIClient()
        self.wallet = Wallet()