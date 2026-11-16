"""Step 10：作答格位址（Step 3 的 A1 記錄）解析為 0 起算的 (row, col)。"""
import pytest

from app.sheets.a1 import parse_a1
from app.sheets.parser import _address


@pytest.mark.parametrize(
    "cell, expected",
    [
        ("'學習單'!H6", (5, 7)),
        ("'Sheet1'!A1", (0, 0)),
        ("'a''b'!AA10", (9, 26)),
        ("'x'!Z1", (0, 25)),
        ("'x'!AZ3", (2, 51)),
    ],
)
def test_parse_a1(cell, expected):
    assert parse_a1(cell) == expected


@pytest.mark.parametrize("bad", ["H6", "'x'!6", "", "'x'!A0", "'x'!a1"])
def test_invalid_address_raises(bad):
    with pytest.raises(ValueError):
        parse_a1(bad)


def test_roundtrip_with_parser_address():
    for title in ("學習單", "it's", "Sheet 1"):
        for r, c in ((0, 0), (5, 7), (49, 51), (9, 26)):
            assert parse_a1(_address(title, r, c)) == (r, c)
