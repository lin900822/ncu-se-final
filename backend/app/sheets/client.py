"""Google Sheets 用戶端：以服務帳號（機器人）身分讀取試算表；回填（Step 10）時才寫入。

- 只呼叫固定網域 sheets.googleapis.com，不使用使用者提供的主機名稱。
- 任何錯誤、日誌皆不得包含服務帳號金鑰內容。
"""
import asyncio
from collections.abc import Callable

import httpx

from ..config import SHEETS_SCOPE, SHEETS_WRITE_SCOPE, SheetsConfig
from ..models import AppError, err
from .parser import Grid

API = "https://sheets.googleapis.com/v4/spreadsheets/{id}"
FIELDS = (
    "sheets(properties(sheetId,title),merges,"
    "data(startRow,startColumn,rowData(values(formattedValue))))"
)
TIMEOUT_SECONDS = 10


_creds_cache: dict[tuple[str, str], object] = {}


def _ipv4_transport() -> httpx.AsyncHTTPTransport:
    """只走 IPv4：部分網路的 IPv6 到 Google 不通，Python 又沒有 Happy Eyeballs，會卡到逾時。"""
    return httpx.AsyncHTTPTransport(local_address="0.0.0.0")


def _new_http() -> httpx.AsyncClient:
    return httpx.AsyncClient(timeout=TIMEOUT_SECONDS, transport=_ipv4_transport())


def _ipv4_auth_request():
    """google-auth 用 requests 取 token：綁定 IPv4 來源位址並加上逾時。"""
    import requests
    from google.auth.transport.requests import Request
    from requests.adapters import HTTPAdapter

    class IPv4Adapter(HTTPAdapter):
        def init_poolmanager(self, *args, **kwargs):
            kwargs["source_address"] = ("0.0.0.0", 0)
            super().init_poolmanager(*args, **kwargs)

    session = requests.Session()
    session.mount("https://", IPv4Adapter())

    class TimedRequest(Request):
        def __call__(self, url, method="GET", body=None, headers=None, timeout=TIMEOUT_SECONDS, **kw):
            return super().__call__(url, method, body, headers, timeout=timeout, **kw)

    return TimedRequest(session=session)


def _default_token_provider(config: SheetsConfig, scope: str = SHEETS_SCOPE) -> Callable[[], str]:
    def provider() -> str:
        from google.oauth2 import service_account

        key = (config.key_file, scope)
        creds = _creds_cache.get(key)
        if creds is None:
            creds = service_account.Credentials.from_service_account_file(
                config.key_file, scopes=[scope]
            )
            _creds_cache[key] = creds
        if not creds.valid:  # 快取憑證：token 有效期內不重複向 Google 換
            creds.refresh(_ipv4_auth_request())
        return creds.token

    return provider


