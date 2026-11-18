"""moomoo wire codes: MY must use KLSE numbers, SG must use SGX codes."""

from app.data.moomoo_fetcher import get_moomoo_code


def test_us_code_unchanged():
    assert get_moomoo_code("NVDA", "US") == "US.NVDA"
    assert get_moomoo_code("nvda") == "US.NVDA"


def test_my_short_name_maps_to_klse_code():
    assert get_moomoo_code("MAYBANK", "MY") == "MY.1155"
    assert get_moomoo_code("maybank", "my") == "MY.1155"


def test_my_accepts_full_universe_key():
    assert get_moomoo_code("MY.MAYBANK", "MY") == "MY.1155"


def test_my_numeric_code_passes_through():
    assert get_moomoo_code("1155", "MY") == "MY.1155"


def test_my_unknown_ticker_passes_through():
    assert get_moomoo_code("NEWCO", "MY") == "MY.NEWCO"


def test_sg_short_names_map_to_sgx_codes():
    assert get_moomoo_code("DBS", "SG") == "SG.D05"
    assert get_moomoo_code("uob", "sg") == "SG.U11"
    assert get_moomoo_code("OCBC", "SG") == "SG.O39"
    assert get_moomoo_code("SINGTEL", "SG") == "SG.Z74"


def test_sg_code_passes_through():
    assert get_moomoo_code("D05", "SG") == "SG.D05"
