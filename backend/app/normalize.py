"""房間代碼與組名的正規化與驗證。"""
import unicodedata

from .models import err

MAX_NAME_LENGTH = 20


def normalize_room_code(s: str) -> str:
    return "".join(str(s).split()).upper()


def clean_group_name(s: str) -> str:
    return str(s).strip()


def normalize_group_name(s: str) -> str:
    """NFKC → 移除所有空白 → casefold；房間內組名唯一鍵。"""
    return "".join(unicodedata.normalize("NFKC", str(s)).split()).casefold()


def validate_group_name(s: str) -> str:
    """回傳去除前後空白的顯示名稱，或丟出 NAME_REQUIRED / NAME_TOO_LONG。"""
    name = clean_group_name(s)
    if not name:
        raise err("NAME_REQUIRED")
    if len(name) > MAX_NAME_LENGTH:
        raise err("NAME_TOO_LONG")
    return name
