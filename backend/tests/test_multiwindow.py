import time

from app.store import store

from .conftest import auth, drain, join_student, make_started_room


def submit(ws, qid, answer):
    ws.send_json({"type": "submit", "questionId": qid, "answer": answer})
    return ws.receive_json()


def teacher_ws(client, code, token):
    cm = client.websocket_connect(f"/ws/teacher?code={code}&token={token}")
    ws = cm.__enter__()
    snap = ws.receive_json()
    return cm, ws, snap


def test_second_window_not_rejected_and_group_listed_once(client, use_sheet):
    code, token = make_started_room(client)
    tcm, tws, _ = teacher_ws(client, code, token)
    c1, w1, j1 = join_student(client, code, "第 1 組")
    c2, w2, j2 = join_student(client, code, "第 1 組")
    try:
        assert j1["type"] == "joined" and j2["type"] == "joined"
        assert j2["rejoined"] is True
        assert len(store.rooms[code].groups) == 1
        # 老師只收到一次 group_joined；第二個視窗不重複通知
        first = tws.receive_json()
        assert first["type"] == "group_joined"
        # 再加入一個其他組的視窗，下一則應是第 2 組而不是第 1 組的重複通知
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


def test_submit_in_one_window_syncs_to_other(client, use_sheet):
    code, _ = make_started_room(client)
    c1, w1, _ = join_student(client, code, "第 1 組")
    c2, w2, _ = join_student(client, code, "第 1 組")
    try:
        m1 = submit(w1, "1", "CPU")
        m2 = w2.receive_json()  # 另一個視窗被動同步
        assert m1 == m2 == {"type": "submitted", "questionId": "1", "answer": "CPU", "round": 1}
    finally:
        c1.__exit__(None, None, None)
        c2.__exit__(None, None, None)


def test_window_limit_ten(client, use_sheet):
    code, _ = make_started_room(client)
    conns = [join_student(client, code, "第 1 組") for _ in range(10)]
    try:
        assert all(j["type"] == "joined" for _, _, j in conns)
        cm, ws, msg = join_student(client, code, "第 1 組")  # 第 11 個
        try:
            assert msg["type"] == "error" and msg["code"] == "GROUP_WINDOWS_FULL"
        finally:
            cm.__exit__(None, None, None)
        # 原有視窗不受影響：仍可送出並收到
        assert submit(conns[0][1], "1", "CPU")["type"] == "submitted"
    finally:
        for cm, _, _ in conns:
            cm.__exit__(None, None, None)


def test_online_only_until_last_window_leaves(client, use_sheet):
    code, token = make_started_room(client)
    tcm, tws, _ = teacher_ws(client, code, token)
    c1, w1, _ = join_student(client, code, "第 1 組")
    tws.receive_json()  # group_joined
    c2, w2, _ = join_student(client, code, "第 1 組")
    try:
        c1.__exit__(None, None, None)  # 關第一個視窗
        time.sleep(0.2)
        assert store.rooms[code].groups["第1組"].online is True
        c2.__exit__(None, None, None)  # 關最後一個
        msg = tws.receive_json()
        assert msg == {"type": "group_status", "name": "第 1 組", "online": False}
        assert store.rooms[code].groups["第1組"].online is False
    finally:
        tcm.__exit__(None, None, None)


def test_rejoin_restores_my_submissions(client, use_sheet):
    code, token = make_started_room(client)
    c1, w1, _ = join_student(client, code, "第 1 組")
    c2, w2, _ = join_student(client, code, "第 1 組")
    try:
        submit(w1, "1", "CPU")
        w2.receive_json()
        c2.__exit__(None, None, None)  # 視窗 B 離線
        submit(w1, "2", "二進位")  # 離線期間另一視窗送出
        c3, w3, j3 = join_student(client, code, "第 1 組")
        try:
            assert j3["mySubmissions"] == {"1": "CPU", "2": "二進位"}
            assert j3["submittedByOthers"] == []
        finally:
            c3.__exit__(None, None, None)
        # 新一輪開始後重置
        client.post(f"/api/rooms/{code}/phase/end", headers=auth(token))
        drain(w1, 2)
        client.post(f"/api/rooms/{code}/phase/start", headers=auth(token))
        drain(w1, 2)
        c4, w4, j4 = join_student(client, code, "第 1 組")
        try:
            assert j4["mySubmissions"] == {} and j4["round"] == 2
        finally:
            c4.__exit__(None, None, None)
    finally:
        c1.__exit__(None, None, None)
