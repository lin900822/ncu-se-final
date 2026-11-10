"""順位仲裁：名次依後端處理序決定（原則 II）。"""
from app.store import store

from .conftest import auth, drain, join_student, make_started_room


def submit(ws, qid, answer, **extra):
    ws.send_json({"type": "submit", "questionId": qid, "answer": answer, **extra})
    return ws.receive_json()


def _subs(code):
    return store.rooms[code].submissions


def test_ranks_follow_arrival_order(client, use_sheet):
    code, token = make_started_room(client)
    tcm = client.websocket_connect(f"/ws/teacher?code={code}&token={token}")
    tws = tcm.__enter__()
    tws.receive_json()  # snapshot
    conns = [join_student(client, code, f"第 {i} 組") for i in (1, 2, 3)]
    try:
        drain(tws, 3)  # group_joined x3
        for i, (_, ws, _) in enumerate(conns, start=1):
            assert submit(ws, "1", f"A{i}")["type"] == "submitted"
            ev = tws.receive_json()
            assert ev["type"] == "submission" and ev["rank"] == i
            assert tws.receive_json()["type"] == "board"
            # 他組會收到匿名提示，先清掉避免影響後續讀取
            for j, (_, other, _) in enumerate(conns, start=1):
                if j != i:
                    assert other.receive_json()["type"] == "question_submitted"
        # 不同題目各自從 1 起算
        assert submit(conns[2][1], "2", "B")["type"] == "submitted"
        assert tws.receive_json()["rank"] == 1
        assert [(s.question_id, s.rank) for s in _subs(code)] == [("1", 1), ("1", 2), ("1", 3), ("2", 1)]
        seqs = [s.seq for s in _subs(code)]
        assert seqs == sorted(set(seqs)) and seqs[0] == 1
    finally:
        for cm, _, _ in conns:
            cm.__exit__(None, None, None)
        tcm.__exit__(None, None, None)


def test_duplicates_and_rejections_do_not_take_ranks(client, use_sheet):
    code, _ = make_started_room(client)
    c1, w1, _ = join_student(client, code, "第 1 組")
    c1b, w1b, _ = join_student(client, code, "第 1 組")
    c2, w2, _ = join_student(client, code, "第 2 組")
    try:
        submit(w1, "1", "CPU")
        w1b.receive_json()  # 同組同步
        w2.receive_json()  # 匿名提示
        first = _subs(code)[0]
        for _ in range(9):
            submit(w1, "1", "again")  # 重複
        w1b.send_json({"type": "submit", "questionId": "1", "answer": "x"})  # 同組另一視窗
        assert w1b.receive_json()["answer"] == "CPU"
        for qid, ans in [("1", ""), ("1", "字" * 501), ("99", "x")]:
            assert submit(w2, qid, ans)["type"] == "error"
        assert len(_subs(code)) == 1 and _subs(code)[0] is first
        assert (first.rank, first.seq) == (1, 1)
        assert submit(w2, "1", "GPU")["type"] == "submitted"
        assert [(s.rank, s.seq) for s in _subs(code)] == [(1, 1), (2, 2)]
    finally:
        for c in (c1, c1b, c2):
            c.__exit__(None, None, None)


def test_client_supplied_fields_ignored(client, use_sheet):
    code, _ = make_started_room(client)
    c1, w1, _ = join_student(client, code, "第 1 組")
    try:
        submit(w1, "1", "CPU", submittedAt="1999-01-01T00:00:00Z", rank=99, seq=99)
        s = _subs(code)[0]
        assert (s.rank, s.seq) == (1, 1) and s.submitted_at.year >= 2026
    finally:
        c1.__exit__(None, None, None)


def test_new_round_restarts_ranks_and_keeps_old(client, use_sheet):
    code, token = make_started_room(client)
    c1, w1, _ = join_student(client, code, "第 1 組")
    c2, w2, _ = join_student(client, code, "第 2 組")
    try:
        submit(w1, "1", "a")
        w2.receive_json()
        submit(w2, "1", "b")
        w1.receive_json()
        client.post(f"/api/rooms/{code}/phase/end", headers=auth(token))
        drain(w1, 2), drain(w2, 2)
        client.post(f"/api/rooms/{code}/phase/start", headers=auth(token))
        drain(w1, 2), drain(w2, 2)
        submit(w2, "1", "c")
        subs = _subs(code)
        assert [(s.round, s.rank, s.seq) for s in subs] == [(1, 1, 1), (1, 2, 2), (2, 1, 3)]
    finally:
        c1.__exit__(None, None, None)
        c2.__exit__(None, None, None)
