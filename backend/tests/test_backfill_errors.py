"""Step 10 US3：時機、權限、外部錯誤、失敗紀錄與靜態審核（原則 III、SC-004、SC-007）。"""
import json
import re
from pathlib import Path

import pytest

from app.models import err
from app.services import sheets as sheets_service
from app.store import store

from .conftest import auth, make_ranked_room, make_started_room, post_backfill
from .test_submission_privacy import flush

APP = Path(__file__).resolve().parents[1] / "app"
BOT = "bot@example.iam.gserviceaccount.com"


def _close(conns):
    for cm, _ws in conns:
        cm.__exit__(None, None, None)


def _code(r):
    return r.json()["error"]["code"]


# ---- 時機與前置條件 ----

def test_not_allowed_while_answering_or_waiting_and_for_stale_round(client, fake_sheet):
    code, token, conns = make_ranked_room(client, end=False)  # 搶答中
    try:
        for preview in (True, False):
            r = post_backfill(client, code, token, preview=preview)
            assert r.status_code == 400 and _code(r) == "BACKFILL_NOT_ALLOWED"
        assert store.rooms[code].backfills == [] and fake_sheet.writes == []
    finally:
        _close(conns)
    code2, token2 = make_started_room(client, start=False)  # 尚未開始
    r2 = post_backfill(client, code2, token2, round_no=0)
    assert r2.status_code == 400 and _code(r2) == "BACKFILL_NOT_ALLOWED"


def test_stale_round_is_not_allowed(client, fake_sheet):
    code, token, conns = make_ranked_room(client)
    try:
        assert client.post(f"/api/rooms/{code}/phase/start", headers=auth(token)).status_code == 200
        assert client.post(f"/api/rooms/{code}/phase/end", headers=auth(token)).status_code == 200  # 第二輪
        r = post_backfill(client, code, token, round_no=1)
        assert r.status_code == 400 and _code(r) == "BACKFILL_NOT_ALLOWED"
        assert fake_sheet.writes == [] and store.rooms[code].backfills == []
    finally:
        _close(conns)


def test_room_without_sheet_cannot_backfill(client, fake_sheet):
    created = client.post("/api/rooms").json()
    code, token = created["code"], created["teacherToken"]
    client.post(f"/api/rooms/{code}/phase/start", headers=auth(token))
    client.post(f"/api/rooms/{code}/phase/end", headers=auth(token))
    for preview in (True, False):
        r = post_backfill(client, code, token, preview=preview)
        assert r.status_code == 400 and _code(r) == "BACKFILL_NO_SHEET"
    assert store.rooms[code].backfills == []


def test_closed_room_within_retention_can_still_backfill(client, fake_sheet):
    code, token, conns = make_ranked_room(client)
    try:
        assert client.post(f"/api/rooms/{code}/close", headers=auth(token)).status_code == 200
        assert post_backfill(client, code, token, preview=True).status_code == 200
        assert post_backfill(client, code, token).status_code == 200
        assert len(fake_sheet.writes) == 1
    finally:
        _close(conns)


# ---- 權限 ----

def test_unauthorized_variants_rejected_without_leak(client, fake_sheet):
    code, token, conns = make_ranked_room(client)
    try:
        body = {"round": 1}
        for path in ("backfill", "backfill/preview"):
            url = f"/api/rooms/{code}/{path}"
            attempts = [
                client.post(url, json=body),
                client.post(url, json=body, headers={"Authorization": "Bearer wrong"}),
                client.post(url, json=body, headers={"Authorization": "Basic abc"}),
                client.post(url, json=body, headers={"Authorization": token}),  # 缺 Bearer
                client.post(url + f"?token={token}", json=body),  # 憑證放網址
            ]
            for r in attempts:
                assert r.status_code == 401 and _code(r) == "UNAUTHORIZED"
                assert "ans-1" not in r.text and "第 1 組" not in r.text
        assert fake_sheet.writes == [] and store.rooms[code].backfills == []
    finally:
        _close(conns)


def test_old_credential_rejected_after_recovery(client, fake_sheet):
    code, token, conns = make_ranked_room(client)
    try:
        new = client.post("/api/rooms/recover", json={"recoveryCode": store.rooms[code].recovery_code}).json()["teacherToken"]
        assert post_backfill(client, code, token).status_code == 401
        assert fake_sheet.writes == []
        assert post_backfill(client, code, new).status_code == 200
    finally:
        _close(conns)


def test_student_messages_are_ignored_and_never_contain_backfill_info(client, fake_sheet):
    code, token, conns = make_ranked_room(client)
    try:
        for _c, w in conns:
            flush(w)
        ws = conns[0][1]
        ws.send_json({"type": "backfill", "round": 1})
        ws.send_json({"type": "backfill_preview", "round": 1})
        assert fake_sheet.writes == [] and store.rooms[code].backfills == []
        assert post_backfill(client, code, token).status_code == 200
        text = json.dumps([m for _c, w in conns for m in flush(w)], ensure_ascii=False)
        for word in ("backfill", "backfills", "sheetUrl", "spreadsheets"):
            assert word not in text, word
    finally:
        _close(conns)


# ---- 外部錯誤對應（經端點）與失敗紀錄 ----

