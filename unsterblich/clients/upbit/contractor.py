from threading import Thread

from .apis import UpbitAPIClient
from .transaction import Wallet, Transaction, TRX_BUY, TRX_SELL

from ...misc import create_logger

log = create_logger(name='UpbitContractor')


class FastContraction:

    api = None # type: UpbitAPIClient
    wallet = None # type: Wallet

    """
    #1. 데이터 순서대로 거래하게 된다.
    #1. 데이터 순서대로 거래하게 된다.
    
    """
    def contract(self, transaction: Transaction):
        pass

    def start_contract(self, transactions: list):
        for tr in transactions:
            assert isinstance(tr, Transaction)

        for tr in transactions:
            self.contract(tr)

    def __init__(self):
        self.api = UpbitAPIClient()