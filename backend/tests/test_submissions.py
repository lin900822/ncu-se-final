import threading
from datetime import datetime, timezone

from app.store import store

from .conftest import auth, drain, join_student, make_started_room


def submit(ws, qid, answer, **extra):
    ws.send_json({"type": "submit", "questionId": qid, "answer": answer, **extra})
    return ws.receive_json()


def _end(client, code, token):
    return client.post(f"/api/rooms/{code}/phase/end", headers=auth(token))


def _start(client, code, token):
    return client.post(f"/api/rooms/{code}/phase/start", headers=auth(token))


# ---- US1：送出、驗證、防重複 ----

def test_submit_success(client, use_sheet):
    code, _ = make_started_room(client)
    cm, ws, joined = join_student(client, code, "第 1 組")
    try:
        assert joined["phase"] == "Answering"
        m = submit(ws, "1", "CPU")
        assert m == {"type": "submitted", "questionId": "1", "answer": "CPU", "round": 1}
        subs = store.rooms[code].submissions
        assert len(subs) == 1 and subs[0].submitted_at is not None
        assert subs[0].group_name == "第 1 組" and subs[0].question_id == "1"
    finally:
        cm.__exit__(None, None, None)


def test_validation_errors_keep_connection(client, use_sheet):
    code, _ = make_started_room(client)
    cm, ws, _ = join_student(client, code, "第 1 組")
    try:
        for qid, ans, expected in [
            ("1", "", "ANSWER_EMPTY"),
            ("1", "   \n ", "ANSWER_EMPTY"),
            ("99", "x", "QUESTION_NOT_FOUND"),
            ("1", "字" * 501, "ANSWER_TOO_LONG"),
        ]:
            m = submit(ws, qid, ans)
            assert m["type"] == "error" and m["code"] == expected and m["questionId"] == qid
        assert store.rooms[code].submissions == []
        ok = submit(ws, "1", "字" * 500)  # 剛好 500 字元可送出
        assert ok["type"] == "submitted" and len(ok["answer"]) == 500
    finally:
        cm.__exit__(None, None, None)


def test_phase_gate(client, use_sheet):
    code, token = make_started_room(client, start=False)
    cm, ws, _ = join_student(client, code, "第 1 組")
    try:
        m = submit(ws, "1", "CPU")
        assert m["code"] == "PHASE_LOCKED"  # 尚未開始
        _start(client, code, token)
        drain(ws, 2)  # phase_changed + question_texts
        assert submit(ws, "1", "CPU")["type"] == "submitted"
        _end(client, code, token)
        assert ws.receive_json()["phase"] == "Ended"
        assert ws.receive_json()["type"] == "round_result"
        assert submit(ws, "2", "GPU")["code"] == "PHASE_LOCKED"  # 已結束
        assert len(store.rooms[code].submissions) == 1
    finally:
        cm.__exit__(None, None, None)


def test_duplicates_ten_times_one_record(client, use_sheet):
    code, _ = make_started_room(client)
    cm, ws, _ = join_student(client, code, "第 1 組")
    try:
        first = submit(ws, "1", "CPU")
        assert first["answer"] == "CPU"
        for i in range(9):
            dup = submit(ws, "1", f"其他答案{i}")
            assert dup["type"] == "submitted" and dup["answer"] == "CPU"  # 回既有答案
        assert len(store.rooms[code].submissions) == 1
    finally:
        cm.__exit__(None, None, None)


def test_client_time_ignored(client, use_sheet):
    code, _ = make_started_room(client)
    cm, ws, _ = join_student(client, code, "第 1 組")
    try:
        submit(ws, "1", "CPU", submittedAt="1999-01-01T00:00:00Z", submitted_at="1999-01-01")
        rec = store.rooms[code].submissions[0]
        assert rec.submitted_at.year == datetime.now(timezone.utc).year  # 伺服器時間
    finally:
        cm.__exit__(None, None, None)


