"""Step 12 US1：投影憑證、唯讀、錯誤一致、不計為組別、即時名單。"""
import json

import pytest

from app.store import store

from .conftest import (
    SHEET_URL,
    auth,
    get_projector_key,
    join_student,
    projector_ws,
)

UNAVAILABLE = {"type": "projector_unavailable"}


def _create(client):
    p = client.post("/api/sheets/preview", json={"url": SHEET_URL}).json()
    r = client.post("/api/rooms", json={"sheetUrl": SHEET_URL, "fingerprint": p["fingerprint"]})
    assert r.status_code == 201
    return r.json()


def test_key_is_distinct_and_reaches_only_the_teacher(client, use_sheet):
    body = _create(client)
    code, token, key = body["code"], body["teacherToken"], body["projectorKey"]
    assert key and key not in (token, body["recoveryCode"])
    assert get_projector_key(client, code, token) == key
    rec = client.post("/api/rooms/recover", json={"recoveryCode": body["recoveryCode"]}).json()
    assert get_projector_key(client, code, rec["teacherToken"]) == key  # 換裝置後相同
    cm, ws, joined = join_student(client, code, "第 1 組")
    try:
        assert key not in json.dumps(joined, ensure_ascii=False)
    finally:
        cm.__exit__(None, None, None)


def test_valid_key_gets_initial_state(client, use_sheet):
    b = _create(client)
    cm, _ws, msg = projector_ws(client, b["code"], b["projectorKey"])
    try:
        assert msg["type"] == "projector_state" and msg["phase"] == "Waiting" and msg["code"] == b["code"]
        assert msg["groups"] == [] and msg["progress"] is None and msg["submitted"] is None
        assert msg["result"] is None and msg["scoreboard"] == []
    finally:
        cm.__exit__(None, None, None)


@pytest.mark.parametrize("which", ["wrong", "teacher", "recovery", "empty", "no_room"])
def test_bad_credentials_get_identical_rejection(client, use_sheet, which):
    b = _create(client)
    code = b["code"]
    key = {"wrong": "nope", "teacher": b["teacherToken"], "recovery": b["recoveryCode"], "empty": "", "no_room": b["projectorKey"]}[which]
    if which == "no_room":
        code = "ZZZZZZ"
    cm, ws, first = projector_ws(client, code, key)
    try:
        assert first == UNAVAILABLE
    finally:
        cm.__exit__(None, None, None)


def _snap(code):
    r = store.rooms[code]
    return (
        [(s.group_name, s.question_id, s.answer, s.seq) for s in r.submissions],
        sorted(r.groups),
        r.phase,
        len(r.phase_log),
        len(r.reviews),
        r.round,
        r.last_activity_at,
    )


def test_projector_is_read_only(client, use_sheet):
    b = _create(client)
    code = b["code"]
    cm, ws, _ = projector_ws(client, code, b["projectorKey"])
    try:
        before = _snap(code)
        for m in (
            {"type": "submit", "questionId": "1", "answer": "x"},
            {"type": "join", "code": code, "name": "第 9 組"},
            {"type": "start"},
            {"anything": 1},
        ):
            ws.send_json(m)
        ws.send_text("not json")
        # 之後仍可正常推送：老師開始搶答，投影收到狀態
        client.post(f"/api/rooms/{code}/phase/start", headers=auth(b["teacherToken"]))
        assert ws.receive_json()["phase"] == "Answering"
        after = _snap(code)
        assert after[0] == before[0] and after[1] == before[1] and after[4] == before[4]
    finally:
        cm.__exit__(None, None, None)


@pytest.mark.parametrize(
    "method, path",
    [
        ("post", "phase/start"),
        ("post", "phase/end"),
        ("post", "close"),
        ("post", "backfill"),
        ("post", "backfill/preview"),
        ("post", "reviews"),
        ("get", "records.csv"),
    ],
)
def test_projector_key_cannot_use_teacher_endpoints(client, use_sheet, method, path):
    b = _create(client)
    code = b["code"]
    bodies = {
        "backfill": {"round": 1},
        "backfill/preview": {"round": 1},
        "reviews": {"round": 1, "unitId": "1", "group": "第 1 組", "action": "invalid", "reason": "x"},
    }
    r = getattr(client, method)(
        f"/api/rooms/{code}/{path}",
        headers=auth(b["projectorKey"]),
        **({"json": bodies.get(path, {})} if method == "post" else {}),
    )
    assert r.status_code == 401
    room = store.rooms[code]
    assert room.phase == "Waiting" and room.status == "Open" and not room.reviews


def test_projectors_are_not_groups_and_do_not_touch_activity(client, use_sheet):
    b = _create(client)
    code = b["code"]
    room = store.rooms[code]
    stamp = room.last_activity_at
    conns = [projector_ws(client, code, b["projectorKey"]) for _ in range(3)]
    try:
        for _cm, ws, _ in conns:
            ws.send_json({"type": "ping"})
        assert room.last_activity_at == stamp
        assert len(room.groups) == 0
        with client.websocket_connect(f"/ws/teacher?token={b['teacherToken']}&code={code}") as t:
            snap = t.receive_json()
            assert snap["count"] == 0 and snap["groups"] == []
        cm, _ws, joined = join_student(client, code, "第 1 組")  # 組名不受影響
        assert joined["group"]["name"] == "第 1 組"
        cm.__exit__(None, None, None)
    finally:
        for cm, _ws, _ in conns:
            cm.__exit__(None, None, None)


def test_new_group_updates_every_projector_but_reconnect_does_not(client, use_sheet):
    b = _create(client)
    code = b["code"]
    p1 = projector_ws(client, code, b["projectorKey"])
    p2 = projector_ws(client, code, b["projectorKey"])
    try:
        cm, ws, _ = join_student(client, code, "第 1 組")
        for _c, pws, _ in (p1, p2):
            assert pws.receive_json()["groups"] == ["第 1 組"]
        cm2, _w2, _ = join_student(client, code, "第 1 組")  # 同組第二視窗：不是新組別
        cm2.__exit__(None, None, None)
        cm3, _w3, _ = join_student(client, code, "第 2 組")
        for _c, pws, _ in (p1, p2):
            assert pws.receive_json()["groups"] == ["第 1 組", "第 2 組"]  # 下一則就是第 2 組的名單
        cm3.__exit__(None, None, None)
        cm.__exit__(None, None, None)
    finally:
        for cm_, _w, _ in (p1, p2):
            cm_.__exit__(None, None, None)
