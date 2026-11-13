"""Step 10 US2：寫入客戶端——請求內容（單一批次、字串值、只寫值）、權限範圍與錯誤對應。"""
import json
import logging

import httpx
import pytest

from app.config import SHEETS_SCOPE, SHEETS_WRITE_SCOPE
from app.models import AppError
from app.sheets.client import SheetsClient

from .test_sheet_client import CONFIG, SECRET, make_client, run


def _capture():
    seen = []

    def handler(req: httpx.Request):
        seen.append((str(req.url), req.headers["Authorization"], json.loads(req.content)))
        return httpx.Response(200, json={})

    return seen, handler


def test_single_batch_request_with_string_values_and_clear():
    seen, handler = _capture()
    run(make_client(handler).write_cells("abc", 0, [(5, 7, "CPU"), (6, 7, None)]))
    assert len(seen) == 1  # 單一請求
    url, auth, body = seen[0]
    assert url == "https://sheets.googleapis.com/v4/spreadsheets/abc:batchUpdate"
    assert auth == "Bearer tok"
    first, second = body["requests"]
    assert first["updateCells"]["range"] == {
        "sheetId": 0, "startRowIndex": 5, "endRowIndex": 6, "startColumnIndex": 7, "endColumnIndex": 8,
    }
    assert first["updateCells"]["rows"] == [{"values": [{"userEnteredValue": {"stringValue": "CPU"}}]}]
    assert first["updateCells"]["fields"] == "userEnteredValue"
    assert second["updateCells"]["rows"] == [{"values": [{}]}]  # 清空
    assert second["updateCells"]["fields"] == "userEnteredValue"


@pytest.mark.parametrize(
    "text",
    ["=1+1", "+1", "-5", "@A1", "007", "3/4", '含逗號, 與 "引號"', "第一行\n第二行", "中文", "字" * 500],
)
def test_text_is_sent_verbatim_as_string_value(text):
    seen, handler = _capture()
    run(make_client(handler).write_cells("abc", 3, [(0, 0, text)]))
    raw = json.dumps(seen[0][2], ensure_ascii=False)
    value = seen[0][2]["requests"][0]["updateCells"]["rows"][0]["values"][0]["userEnteredValue"]
    assert value == {"stringValue": text}
    assert "formulaValue" not in raw and "numberValue" not in raw and "boolValue" not in raw


def test_only_target_cells_and_only_values_are_touched():
    seen, handler = _capture()
    run(make_client(handler).write_cells("abc", 7, [(1, 1, "a"), (2, 2, "b"), (3, 3, None)]))
    reqs = seen[0][2]["requests"]
    assert len(reqs) == 3  # 只有目標格
    for rq in reqs:
        assert set(rq) == {"updateCells"}
        assert rq["updateCells"]["fields"] == "userEnteredValue"  # 不碰格式、資料驗證、合併設定
        assert "userEnteredFormat" not in json.dumps(rq)
        assert rq["updateCells"]["range"]["sheetId"] == 7


def test_write_uses_write_scope_and_read_keeps_readonly_scope(monkeypatch):
    scopes = []

    class FakeCreds:
        valid = True
        token = "tok"

    def fake_from_file(path, scopes=None):
        scopes_list.append(list(scopes))
        return FakeCreds()

    from google.oauth2 import service_account

    scopes_list = scopes
    monkeypatch.setattr(service_account.Credentials, "from_service_account_file", staticmethod(fake_from_file))
    http = httpx.AsyncClient(transport=httpx.MockTransport(lambda r: httpx.Response(200, json={"sheets": [{"properties": {"sheetId": 0, "title": "t"}}]})))
    client = SheetsClient(CONFIG, http=http)
    run(client.write_cells("abc", 0, [(0, 0, "x")]))
    run(client.fetch("abc", None))
    assert scopes == [[SHEETS_WRITE_SCOPE], [SHEETS_SCOPE]]
    assert SHEETS_SCOPE.endswith("spreadsheets.readonly") and SHEETS_WRITE_SCOPE.endswith("/auth/spreadsheets")


@pytest.mark.parametrize(
    "status, text, code",
    [
        (403, SECRET, "SHEET_NOT_EDITABLE"),
        (401, SECRET, "SHEET_NOT_EDITABLE"),
        (404, SECRET, "SHEET_NOT_FOUND"),
        (429, SECRET, "SHEET_QUOTA"),
        (400, "This range is Protected", "SHEET_NOT_EDITABLE"),
        (400, "Invalid requests[0].updateCells", "SHEET_WRITE_FAILED"),
        (503, SECRET, "SHEET_TIMEOUT"),
    ],
)
def test_error_mapping(status, text, code, caplog):
    caplog.set_level(logging.DEBUG)
    with pytest.raises(AppError) as e:
        run(make_client(lambda r: httpx.Response(status, text=text)).write_cells("abc", 0, [(0, 0, "x")]))
    assert e.value.code == code
    if code == "SHEET_NOT_EDITABLE":
        assert e.value.http_status == 403
        assert e.value.details == {"serviceAccountEmail": CONFIG.client_email}
        assert CONFIG.client_email in e.value.message and "編輯者" in e.value.message
    assert SECRET not in e.value.message and SECRET not in caplog.text


def test_timeout_and_not_configured():
    def boom(req):
        raise httpx.ConnectTimeout("t")

    with pytest.raises(AppError) as e:
        run(make_client(boom).write_cells("abc", 0, [(0, 0, "x")]))
    assert e.value.code == "SHEET_TIMEOUT"
    with pytest.raises(AppError) as e2:
        run(SheetsClient(None).write_cells("abc", 0, [(0, 0, "x")]))
    assert e2.value.code == "SHEETS_NOT_CONFIGURED"