def test_new_round_resets_but_keeps_history(client, use_sheet):
    code, token = make_started_room(client)
    cm, ws, _ = join_student(client, code, "第 1 組")
    try:
        submit(ws, "1", "CPU")
        _end(client, code, token)
        drain(ws, 2)  # phase_changed + round_result
        _start(client, code, token)
        drain(ws, 2)  # phase_changed(round 2) + question_texts
        m = submit(ws, "1", "新一輪")
        assert m["type"] == "submitted" and m["round"] == 2 and m["answer"] == "新一輪"
        subs = store.rooms[code].submissions
        assert [(s.round, s.answer) for s in subs] == [(1, "CPU"), (2, "新一輪")]
    finally:
        cm.__exit__(None, None, None)


def test_simultaneous_submit_from_two_windows_one_record(client, use_sheet):
    code, _ = make_started_room(client)
    c1, w1, _ = join_student(client, code, "第 1 組")
    c2, w2, _ = join_student(client, code, "第 1 組")
    try:
        barrier = threading.Barrier(2)

        def go(ws, ans):
            barrier.wait()
            ws.send_json({"type": "submit", "questionId": "2", "answer": ans})

        ts = [threading.Thread(target=go, args=(w1, "甲")), threading.Thread(target=go, args=(w2, "乙"))]
        [t.start() for t in ts]
        [t.join() for t in ts]
        r1, r2 = w1.receive_json(), w2.receive_json()
        subs = store.rooms[code].submissions
        assert len(subs) == 1
        # 兩個視窗最後看到的都是先被接受的那一筆
        assert r1["answer"] == r2["answer"] == subs[0].answer
    finally:
        c1.__exit__(None, None, None)
        c2.__exit__(None, None, None)


# ---- US4：老師端查看 ----

def _teacher(client, code, token):
    cm = client.websocket_connect(f"/ws/teacher?code={code}&token={token}")
    ws = cm.__enter__()
    return cm, ws, ws.receive_json()


def test_teacher_receives_submission_event_with_server_time(client, use_sheet):
    code, token = make_started_room(client)
    tcm, tws, _ = _teacher(client, code, token)
    cm, ws, _ = join_student(client, code, "第 1 組")
    tws.receive_json()  # group_joined
    try:
        submit(ws, "1", "CPU")
        m = tws.receive_json()
        assert set(m.keys()) == {"type", "group", "questionId", "answer", "round", "submittedAt", "rank", "bundleId"}
        assert m["type"] == "submission" and m["group"] == "第 1 組" and m["answer"] == "CPU"
        assert m["submittedAt"].endswith("Z")  # 伺服器 UTC
    finally:
        cm.__exit__(None, None, None)
        tcm.__exit__(None, None, None)


def test_snapshot_submissions_all_rounds_and_recover(client, use_sheet):
    code, token = make_started_room(client)
    cm, ws, _ = join_student(client, code, "第 1 組")
    try:
        submit(ws, "1", "CPU")
        _end(client, code, token)
        drain(ws, 2)  # phase_changed + round_result
        _start(client, code, token)
        drain(ws, 2)
        submit(ws, "1", "第二輪")
        tcm, tws, snap = _teacher(client, code, token)
        try:
            subs = snap["room"]["submissions"]
            assert [(s["round"], s["answer"]) for s in subs] == [(1, "CPU"), (2, "第二輪")]
            assert all(
                set(s.keys()) == {"group", "questionId", "answer", "round", "submittedAt", "rank", "bundleId"}
                for s in subs
            )
        finally:
            tcm.__exit__(None, None, None)
        # 以恢復碼回復後仍相同
        rec = client.post(
            "/api/rooms/recover",
            json={"recoveryCode": store.rooms[code].recovery_code},
        ).json()
        tcm2, tws2, snap2 = _teacher(client, code, rec["teacherToken"])
        try:
            assert snap2["room"]["submissions"] == subs
        finally:
            tcm2.__exit__(None, None, None)
    finally:
        cm.__exit__(None, None, None)