class SheetsClient:
    def __init__(
        self,
        config: SheetsConfig | None,
        http: httpx.AsyncClient | None = None,
        token_provider: Callable[[], str] | None = None,
    ) -> None:
        self.config = config
        self._http = http
        self._token_provider = token_provider

    async def _token(self, scope: str = SHEETS_SCOPE) -> str:
        assert self.config is not None
        provider = self._token_provider or _default_token_provider(self.config, scope)
        try:
            return await asyncio.to_thread(provider)
        except Exception as e:  # 不將例外內容外送，避免洩漏金鑰資訊
            from google.auth import exceptions as gexc

            if isinstance(e, gexc.TransportError):
                raise err("SHEET_TIMEOUT") from None
            raise err("SHEETS_NOT_CONFIGURED") from None

    async def fetch(self, spreadsheet_id: str, gid: int | None) -> tuple[Grid, str, int]:
        if self.config is None:
            raise err("SHEETS_NOT_CONFIGURED")
        token = await self._token()
        http = self._http or _new_http()
        try:
            resp = await http.get(
                API.format(id=spreadsheet_id),
                params={"includeGridData": "true", "fields": FIELDS},
                headers={"Authorization": f"Bearer {token}"},
                timeout=TIMEOUT_SECONDS,
            )
        except httpx.HTTPError:
            raise err("SHEET_TIMEOUT") from None
        finally:
            if self._http is None:
                await http.aclose()
        return self._to_grid(resp, gid)

    async def write_cells(
        self,
        spreadsheet_id: str,
        sheet_id: int,
        updates: list[tuple[int, int, str | None]],
    ) -> None:
        """回填寫入：**單一批次**更新（Google 對整批先驗證再套用，任一無效則整批不生效＝全有或全無）。

        每個 (row, col, text) 一個 updateCells：以 stringValue 寫入（文字原樣，不會被當成公式、
        不會被轉成數字或日期）；text 為 None 表示清空。fields 固定為 userEnteredValue（只寫值，
        不動格式、資料驗證、合併設定）。只使用讀寫範圍於此方法。
        """
        if self.config is None:
            raise err("SHEETS_NOT_CONFIGURED")
        requests = []
        for row, col, text in updates:
            requests.append(
                {
                    "updateCells": {
                        "range": {
                            "sheetId": sheet_id,
                            "startRowIndex": row,
                            "endRowIndex": row + 1,
                            "startColumnIndex": col,
                            "endColumnIndex": col + 1,
                        },
                        "rows": [
                            {"values": [{} if text is None else {"userEnteredValue": {"stringValue": text}}]}
                        ],
                        "fields": "userEnteredValue",
                    }
                }
            )
        token = await self._token(SHEETS_WRITE_SCOPE)
        http = self._http or _new_http()
        try:
            resp = await http.post(
                API.format(id=spreadsheet_id) + ":batchUpdate",
                json={"requests": requests},
                headers={"Authorization": f"Bearer {token}"},
                timeout=TIMEOUT_SECONDS,
            )
        except httpx.HTTPError:
            raise err("SHEET_TIMEOUT") from None
        finally:
            if self._http is None:
                await http.aclose()
        self._check_write(resp)

    def _check_write(self, resp: httpx.Response) -> None:
        if resp.status_code == 200:
            return
        email = self.config.client_email if self.config else ""

        def not_editable() -> AppError:
            return AppError(
                "SHEET_NOT_EDITABLE",
                f"無法寫入，請將試算表共用給 {email} 並設為編輯者",
                403,
                {"serviceAccountEmail": email},
            )

        if resp.status_code in (401, 403):
            raise not_editable()
        if resp.status_code == 404:
            raise err("SHEET_NOT_FOUND")
        if resp.status_code == 429:
            raise err("SHEET_QUOTA")
        if resp.status_code == 400:
            if "protected" in resp.text.lower():
                raise not_editable()  # 受保護範圍：機器人無權寫入
            raise err("SHEET_WRITE_FAILED")
        raise err("SHEET_TIMEOUT")

    def _to_grid(self, resp: httpx.Response, gid: int | None) -> tuple[Grid, str, int]:
        if resp.status_code in (401, 403):
            email = self.config.client_email if self.config else ""
            raise AppError(
                "SHEET_FORBIDDEN",
                f"無法讀取，請將試算表共用給 {email}",
                403,
                {"serviceAccountEmail": email},
            )
        if resp.status_code == 404:
            raise err("SHEET_NOT_FOUND")
        if resp.status_code == 400:
            raise err("SHEET_FORMAT_UNRECOGNIZED")
        if resp.status_code != 200:
            raise err("SHEET_TIMEOUT")
        try:
            sheets = resp.json().get("sheets") or []
        except ValueError:
            raise err("SHEET_TIMEOUT") from None
        if not sheets:
            raise err("SHEET_NOT_FOUND")
        sheet = None
        if gid is None:
            sheet = sheets[0]
        else:
            sheet = next(
                (s for s in sheets if s.get("properties", {}).get("sheetId") == gid), None
            )
            if sheet is None:
                raise err("SHEET_NOT_FOUND")
        props = sheet.get("properties", {})
        rows: list[list[str]] = []
        for block in sheet.get("data") or []:
            r0 = block.get("startRow", 0)
            c0 = block.get("startColumn", 0)
            for i, row in enumerate(block.get("rowData") or []):
                r = r0 + i
                while len(rows) <= r:
                    rows.append([])
                for j, cell in enumerate((row or {}).get("values") or []):
                    c = c0 + j
                    line = rows[r]
                    while len(line) <= c:
                        line.append("")
                    line[c] = (cell or {}).get("formattedValue", "") or ""
        merges = [
            (
                m.get("startRowIndex", 0),
                m.get("endRowIndex", 0),
                m.get("startColumnIndex", 0),
                m.get("endColumnIndex", 0),
            )
            for m in sheet.get("merges") or []
        ]
        return Grid(rows=rows, merges=merges), props.get("title", ""), props.get("sheetId", 0)
