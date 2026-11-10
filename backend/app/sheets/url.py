"""解析 Google Sheet 連結。只接受 docs.google.com/spreadsheets/d/<id>，
後端只會對固定的 Google 網域送出請求，不使用使用者提供的主機名稱。"""
import re

from ..models import err

_URL = re.compile(r"^https://docs\.google\.com/spreadsheets/d/([A-Za-z0-9_-]+)(?:[/?#].*)?$")
_GID = re.compile(r"[#?&]gid=(\d+)")


def parse_sheet_url(url: str) -> tuple[str, int | None]:
    url = (url or "").strip()
    m = _URL.match(url)
    if not m:
        raise err("SHEET_URL_INVALID")
    g = _GID.search(url)
    return m.group(1), int(g.group(1)) if g else None
