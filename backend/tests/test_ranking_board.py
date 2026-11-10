"""老師端進度板：由送出紀錄推導並即時推送。"""
from app.services import ranking
from app.store import store

from .conftest import auth, drain, join_student, make_started_room


def teacher(client, code, token):
    cm = client.websocket_connect(f"/ws/teacher?code={code}&token={token}")
    ws = cm.__enter__()
    return cm, ws, ws.receive_json()


def submit(ws, qid, answer):
    ws.send_json({"type": "submit", "questionId": qid, "answer": answer})
    return ws.receive_json()


def test_empty_board(client, use_sheet):
    code, _ = make_started_room(client)
    b = ranking.build_board(store.rooms[code])
    assert len(b["questions"]) == 6 and b["leadTally"] == []
    assert all(q["leader"] is None and q["submittedCount"] == 0 and q["ranking"] == [] for q in b["questions"])
    assert [q["questionId"] for q in b["questions"]] == ["1", "2", "3", "4", "5", "6"]


def test_board_events_leader_and_tally(client, use_sheet):
    code, token = make_started_room(client)
    tcm, tws, snap = teacher(client, code, token)
    assert snap["room"]["board"]["leadTally"] == []
    c1, w1, _ = join_student(client, code, "第 1 組")
    c2, w2, _ = join_student(client, code, "第 2 組")
    try:
        drain(tws, 2)
        submit(w1, "1", "a")
        w2.receive_json()
        assert tws.receive_json()["type"] == "submission"
        b = tws.receive_json()
        assert b["type"] == "board" and b["questions"][0]["leader"] == "第 1 組"
        submit(w2, "1", "b")
        w1.receive_json()
        tws.receive_json()
        b = tws.receive_json()
        q1 = b["questions"][0]
        assert q1["leader"] == "第 1 組" and q1["submittedCount"] == 2
        assert [(r["rank"], r["group"]) for r in q1["ranking"]] == [(1, "第 1 組"), (2, "第 2 組")]
        assert b["questions"][1]["leader"] is None
        # 第 2 組領先 Q2；領先題數：各 1，同數依組名
        submit(w2, "2", "c")
        w1.receive_json()
        tws.receive_json()
        b = tws.receive_json()
        assert b["leadTally"] == [
            {"group": "第 1 組", "leadCount": 1},
            {"group": "第 2 組", "leadCount": 1},
        ]
        assert b == ranking.build_board(store.rooms[code])
        # 重複與被拒絕的送出不觸發 board
        submit(w1, "1", "again")
        submit(w1, "1", "")
        submit(w2, "3", "d")
        w1.receive_json()
        assert tws.receive_json()["type"] == "submission"
        assert tws.receive_json()["type"] == "board"
    finally:
        for c in (c1, c2, tcm):
            c.__exit__(None, None, None)


def test_snapshot_restores_and_new_round_clears(client, use_sheet):
    code, token = make_started_room(client)
    c1, w1, _ = join_student(client, code, "第 1 組")
    try:
        submit(w1, "1", "a")
        tcm, tws, snap = teacher(client, code, token)
        try:
            assert snap["room"]["board"] == ranking.build_board(store.rooms[code])
            assert snap["room"]["board"]["questions"][0]["leader"] == "第 1 組"
            client.post(f"/api/rooms/{code}/phase/end", headers=auth(token))
            drain(tws, 1)
            client.post(f"/api/rooms/{code}/phase/start", headers=auth(token))
            msgs = drain(tws, 3)  # phase_changed, question_texts, board
            b = [m for m in msgs if m["type"] == "board"][0]
            assert b["round"] == 2 and all(q["submittedCount"] == 0 for q in b["questions"])
            assert len(store.rooms[code].submissions) == 1  # 舊紀錄保留
        finally:
            tcm.__exit__(None, None, None)
    finally:
        c1.__exit__(None, None, None)


def test_two_groups_simultaneous_q1(client, use_sheet):
    """驗證效果：兩組同時送 Q1 → 一個第 1、一個第 2；看板顯示最快組別。"""
    code, token = make_started_room(client)
    c1, w1, _ = join_student(client, code, "第 1 組")
    c2, w2, _ = join_student(client, code, "第 2 組")
    try:
        w1.send_json({"type": "submit", "questionId": "1", "answer": "a"})
        w2.send_json({"type": "submit", "questionId": "1", "answer": "b"})
        drain(w1, 2), drain(w2, 2)
        b = ranking.build_board(store.rooms[code])
        q1 = b["questions"][0]
        assert sorted(r["rank"] for r in q1["ranking"]) == [1, 2]
        assert q1["leader"] == q1["ranking"][0]["group"]
    finally:
        c1.__exit__(None, None, None)
        c2.__exit__(None, None, None)
