"""同組單一視窗：第二個視窗被拒絕，原視窗不受影響；原視窗關閉後可重新加入。"""
import time

from app.store import store

from .conftest import (
    assert_second_window_rejected,
    auth,
    drain,
    join_student,
    join_student_retry,
    make_started_room,
)


def submit(ws, qid, answer):
    ws.send_json({"type": "submit", "questionId": qid, "answer": answer})
    return ws.receive_json()


def teacher_ws(client, code, token):
    cm = client.websocket_connect(f"/ws/teacher?code={code}&token={token}")
    ws = cm.__enter__()
    snap = ws.receive_json()
    return cm, ws, snap


def test_second_window_rejected_and_group_listed_once(client, use_sheet):
    code, token = make_started_room(client)
    tcm, tws, _ = teacher_ws(client, code, token)
    c1, w1, j1 = join_student(client, code, "第 1 組")
    c2, w2, j2 = join_student(client, code, "第 1 組")
    try:
        assert j1["type"] == "joined"
        assert j2["type"] == "error" and j2["code"] == "GROUP_WINDOWS_FULL"
        assert len(store.rooms[code].groups) == 1
        first = tws.receive_json()
        assert first["type"] == "group_joined"
        # 被拒絕的視窗不會產生通知：下一則應是第 2 組，而不是第 1 組的重複通知
        c3, w3, _ = join_student(client, code, "第 2 組")
        try:
            nxt = tws.receive_json()
            assert nxt["type"] == "group_joined" and nxt["group"]["name"] == "第 2 組"
        finally:
            c3.__exit__(None, None, None)
    finally:
        c1.__exit__(None, None, None)
        c2.__exit__(None, None, None)
        tcm.__exit__(None, None, None)


def test_rejected_window_does_not_affect_original(client, use_sheet):
    code, _ = make_started_room(client)
    c1, w1, _ = join_student(client, code, "第 1 組")
    try:
        assert_second_window_rejected(client, code, "第 1 組")
        assert store.rooms[code].groups["第1組"].online is True
        # 原視窗仍可正常送出
        assert submit(w1, "1", "CPU") == {
            "type": "submitted", "questionId": "1", "answer": "CPU", "round": 1,
        }
    finally:
        c1.__exit__(None, None, None)


def test_rejection_is_per_group(client, use_sheet):
    code, _ = make_started_room(client)
    c1, _w1, j1 = join_student(client, code, "第 1 組")
    c2, _w2, j2 = join_student(client, code, "第 2 組")
    try:
        assert j1["type"] == "joined" and j2["type"] == "joined"
        assert_second_window_rejected(client, code, "第 1 組")
        assert_second_window_rejected(client, code, "第 2 組")
    finally:
        c1.__exit__(None, None, None)
        c2.__exit__(None, None, None)


def test_offline_after_window_closes_then_rejoin_allowed(client, use_sheet):
    code, token = make_started_room(client)
    tcm, tws, _ = teacher_ws(client, code, token)
    c1, w1, _ = join_student(client, code, "第 1 組")
    tws.receive_json()  # group_joined
    c1.__exit__(None, None, None)  # 唯一視窗關閉 → 離線
    msg = tws.receive_json()
    assert msg == {"type": "group_status", "name": "第 1 組", "online": False}
    assert store.rooms[code].groups["第1組"].online is False
    c2, w2, j2 = join_student_retry(client, code, "第 1 組")
    try:
        assert j2["type"] == "joined" and j2["rejoined"] is True
        assert store.rooms[code].groups["第1組"].online is True
    finally:
        c2.__exit__(None, None, None)
        tcm.__exit__(None, None, None)


def test_rejoin_restores_my_submissions(client, use_sheet):
    code, token = make_started_room(client)
    c1, w1, _ = join_student(client, code, "第 1 組")
    submit(w1, "1", "CPU")
    submit(w1, "2", "二進位")
    c1.__exit__(None, None, None)  # 唯一視窗離線
    c3, w3, j3 = join_student_retry(client, code, "第 1 組")
    try:
        assert j3["mySubmissions"] == {"1": "CPU", "2": "二進位"}
        assert j3["submittedByOthers"] == []
        # 新一輪開始後重置
        client.post(f"/api/rooms/{code}/phase/end", headers=auth(token))
        drain(w3, 2)
        client.post(f"/api/rooms/{code}/phase/start", headers=auth(token))
        drain(w3, 2)
    finally:
        c3.__exit__(None, None, None)
    c4, w4, j4 = join_student_retry(client, code, "第 1 組")
    try:
        assert j4["mySubmissions"] == {} and j4["round"] == 2
    finally:
        c4.__exit__(None, None, None)
