"""結果公布：結算時每題第 1 名的組名與答案。"""
from app.services import ranking, results
from app.store import store

from .conftest import auth, drain, join_student, make_started_room


def submit(ws, qid, answer):
    ws.send_json({"type": "submit", "questionId": qid, "answer": answer})
    return ws.receive_json()


def _end(client, code, token):
    return client.post(f"/api/rooms/{code}/phase/end", headers=auth(token))


def _teacher(client, code, token):
    cm = client.websocket_connect(f"/ws/teacher?code={code}&token={token}")
    ws = cm.__enter__()
    return cm, ws, ws.receive_json()


def _play(client):
    """3 組：第 1 組先送 Q1、第 2 組後送 Q1、第 3 組送 Q2；第 1 組另開第二視窗。"""
    code, token = make_started_room(client)
    c1, w1, _ = join_student(client, code, "第 1 組")
    c1b, w1b, _ = join_student(client, code, "第 1 組")
    c2, w2, _ = join_student(client, code, "第 2 組")
    c3, w3, _ = join_student(client, code, "第 3 組")
    submit(w1, "1", "CPU")
    w1b.receive_json(), w2.receive_json(), w3.receive_json()
    submit(w2, "1", "GPU")
    w1.receive_json(), w1b.receive_json(), w3.receive_json()
    submit(w3, "2", "RAM")
    w1.receive_json(), w1b.receive_json(), w2.receive_json()
    return code, token, [(c1, w1), (c1b, w1b), (c2, w2), (c3, w3)]


def _close(conns):
    for c, _ in conns:
        c.__exit__(None, None, None)


def test_round_result_to_all_students(client, use_sheet):
    code, token, conns = _play(client)
    try:
        assert _end(client, code, token).json()["changed"] is True
        msgs = []
        for _, ws in conns:
            assert ws.receive_json()["type"] == "phase_changed"
            msgs.append(ws.receive_json())
        assert all(m == msgs[0] for m in msgs)  # 每個視窗（含同組、他組）內容相同
        m = msgs[0]
        assert m["type"] == "round_result" and m["round"] == 1
        res = m["results"]
        assert [r["questionId"] for r in res] == ["1", "2", "3", "4", "5", "6"]
        assert res[0] == {"questionId": "1", "winnerGroup": "第 1 組", "answer": "CPU"}
        assert res[1] == {"questionId": "2", "winnerGroup": "第 3 組", "answer": "RAM"}
        assert all(r["winnerGroup"] is None and r["answer"] is None for r in res[2:])
        # 與老師看板一致
        board = ranking.build_board(store.rooms[code])
        for r, q in zip(res, board["questions"]):
            assert r["winnerGroup"] == q["leader"]
    finally:
        _close(conns)


def test_no_submissions_all_null(client, use_sheet):
    code, token = make_started_room(client)
    c1, w1, _ = join_student(client, code, "第 1 組")
    try:
        _end(client, code, token)
        w1.receive_json()
        m = w1.receive_json()
        assert len(m["results"]) == 6
        assert all(r["winnerGroup"] is None and r["answer"] is None for r in m["results"])
    finally:
        c1.__exit__(None, None, None)


def test_group_sheet_question_ids(client, use_sheet):
    use_sheet("group.xlsx")
    code, token = make_started_room(client)
    c1, w1, _ = join_student(client, code, "第 1 組")
    try:
        qids = [q.id for q in store.rooms[code].questions]
        assert any("-" in q for q in qids)
        assert submit(w1, qids[-1], "x")["type"] == "submitted"
        _end(client, code, token)
        w1.receive_json()
        m = w1.receive_json()
        assert [r["questionId"] for r in m["results"]] == qids
        assert m["results"][-1]["winnerGroup"] == "第 1 組"
    finally:
        c1.__exit__(None, None, None)


def test_repeat_end_no_second_result_and_stable(client, use_sheet):
    code, token, conns = _play(client)
    try:
        _end(client, code, token)
        drain(conns[0][1], 2)
        before = results.build_result(store.rooms[code])
        assert _end(client, code, token).json()["changed"] is False
        assert results.build_result(store.rooms[code]) == before
        # 之後送出被拒絕；結果不變；同連線下一則訊息就是錯誤（沒有第二則 round_result）
        ws = conns[0][1]
        ws.send_json({"type": "submit", "questionId": "3", "answer": "late"})
        assert ws.receive_json()["code"] == "PHASE_LOCKED"
        assert results.build_result(store.rooms[code]) == before
    finally:
        _close(conns)


def test_teacher_gets_identical_round_result(client, use_sheet):
    code, token, conns = _play(client)
    tcm, tws, snap = _teacher(client, code, token)
    try:
        assert snap["room"]["result"] is None  # 公布前
        _end(client, code, token)
        assert tws.receive_json()["type"] == "phase_changed"
        tm = tws.receive_json()
        assert tm["type"] == "round_result"
        sm = [conns[0][1].receive_json() for _ in range(2)][1]
        assert tm == sm
        board = ranking.build_board(store.rooms[code])
        for r, q in zip(tm["results"], board["questions"]):
            assert r["winnerGroup"] == q["leader"]
        tcm2, tws2, snap2 = _teacher(client, code, token)
        try:
            assert snap2["room"]["result"] == {"round": tm["round"], "results": tm["results"]}
        finally:
            tcm2.__exit__(None, None, None)
    finally:
        tcm.__exit__(None, None, None)
        _close(conns)
