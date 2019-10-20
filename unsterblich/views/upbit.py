from django.urls import path


from rest_framework.viewsets import ViewSet
from rest_framework.request import Request
from rest_framework.response import Response

from ..globals import GET, POST

from ..serializers.generics import ReqContractTransactions, ReqMarkets, ReqTopologySra, ReqSingleContract

from ..clients.upbit.apis import UpbitAPIClient, UpbitLocalClient

from ..clients.upbit.transaction import Wallet, Transaction, TRX_BUY, TRX_SELL
from ..clients.upbit.topology import Topology
from ..clients.upbit.contractor import FastContraction


"""
#1. select available markets
#2. draw topology
#3. deserialize topology
#4. serialize topology (selective)
#5. multithreading virtual trade calcuation
#6. contract chained transactions!

"""

fastContractor = FastContraction()

class UpbitActionView(ViewSet):


    def contract_chained_transactions(self, req: Request):
        data = req.data

        # 1. maximum start context

        balance = float(data['balance']) # maximum balance
        objects = data['objects']

        if fastContractor.is_contracting:
            return Response({
                "result" : False, "reason" : "contractor already running."
            })
        fastContractor.set_contracting(True)

        transactions = []
        for obj in objects:
            transactions.append(Transaction.deserialize(obj))


        balance_start, balance_end = fastContractor.start_contract(
                transactions=transactions,
                maximum_contract=balance
        )

        # TODO: save / tracking contract results & etc
        # TODO: Response Serializer
        return Response({
            'result' : True,
            'balance_start' : balance_start, 'balance_end' :  balance_end,
            'profit' : balance_end - balance_start
        })

    def available_markets(self, req: Request):
        _sra = ReqMarkets(data=req.query_params)
        _sra.is_valid(raise_exception=True)
        _req = _sra.validated_data
        _update = _req['update']

        markets = UpbitAPIClient().get_all_markets() if _update else \
            UpbitLocalClient().all_markets

        if _update:
            UpbitLocalClient().all_markets = markets

        return Response(markets)


    def topologies(self, req: Request):
        _sra = ReqTopologySra(data=req.query_params)
        _sra.is_valid(raise_exception=True)
        _req = _sra.validated_data

        base_coin = _req['base_coin']
        balance = _req['balance']
        cycle = _req['cycle']

        _wallet = Wallet()
        _wallet.set(base_coin, balance)

        top = Topology.create_via_base(base_coin, wallet=_wallet, cycle=cycle)
        serialized = top.serialize()

        result = {
            'length' : len(serialized), 'topology_top' : base_coin, 'cycle' : cycle if cycle else 1,
            'objects' : serialized
        }

        # _test = Topology.deserialize(result)

        # ... serialize
        return Response(result)


    def test(self, req: Request):
        return Response(UpbitAPIClient().get_user_balance())

    def test_wallet(self, req: Request):
        FastContraction().update_wallet()
        return Response("OK")

    def test_contract(self, req: Request):

        _sra = ReqSingleContract(data=req.query_params)
        _sra.is_valid(raise_exception=True)
        _req = _sra.validated_data

        market = _req['market']
        transaction_type = _req['transaction_type']
        allow_market_order = _req['allow_market_order']
        volume = _req['volume']
        price = _req['price']

        return Response(FastContraction().contract(
            transaction=Transaction(
                market=market, transaction_type=transaction_type),
                allow_market_order=allow_market_order, vol=volume, pri=price
        ))

_sv = UpbitActionView

urlpatterns = [
    path('contract', _sv.as_view(
        actions={POST : 'contract_chained_transactions'})
    ),

    path('available_markets', _sv.as_view(
        actions={GET : 'available_markets'})
    ),

    path('topologies', _sv.as_view(
        actions={GET : 'topologies'})
    ),

    path('test', _sv.as_view(
        actions={GET : 'test'})
    ),

    path('test_wallet', _sv.as_view(
        actions={GET : 'test_wallet'})
    ),

    path('test_contract', _sv.as_view(
        actions={GET : 'test_contract'})
    ),
]