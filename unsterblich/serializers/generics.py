from rest_framework.serializers import Serializer
from rest_framework.serializers import CharField, FloatField, IntegerField, BooleanField


# default allow_null=False
# keyword "default" -> required=False 에서 디폴트 설정되어있지 않다면 dict key 접근시 접근불가함!


class ReqContractTransactions(Serializer):
    pass


class ReqMarkets(Serializer):
    update = BooleanField(required=False, default=False)


class ReqTopologySra(Serializer):
    base_coin = CharField(required=True) # TODO: Unique Field (check model available)
    balance = FloatField(required=True)
    cycle = IntegerField(required=False, default=1)
    # update = BooleanField(required=True)


