import json

import pytest

from app.models import err
from app.services import sheets as sheets_service  # noqa: F401
from app.store import store

from .conftest import auth, join_student

URL = "https://docs.google.com/spreadsheets/d/abc123/edit#gid=0"
PUBLIC_KEYS = {"id", "number", "sub", "label"}


def preview(client, url=URL):
    return client.post("/api/sheets/preview", json={"url": url})


def create_with_sheet(client):
    p = preview(client).json()
    return client.post("/api/rooms", json={"sheetUrl": URL, "fingerprint": p["fingerprint"]})


# ---- US1：預覽與建立 ----

def test_preview_ok_without_cells(client, use_sheet):
    r = preview(client)
    assert r.status_code == 200
    body = r.json()
    assert body["sheetTitle"] == "學習單"
    assert [q["id"] for q in body["questions"]] == ["1", "2", "3", "4", "5", "6"]
    assert all(set(q.keys()) == PUBLIC_KEYS for q in body["questions"])
    assert "!G" not in r.text and "cell" not in r.text
    assert store.rooms == {}  # 預覽不建立房間


def test_preview_group_sample(client, use_sheet):
    use_sheet("group.xlsx")
    ids = [q["id"] for q in preview(client).json()["questions"]]
    assert ids == ["1-1", "1-2", "2-1", "2-2", "3", "4"]


def test_preview_invalid_url(client, use_sheet):
    r = preview(client, "https://evil.example.com/spreadsheets/d/abc/edit")
    assert r.status_code == 400 and r.json()["error"]["code"] == "SHEET_URL_INVALID"


def test_preview_not_configured(client, monkeypatch):
    monkeypatch.setenv("GOOGLE_SERVICE_ACCOUNT_FILE", "")
    r = preview(client)
    assert r.status_code == 503 and r.json()["error"]["code"] == "SHEETS_NOT_CONFIGURED"


def test_create_without_body_still_works(client):
    r = client.post("/api/rooms")
    assert r.status_code == 201
    body = r.json()
    assert body["questions"] == [] and body["sheetTitle"] is None


def test_create_with_sheet(client, use_sheet):
    r = create_with_sheet(client)
    assert r.status_code == 201
    body = r.json()
    assert len(body["questions"]) == 6
    assert all(set(q.keys()) == PUBLIC_KEYS for q in body["questions"])
    room = store.rooms[body["code"]]
    assert room.questions[0].cell == "'學習單'!G5"  # 伺服器保存位置
    assert room.sheet.fingerprint


def test_fingerprint_mismatch_does_not_create_room(client, use_sheet):
    p = preview(client).json()
    use_sheet("group.xlsx")  # 預覽後試算表被改動
    r = client.post("/api/rooms", json={"sheetUrl": URL, "fingerprint": p["fingerprint"]})
    assert r.status_code == 409 and r.json()["error"]["code"] == "SHEET_CHANGED"
    assert store.rooms == {} and store.recovery_index == {}


def test_only_one_of_url_or_fingerprint(client, use_sheet):
    assert client.post("/api/rooms", json={"sheetUrl": URL}).status_code == 400
    assert client.post("/api/rooms", json={"fingerprint": "x"}).status_code == 400
    assert store.rooms == {}


@pytest.mark.parametrize(
    "code",
    ["SHEET_FORBIDDEN", "SHEET_NOT_FOUND", "SHEET_TIMEOUT", "SHEET_QUESTIONS_INVALID", "SHEET_NO_QUESTIONS"],
)
def test_sheet_errors_never_create_room(client, monkeypatch, code):
    async def boom(spreadsheet_id, gid):
        raise err(code)

    monkeypatch.setattr(sheets_service, "_fetch", boom)
    r = client.post("/api/rooms", json={"sheetUrl": URL, "fingerprint": "x"})
    assert r.json()["error"]["code"] == code
    assert store.rooms == {} and store.recovery_index == {}


# ---- US2：學生端取得題目 ----

def _teacher_ws(client, code, token):
    cm = client.websocket_connect(f"/ws/teacher?code={code}&token={token}")
    return cm, cm.__enter__(), None


def test_joined_has_public_questions_only(client, use_sheet):
    body = create_with_sheet(client).json()
    cm, ws, joined = join_student(client, body["code"], "第 1 組")
    try:
        assert [q["id"] for q in joined["questions"]] == ["1", "2", "3", "4", "5", "6"]
        assert all(set(q.keys()) == PUBLIC_KEYS for q in joined["questions"])
        assert "!" not in json.dumps(joined, ensure_ascii=False)  # 不含試算表位置
    finally:
        cm.__exit__(None, None, None)
    # 斷線後重新加入，題目相同（FR-008）
    cm2, ws2, joined2 = join_student(client, body["code"], "第 1 組")
    try:
        assert joined2["questions"] == joined["questions"]
        assert joined2["rejoined"] is True
    finally:
        cm2.__exit__(None, None, None)


