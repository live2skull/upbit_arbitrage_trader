import math
from decimal import Decimal, getcontext, ROUND_DOWN, ROUND_UP
from sympy import Symbol, solve

from ...misc import create_logger
from ...config import UPBIT_DECIMAL_PRECISION, CALC_DECIMAL_PRECISION

logger = create_logger("calculator")

getcontext().prec = CALC_DECIMAL_PRECISION

CONVERT_FORMAT = "%." + str(UPBIT_DECIMAL_PRECISION) + 'f'

# https://src-bin.com/ko/q/6f3bc
# 정확한 이유는 모르지만 이렇게 했을 때 필요한 precision까지 끊어낼 수 있다.
# %.nf 형식으로 작성할 경우 원하는 precision까지만 정확하게 부동 소수점을 제외하고
# 출력할 수 있다.
def dec2float(value: Decimal):
    return float(CONVERT_FORMAT % value)

## -> 호가에 반영된다는 의미임. : 테스트 완료. balance에는 정수 단위부터(1원) 사용 가능하다.
## -> 계산할때는 신경쓸 필요 없다.

def conv2dec(value):
    return value if isinstance(value, Decimal) else Decimal(value)


def solve_equation(equation):
    return Decimal(str(solve(equation)[0]))


def truncate(value: Decimal):
    return math.trunc(value)

## ask_prices, ask_amounts 데이터들도 전부 dec으로 가정..??
## -> set 함수에 진입하기 전 decimal 타입으로 변경하여 줍니다.
## fee = percentage!


## https://eev.ee/blog/2011/04/24/gotcha-python-scoping-closures/
# mutable 한 데이터를 scoping 할 수 있다?
class CalcSession:
    balance = None # type: Decimal
    amount = None # type: Decimal
    fee = None # type: Decimal
    is_finished = None # type: int

    def __init__(self, balance, amount, fee):
        self.balance = conv2dec(balance)
        self.amount = conv2dec(amount)
        self.fee = Decimal(fee * 0.01 + 1)


def vt_buy_all(balance, fee, ask_prices: list, ask_amounts: list, isKRW=True):
    sess = CalcSession(balance, 0, fee)
    is_finished = 0

    def set_buy_amount(ask_price: Decimal, ask_amount: Decimal):

        sym_amount = Symbol('sym_amount')
        equation = (sym_amount * ask_price) * sess.fee - sess.balance
        _amount = solve_equation(equation)

        if _amount > ask_amount: # 현재의 거래가 완벽히 끝나지 않고 부분채결이 됨.
            tbalance = Decimal((ask_amount * ask_price) * sess.fee) # 현재 호가에서 드는 가격 (최대)
            sess.balance -= truncate(tbalance) if isKRW else tbalance
            sess.amount += ask_amount # 현재 호가에서 구매 가능한 갯수 - 현재 호가 전체!
            return False

        else:
            sess.balance -= truncate(sess.balance) if isKRW else sess.balance
            sess.amount += _amount
            return True

    # TODO: empty orderbook checker
    if len(ask_prices) is 0:
        logger.critical("vt_buy_all: 호가 정보가 존재하지 않음.")
        raise ValueError("호가 정보가 없음")

    for i in range(0, len(ask_prices)):
        _ask_price = Decimal(ask_prices[i])
        _ask_amount = Decimal(ask_amounts[i])

        if set_buy_amount(ask_price=_ask_price, ask_amount=_ask_amount):
            is_finished += 1
            break

    if not bool(is_finished):
        logger.critical("vt_buy_all: 최대 호가로 거래를 종결할 수 없음.")
        raise ValueError("최대 호가로 거래를 종결할 수 없음")

    if isKRW: sess.balance = truncate(sess.balance)
    return dec2float(sess.balance), dec2float(sess.amount)



def vt_sell_all(amount, fee, bid_prices: list, bid_amounts: list, isKRW=True):

    sess = CalcSession(0, amount, fee)
    is_finished = 0

    def set_sell_balance(bid_price: Decimal, bid_amount: Decimal):

        is_continue = 0
        _amount = Decimal(0)
        if sess.amount > bid_amount:
            is_continue += 1
            _amount += bid_amount
        else:
            _amount += sess.amount

        contract_balance = _amount * bid_price
        fee_balance = contract_balance * (sess.fee - 1)
        _balance = contract_balance - fee_balance # 실제 입금되는 금액은 다음과 같다.

        sess.balance += truncate(_balance) if isKRW else _balance
        sess.amount -= _amount
        return not bool(is_continue)

    if len(bid_prices) is 0:
        logger.critical("vt_sell_all: 호가 정보가 존재하지 않음.")
        raise ValueError("호가 정보가 존재하지 않음.")

    for i in range(0, len(bid_prices)):
        _bid_price = Decimal(bid_prices[i])
        _bid_amount = Decimal(bid_amounts[i])

        if set_sell_balance(bid_price=_bid_price, bid_amount=_bid_amount):
            is_finished += 1
            break

    if not bool(is_finished):
        logger.critical("vt_sell_all: 최대 호가로 거래를 종결할 수 없음.")
        raise ValueError("최대 호가로 거래를 종결할 수 없음")

    if isKRW: sess.balance = truncate(sess.balance)
    return dec2float(sess.balance), dec2float(sess.amount)




