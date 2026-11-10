"""設定：由 backend/.env 載入環境變數。

服務帳號金鑰檔只在伺服器端讀取；本模組不保存、不記錄、不回傳 private_key。
"""
import json
import os
from dataclasses import dataclass
from pathlib import Path

from dotenv import load_dotenv

# 本步驟只讀取試算表（最小權限）；回填步驟才改為 .../auth/spreadsheets
SHEETS_SCOPE = "https://www.googleapis.com/auth/spreadsheets.readonly"

load_dotenv(Path(__file__).resolve().parents[1] / ".env")


@dataclass(frozen=True)
class SheetsConfig:
    key_file: str
    client_email: str  # 非機密；「未共用」錯誤提示時顯示給老師


def get_sheets_config() -> SheetsConfig | None:
    """未設定、檔案不存在或欄位缺漏時回傳 None（呼叫端以 SHEETS_NOT_CONFIGURED 處理）。"""
    path = os.environ.get("GOOGLE_SERVICE_ACCOUNT_FILE", "").strip()
    if not path:
        return None
    try:
        with open(path, encoding="utf-8") as f:
            data = json.load(f)
        email = data["client_email"]
        if not data.get("private_key") or not email:
            return None
    except (OSError, ValueError, KeyError, TypeError):
        return None
    return SheetsConfig(key_file=path, client_email=str(email))
