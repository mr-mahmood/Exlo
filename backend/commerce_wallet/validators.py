from core.errors import APIError, WalletError

MIN_TOPUP_AMOUNT = 1_000_000  # Rial
MAX_TOPUP_AMOUNT = 200_000_000  # Rial


def parse_topup_amount(amount):
    if amount is None or amount == "":
        raise APIError(WalletError.AMOUNT_REQUIRE)

    # bool is a subclass of int — reject it explicitly
    if isinstance(amount, bool):
        raise APIError(WalletError.AMOUNT_REQUIRE)

    # Only accept real ints (reject floats, strings, lists, dicts, etc.)
    if not isinstance(amount, int):
        raise APIError(WalletError.AMOUNT_REQUIRE)

    if amount < MIN_TOPUP_AMOUNT:
        raise APIError(WalletError.AMOUNT_TOO_LOW)
    if amount > MAX_TOPUP_AMOUNT:
        raise APIError(WalletError.AMOUNT_TOO_HIGH)

    return amount