@pytest.mark.parametrize(
    "exc, status, code",
    [
        (lambda: err("SHEET_NOT_EDITABLE", {"serviceAccountEmail": BOT}), 403, "SHEET_NOT_EDITABLE"),
        (lambda: err("SHEET_QUOTA"), 429, "SHEET_QUOTA"),
        (lambda: err("SHEET_TIMEOUT"), 504, "SHEET_TIMEOUT"),
        (lambda: err("SHEET_NOT_FOUND"), 404, "SHEET_NOT_FOUND"),
        (lambda: err("SHEET_WRITE_FAILED"), 502, "SHEET_WRITE_FAILED"),
        (lambda: err("SHEETS_NOT_CONFIGURED"), 503, "SHEETS_NOT_CONFIGURED"),
    ],
)
def test_write_errors_are_reported_recorded_and_leave_sheet_untouched(client, fake_sheet, exc, status, code):
    code_, token, conns = make_ranked_room(client)
    try:
        before = fake_sheet.snapshot()
        fake_sheet.fail_next = exc()
        r = post_backfill(client, code_, token)
        assert r.status_code == status and _code(r) == code
        if code == "SHEET_NOT_EDITABLE":
            assert r.json()["error"]["details"]["serviceAccountEmail"] == BOT
        assert fake_sheet.snapshot() == before and fake_sheet.writes == []
        rec = store.rooms[code_].backfills
        assert len(rec) == 1 and rec[0].result == "Failed" and rec[0].reason == code
        assert rec[0].written == {} and rec[0].cleared == []
    finally:
        _close(conns)


@pytest.mark.parametrize("code", ["SHEET_FORBIDDEN", "SHEET_NOT_FOUND", "SHEET_TIMEOUT"])
def test_read_failures_at_confirm_are_recorded_but_preview_failures_are_not(client, fake_sheet, monkeypatch, code):
    code_, token, conns = make_ranked_room(client)
    try:
        async def broken(spreadsheet_id, gid):
            raise err(code)

        monkeypatch.setattr(sheets_service, "_fetch", broken)
        rp = post_backfill(client, code_, token, preview=True)
        assert _code(rp) == code and store.rooms[code_].backfills == []  # 預覽失敗不記錄
        rc = post_backfill(client, code_, token)
        assert _code(rc) == code
        recs = store.rooms[code_].backfills
        assert len(recs) == 1 and recs[0].result == "Failed" and recs[0].reason == code
        assert fake_sheet.writes == []
    finally:
        _close(conns)


def test_structure_change_at_confirm_is_a_recorded_failure(client, fake_sheet):
    code, token, conns = make_ranked_room(client)
    try:
        fake_sheet.insert_row(0)
        r = post_backfill(client, code, token)
        assert _code(r) == "SHEET_STRUCTURE_CHANGED"
        assert [x.reason for x in store.rooms[code].backfills] == ["SHEET_STRUCTURE_CHANGED"]
    finally:
        _close(conns)


def test_failures_are_broadcast_to_teachers(client, fake_sheet):
    code, token, conns = make_ranked_room(client)
    try:
        with client.websocket_connect(f"/ws/teacher?token={token}&code={code}") as t:
            t.receive_json()
            fake_sheet.fail_next = err("SHEET_NOT_EDITABLE", {"serviceAccountEmail": BOT})
            post_backfill(client, code, token)
            while True:
                m = t.receive_json()
                if m["type"] == "backfill_updated":
                    break
        assert m["backfills"][-1]["result"] == "Failed" and m["backfills"][-1]["reason"] == "SHEET_NOT_EDITABLE"
        assert "編輯者" in m["backfills"][-1]["message"]
    finally:
        _close(conns)


def test_precheck_failures_are_not_recorded_and_order_is_fixed(client, fake_sheet, monkeypatch):
    code, token, conns = make_ranked_room(client, end=False)
    try:
        async def broken(spreadsheet_id, gid):
            raise err("SHEET_TIMEOUT")

        monkeypatch.setattr(sheets_service, "_fetch", broken)
        # 階段不符優先於試算表錯誤；未授權優先於階段
        assert _code(post_backfill(client, code, token)) == "BACKFILL_NOT_ALLOWED"
        assert post_backfill(client, code, None).status_code == 401
        assert store.rooms[code].backfills == []
    finally:
        _close(conns)


# ---- 靜態審核 ----

def test_static_scan_backfill_is_teacher_only_and_write_scope_is_confined():
    pattern = re.compile(r"^\s*from\s+\S*services\s+import\s+.*\bbackfill\b|^\s*from\s+\S*services\.backfill\s+import", re.M)
    users = [
        p.relative_to(APP).as_posix()
        for p in APP.rglob("*.py")
        if p.name != "backfill.py" and pattern.search(p.read_text(encoding="utf-8"))
    ]
    assert users == ["api/rooms.py"]
    for f in ("api/ws.py", "realtime.py", "services/groups.py", "services/submissions.py", "services/phase.py"):
        assert not re.search(r"\bservices\.backfill\b|import .*\bbackfill\b", (APP / f).read_text(encoding="utf-8")), f
    holders = sorted(
        p.relative_to(APP).as_posix()
        for p in APP.rglob("*.py")
        if "SHEETS_WRITE_SCOPE" in p.read_text(encoding="utf-8")
    )
    assert holders == ["config.py", "sheets/client.py"]
