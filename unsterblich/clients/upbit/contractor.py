from threading import Thread

from .apis import UpbitAPIClient
from .transaction import Wallet, Transaction, TRX_BUY, TRX_SELL

from ...misc import create_logger

log = create_logger(name='UpbitContractor', level=0)



class FastContraction:

    api = None # type: UpbitAPIClient
    wallet = None # type: Wallet

    """
    #1. 데이터 순서대로 거래하게 된다.
    
    """

    def get_buy_price(self, transaction: Transaction):
        pass


    def get_sell_volume(self, transaction: Transaction):
        pass


    def contract(self, transaction: Transaction):

        # 매수 / 매도에 따라서 필요한 금액을 선정해야 합니다.

        market = transaction.market
        side = 'bid' if transaction.transaction_type is TRX_BUY else 'ask'
        ord_type = 'price' if transaction.transaction_type is TRX_BUY else 'market'

        # 시장가 매도 시 필수
        volume = self.get_sell_volume(transaction) \
            if transaction.transaction_type is TRX_BUY else 1
        
        # 시장가 매수 시 필수
        price = self.get_buy_price(transaction) \
            if transaction.transaction_type is TRX_SELL else 1

        ## TODO: error handling!
        self.api.contract(market=market, side=side,
                          ord_type=ord_type, volume=volume, price=price)



    def start_contract(self, transactions: list):
        for tr in transactions:
            assert isinstance(tr, Transaction)

        for tr in transactions:
            self.contract(tr)

    def __init__(self):
        self.api = UpbitAPIClient()