def test_joined_without_sheet_has_empty_questions(client):
    code = client.post("/api/rooms").json()["code"]
    cm, ws, joined = join_student(client, code, "第 1 組")
    try:
        assert joined["questions"] == []
    finally:
        cm.__exit__(None, None, None)


# ---- US3：老師端題目清單 ----

def test_teacher_snapshot_has_questions(client, use_sheet):
    body = create_with_sheet(client).json()
    cm, ws, _ = _teacher_ws(client, body["code"], body["teacherToken"])
    try:
        snap = ws.receive_json()
        room = snap["room"]
        assert room["sheetTitle"] == "學習單"
        assert len(room["questions"]) == 6
        assert all(set(q.keys()) == PUBLIC_KEYS for q in room["questions"])
        assert "!G" not in json.dumps(snap, ensure_ascii=False)
    finally:
        cm.__exit__(None, None, None)


def test_snapshot_questions_survive_recover(client, use_sheet):
    body = create_with_sheet(client).json()
    r = client.post("/api/rooms/recover", json={"recoveryCode": body["recoveryCode"]})
    assert r.status_code == 200
    cm, ws, _ = _teacher_ws(client, body["code"], r.json()["teacherToken"])
    try:
        assert len(ws.receive_json()["room"]["questions"]) == 6
    finally:
        cm.__exit__(None, None, None)


def test_snapshot_without_sheet(client):
    body = client.post("/api/rooms").json()
    cm, ws, _ = _teacher_ws(client, body["code"], body["teacherToken"])
    try:
        room = ws.receive_json()["room"]
        assert room["questions"] == [] and room["sheetTitle"] is None
    finally:
        cm.__exit__(None, None, None)


# ---- 題目文字：開始搶答後才顯示（FR-014、SC-007） ----

SAMPLE_TEXT_FRAGMENTS = ["英文縮寫", "二進位", "後進先出", "Windows"]


def _start(client, code, token):
    return client.post(f"/api/rooms/{code}/phase/start", headers=auth(token))


def _end(client, code, token):
    return client.post(f"/api/rooms/{code}/phase/end", headers=auth(token))


def test_preview_and_public_questions_have_no_text(client, use_sheet):
    r = preview(client)
    assert not any(f in r.text for f in SAMPLE_TEXT_FRAGMENTS)
    body = create_with_sheet(client).json()
    assert not any(f in json.dumps(body, ensure_ascii=False) for f in SAMPLE_TEXT_FRAGMENTS)


def test_no_text_before_start(client, use_sheet):
    body = create_with_sheet(client).json()
    cm, ws, joined = join_student(client, body["code"], "第 1 組")
    try:
        assert joined["texts"] == {}
        assert not any(f in json.dumps(joined, ensure_ascii=False) for f in SAMPLE_TEXT_FRAGMENTS)
    finally:
        cm.__exit__(None, None, None)


def test_texts_revealed_on_start_and_hidden_after(client, use_sheet):
    body = create_with_sheet(client).json()
    code, token = body["code"], body["teacherToken"]
    tcm, tws, _ = _teacher_ws(client, code, token)
    tws.receive_json()  # snapshot
    scm, sws, joined = join_student(client, code, "第 1 組")
    tws.receive_json()  # group_joined
    try:
        assert _start(client, code, token).status_code == 200
        for ws in (sws, tws):
            phase = ws.receive_json()
            assert set(phase.keys()) == {"type", "phase", "round", "changedAt"}
            qt = ws.receive_json()
            assert qt["type"] == "question_texts" and qt["round"] == 1
            assert set(qt["texts"].keys()) == {"1", "2", "3", "4", "5", "6"}
            assert "英文縮寫" in qt["texts"]["1"]
        # 搶答中重新加入：立即取得
        scm.__exit__(None, None, None)
        scm, sws, joined2 = join_student(client, code, "第 1 組")
        assert len(joined2["texts"]) == 6
        # 結束後：不再送出；重連也拿不到
        assert _end(client, code, token).status_code == 200
        assert sws.receive_json()["phase"] == "Ended"
        scm.__exit__(None, None, None)
        scm, sws, joined3 = join_student(client, code, "第 1 組")
        assert joined3["texts"] == {}
    finally:
        scm.__exit__(None, None, None)
        tcm.__exit__(None, None, None)


def test_teacher_snapshot_has_texts(client, use_sheet):
    body = create_with_sheet(client).json()
    cm, ws, _ = _teacher_ws(client, body["code"], body["teacherToken"])
    try:
        texts = ws.receive_json()["room"]["texts"]
        assert len(texts) == 6 and "英文縮寫" in texts["1"]
    finally:
        cm.__exit__(None, None, None)


def test_group_texts_keyed_by_id(client, use_sheet):
    use_sheet("group.xlsx")
    body = create_with_sheet(client).json()
    code, token = body["code"], body["teacherToken"]
    _start(client, code, token)
    cm, ws, joined = join_student(client, code, "第 1 組")
    try:
        assert set(joined["texts"].keys()) == {"1-1", "1-2", "2-1", "2-2", "3", "4"}
    finally:
        cm.__exit__(None, None, None)
