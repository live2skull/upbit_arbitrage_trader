from datetime import datetime

from django.db.models import Model, CASCADE

from django.db.models import ForeignKey
from django.db.models import OneToOneField
from django.db.models import \
    CharField, SmallIntegerField, UUIDField, IntegerField, EmailField, AutoField, BigAutoField, TextField, DateTimeField, DecimalField

from .clients.upbit.transaction import Transaction


class IdModelMixin(Model):
    id = BigAutoField(primary_key=True, auto_created=True, editable=False)

    class Meta:
        abstract = True


class ProfitResult(IdModelMixin, Model):
    balance = DecimalField(max_digits=20, decimal_places=8)
    profit = DecimalField(max_digits=20, decimal_places=8)

    created_at = DateTimeField(auto_now_add=True)

    @classmethod
    def create(cls, balance: float, profit: float, transactions: list):
        profit_result = cls()
        profit_result.balance = balance
        profit_result.profit = profit
        profit_result.save()

        for transaction in transactions: # type: Transaction
            ProfitResultTransaction.create(
                transaction=transaction, profit_result=profit_result
            )

        return profit_result


class ProfitResultTransaction(IdModelMixin, Model):
    profit_result = ForeignKey(ProfitResult, null=True,
        related_name='transactions', on_delete=CASCADE
    )

    market = CharField(null=True, max_length=16)
    transaction_type = SmallIntegerField(null=True, choices=[0, 1]) # BUY / SELL

    @classmethod
    def create(cls, transaction: Transaction, profit_result: ProfitResult):
        result_transaction = cls()
        result_transaction.market = transaction.market
        result_transaction.transaction_type = transaction.transaction_type
        result_transaction.profit_result = profit_result
        result_transaction.save()

        return result_transaction


