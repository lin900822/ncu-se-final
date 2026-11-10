import asyncio
import logging

import httpx
import pytest

from app.config import SHEETS_SCOPE, SheetsConfig
from app.models import AppError
from app.sheets.client import SheetsClient

CONFIG = SheetsConfig(key_file="/dev/null", client_email="bot@example.iam.gserviceaccount.com")
SECRET = "-----BEGIN PRIVATE KEY-----SECRET-----"

PAYLOAD = {
    "sheets": [
        {
            "properties": {"sheetId": 0, "title": "第一頁"},
            "merges": [
                {"startRowIndex": 1, "endRowIndex": 3, "startColumnIndex": 1, "endColumnIndex": 2}
            ],
            "data": [
                {
                    "startRow": 0,
                    "startColumn": 0,
                    "rowData": [
                        {},
                        {"values": [{}, {"formattedValue": "題號"}]},
                    ],
                }
            ],
        },
        {
            "properties": {"sheetId": 77, "title": "學習單"},
            "data": [{"rowData": [{"values": [{"formattedValue": "x"}]}]}],
        },
    ]
}


def make_client(handler, config=CONFIG):
    http = httpx.AsyncClient(transport=httpx.MockTransport(handler))
    return SheetsClient(config, http=http, token_provider=lambda: "tok")


def run(coro):
    return asyncio.run(coro)


def test_ok_first_sheet_and_gid():
    seen = {}

    def handler(req: httpx.Request):
        seen["host"] = req.url.host
        seen["auth"] = req.headers["Authorization"]
        return httpx.Response(200, json=PAYLOAD)

    grid, title, sid = run(make_client(handler).fetch("abc", None))
    assert (title, sid) == ("第一頁", 0)
    assert grid.rows[1][1] == "題號"
    assert grid.merges == [(1, 3, 1, 2)]
    assert seen["host"] == "sheets.googleapis.com" and seen["auth"] == "Bearer tok"
    grid2, title2, sid2 = run(make_client(handler).fetch("abc", 77))
    assert (title2, sid2) == ("學習單", 77) and grid2.rows[0][0] == "x"
    with pytest.raises(AppError) as e:
        run(make_client(handler).fetch("abc", 999))
    assert e.value.code == "SHEET_NOT_FOUND"


def test_scope_is_readonly():
    assert SHEETS_SCOPE.endswith("spreadsheets.readonly")


@pytest.mark.parametrize(
    "status,code",
    [(403, "SHEET_FORBIDDEN"), (404, "SHEET_NOT_FOUND"), (500, "SHEET_TIMEOUT")],
)
def test_status_mapping(status, code):
    with pytest.raises(AppError) as e:
        run(make_client(lambda r: httpx.Response(status, text=SECRET)).fetch("abc", None))
    assert e.value.code == code
    if code == "SHEET_FORBIDDEN":
        assert e.value.details == {"serviceAccountEmail": CONFIG.client_email}
        assert CONFIG.client_email in e.value.message
    assert SECRET not in e.value.message


def test_timeout_and_network_error():
    def boom(req):
        raise httpx.ConnectTimeout("t")

    with pytest.raises(AppError) as e:
        run(make_client(boom).fetch("abc", None))
    assert e.value.code == "SHEET_TIMEOUT"


def test_not_configured():
    with pytest.raises(AppError) as e:
        run(SheetsClient(None).fetch("abc", None))
    assert e.value.code == "SHEETS_NOT_CONFIGURED"


def test_token_failure_does_not_leak(caplog):
    def bad_token():
        raise RuntimeError(SECRET)

    http = httpx.AsyncClient(transport=httpx.MockTransport(lambda r: httpx.Response(200)))
    caplog.set_level(logging.DEBUG)
    with pytest.raises(AppError) as e:
        run(SheetsClient(CONFIG, http=http, token_provider=bad_token).fetch("abc", None))
    assert e.value.code == "SHEETS_NOT_CONFIGURED"
    assert SECRET not in e.value.message and SECRET not in caplog.text
    assert SECRET not in repr(CONFIG)
