"""解析 Step 3 記錄的作答格位址（A1 表示法含分頁名）。

格式：'<分頁名>'!<欄字母><列號>，分頁名內的單引號以兩個單引號跳脫（見 parser._address）。
回傳 0 起算的 (row, col)，供回填寫入定位。
"""
import re

_PATTERN = re.compile(r"^'((?:[^']|'')*)'!([A-Z]+)(\d+)$")


def parse_a1(cell: str) -> tuple[int, int]:
    m = _PATTERN.match(cell or "")
    if not m:
        raise ValueError(f"invalid cell address: {cell!r}")
    letters, number = m.group(2), int(m.group(3))
    if number < 1:
        raise ValueError(f"invalid cell address: {cell!r}")
    col = 0
    for ch in letters:
        col = col * 26 + (ord(ch) - 64)
    return number - 1, col - 1
