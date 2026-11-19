"""Price sanity floor: corrupt feed values (e.g. yfinance DIGI 0.0001) become 0.0."""

from app.core.stocks import MIN_VALID_PRICE, valid_price


def test_sub_cent_prices_are_rejected():
    assert valid_price(0.0001) == 0.0
    assert valid_price(0.0099) == 0.0


def test_floor_boundary_passes():
    assert valid_price(MIN_VALID_PRICE) == MIN_VALID_PRICE
    assert valid_price(9.25) == 9.25
    assert valid_price(152.21) == 152.21


def test_nan_and_inf_are_rejected():
    assert valid_price(float("nan")) == 0.0
    assert valid_price(float("inf")) == 0.0


def test_non_numeric_input_is_rejected():
    assert valid_price("abc") == 0.0
    assert valid_price(None) == 0.0


def test_zero_and_negative_are_rejected():
    assert valid_price(0) == 0.0
    assert valid_price(-1.5) == 0.0
