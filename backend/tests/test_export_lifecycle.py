"""Step 8 US4：活動結束後（含房間結束、閒置自動結束）仍可匯出；房間被清除後明確提示。"""
import asyncio
from datetime import timedelta

from app.main import _sweep_once
from app.models import utcnow
from app.store import store

from .conftest import auth, get_export, join_student, make_started_room
from .test_submission_privacy import flush


def _with_record(client):
    code, token = make_started_room(client)
    cm, ws, _ = join_student(client, code, "第 1 組")
    ws.send_json({"type": "submit", "questionId": "1", "answer": "CPU"})
    flush(ws)
    cm.__exit__(None, None, None)  # 學生離線（房間無連線，才會被閒置掃描關閉）
    return code, token


def test_same_content_before_and_after_ending_answering(client, use_sheet):
    code, token = _with_record(client)
    before = get_export(client, code, token).content
    assert client.post(f"/api/rooms/{code}/phase/end", headers=auth(token)).status_code == 200
    assert store.rooms[code].phase == "Ended"
    assert get_export(client, code, token).content == before


def test_export_after_room_closed_manually(client, use_sheet):
    code, token = _with_record(client)
    before = get_export(client, code, token).content
    assert client.post(f"/api/rooms/{code}/close", headers=auth(token)).status_code == 200
    assert store.rooms[code].status == "Closed"
    r = get_export(client, code, token)
    assert r.status_code == 200 and r.content == before


def test_export_after_idle_auto_close(client, use_sheet):
    code, token = _with_record(client)
    before = get_export(client, code, token).content
    store.rooms[code].last_activity_at = utcnow() - timedelta(hours=3)
    asyncio.run(_sweep_once())
    room = store.rooms[code]
    assert room.status == "Closed" and room.closed_reason == "IdleTimeout"
    r = get_export(client, code, token)
    assert r.status_code == 200 and r.content == before


def test_room_removed_returns_records_gone(client, use_sheet):
    code, token = _with_record(client)
    store.remove_room(code)  # 模擬超過 24 小時保留期（或服務重啟）
    r = get_export(client, code, token)
    assert r.status_code == 404
    e = r.json()["error"]
    assert e["code"] == "RECORDS_GONE"
    assert e["message"] == "紀錄已不存在，請於活動結束後盡快匯出"
    assert "text/csv" not in r.headers.get("content-type", "")


def test_never_created_room_also_records_gone(client):
    r = get_export(client, "ZZZZZZ", "any-token")
    assert r.status_code == 404 and r.json()["error"]["code"] == "RECORDS_GONE"


def test_closed_room_without_records_is_no_records_not_gone(client, use_sheet):
    code, token = make_started_room(client)
    assert client.post(f"/api/rooms/{code}/close", headers=auth(token)).status_code == 200
    r = get_export(client, code, token)
    assert r.status_code == 404 and r.json()["error"]["code"] == "NO_RECORDS"
