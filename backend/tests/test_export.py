"""Step 8 US1：老師匯出作答明細 CSV（內容、欄位、排名、標頭、空狀態）。"""
import re

from app.models import iso
from app.store import store

from .conftest import get_export, join_student, make_started_room, parse_csv
from .test_submission_privacy import flush

HEADER = ["輪次", "題號", "題組", "組別", "答案", "接收時間", "排名"]
TIME_RE = re.compile(r"^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}Z$")


def _submit(ws, qid, answer):
    ws.send_json({"type": "submit", "questionId": qid, "answer": answer})
    flush(ws)


def _room_with_records(client):
    code, token = make_started_room(client)
    a, wa, _ = join_student(client, code, "第 1 組")
    b, wb, _ = join_student(client, code, "第 2 組")
    _submit(wa, "1", "CPU")
    _submit(wb, "1", "cpu")
    _submit(wa, "2", "二進位")
    return code, token, (a, b)


def test_export_content_columns_and_ranks(client, use_sheet):
    code, token, cms = _room_with_records(client)
    try:
        r = get_export(client, code, token)
        assert r.status_code == 200
        rows = parse_csv(r)
        assert rows[0] == HEADER
        assert len(rows) == 4  # 標題列 + 3 筆
        data = rows[1:]
        assert [row[1:4] + row[4:5] + row[6:] for row in data] == [
            ["Q1", "", "第 1 組", "CPU", "1"],
            ["Q1", "", "第 2 組", "cpu", "2"],
            ["Q2", "", "第 1 組", "二進位", "1"],
        ]
        assert all(row[0] == "1" for row in data)
        # 接收時間：格式正確，且就是後端記錄的時間（客戶端無法影響）
        subs = {(s.group_name, s.question_id): s for s in store.rooms[code].submissions}
        for row in data:
            assert TIME_RE.match(row[5])
        assert data[0][5] == iso(subs[("第 1 組", "1")].submitted_at)
        assert data[1][5] == iso(subs[("第 2 組", "1")].submitted_at)
    finally:
        for cm in cms:
            cm.__exit__(None, None, None)


def test_export_works_while_answering(client, use_sheet):
    code, token, cms = _room_with_records(client)
    try:
        assert store.rooms[code].phase == "Answering"
        assert get_export(client, code, token).status_code == 200
    finally:
        for cm in cms:
            cm.__exit__(None, None, None)


def test_export_without_records_returns_no_records(client, use_sheet):
    code, token = make_started_room(client)
    r = get_export(client, code, token)
    assert r.status_code == 404
    e = r.json()["error"]
    assert e["code"] == "NO_RECORDS" and e["message"] == "尚無送出紀錄可匯出"
    assert "text/csv" not in r.headers.get("content-type", "")


def test_export_headers(client, use_sheet):
    code, token, cms = _room_with_records(client)
    try:
        r = get_export(client, code, token)
        ctype = r.headers["content-type"].lower()
        assert ctype.startswith("text/csv") and "charset=utf-8" in ctype
        disp = r.headers["content-disposition"]
        assert disp.startswith("attachment")
        assert f"records_{code}_" in disp and "filename*=UTF-8''" in disp
        assert r.headers["cache-control"] == "no-store"
    finally:
        for cm in cms:
            cm.__exit__(None, None, None)


def test_export_uses_subquestion_labels(client, use_sheet):
    use_sheet("group.xlsx")
    code, token = make_started_room(client)
    a, wa, _ = join_student(client, code, "第 1 組")
    try:
        _submit(wa, "1-2", "答")
        rows = parse_csv(get_export(client, code, token))
        assert rows[1][1] == "Q1（2）"
    finally:
        a.__exit__(None, None, None)
