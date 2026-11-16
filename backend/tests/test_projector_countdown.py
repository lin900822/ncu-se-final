"""Step 12 US2：倒數事件只在實際開始搶答時送一次，不補播，不影響階段時序。"""
import json

from .conftest import auth, get_projector_key, join_student, make_fair_room, projector_ws, take_projector

G1 = "第 1 組"


def _start(client, code, token):
    r = client.post(f"/api/rooms/{code}/phase/start", headers=auth(token))
    assert r.status_code == 200
    return r.json()


def _end(client, code, token):
    assert client.post(f"/api/rooms/{code}/phase/end", headers=auth(token)).status_code == 200


def test_countdown_follows_the_answering_state(client, use_sheet):
    code, token, conns = make_fair_room(client, start=False)
    key = get_projector_key(client, code, token)
    cm, ws, first = projector_ws(client, code, key)
    try:
        assert first["phase"] == "Waiting"
        _start(client, code, token)
        state, countdown = take_projector(ws, 2)
        assert state["type"] == "projector_state" and state["phase"] == "Answering" and state["round"] == 1
        assert state["progress"] == {"answered": 0, "total": 6}
        assert countdown == {"type": "countdown", "round": 1}  # 狀態在前、倒數在後
    finally:
        cm.__exit__(None, None, None)
        for c, _w in conns.values():
            c.__exit__(None, None, None)


def test_idempotent_start_does_not_replay(client, use_sheet):
    code, token, conns = make_fair_room(client, start=False)
    key = get_projector_key(client, code, token)
    cm, ws, _ = projector_ws(client, code, key)
    try:
        assert _start(client, code, token)["changed"] is True
        take_projector(ws, 2)
        assert _start(client, code, token)["changed"] is False  # 冪等：不重送
        _end(client, code, token)
        msg = ws.receive_json()  # 下一則直接是結算狀態，而不是 countdown
        assert msg["type"] == "projector_state" and msg["phase"] == "Ended"
    finally:
        cm.__exit__(None, None, None)
        for c, _w in conns.values():
            c.__exit__(None, None, None)


def test_late_and_reconnecting_projectors_never_get_countdown(client, use_sheet):
    code, token, conns = make_fair_room(client, start=False)
    key = get_projector_key(client, code, token)
    try:
        _start(client, code, token)
        cm, ws, first = projector_ws(client, code, key)  # 開始之後才連線
        assert first["type"] == "projector_state" and first["phase"] == "Answering"
        cm.__exit__(None, None, None)
        cm2, ws2, again = projector_ws(client, code, key)  # 重新連線
        assert again["type"] == "projector_state"
        # 之後的第一則是新事件（新組別加入的名單），不是倒數
        c3, _w3, _ = join_student(client, code, "第 7 組")
        nxt = ws2.receive_json()
        assert nxt["type"] == "projector_state" and "第 7 組" in nxt["groups"]
        c3.__exit__(None, None, None)
        cm2.__exit__(None, None, None)
    finally:
        for c, _w in conns.values():
            c.__exit__(None, None, None)


def test_second_round_counts_down_again_and_clears_progress(client, use_sheet):
    from .conftest import claim

    code, token, conns = make_fair_room(client, start=False)
    key = get_projector_key(client, code, token)
    cm, ws, _ = projector_ws(client, code, key)
    try:
        _start(client, code, token)
        take_projector(ws, 2)
        claim(conns, G1, "1", "a")
        assert ws.receive_json()["progress"]["answered"] == 1
        _end(client, code, token)
        assert ws.receive_json()["phase"] == "Ended"
        _start(client, code, token)
        state, countdown = take_projector(ws, 2)
        assert countdown == {"type": "countdown", "round": 2}
        assert state["round"] == 2 and state["progress"]["answered"] == 0
    finally:
        cm.__exit__(None, None, None)
        for c, _w in conns.values():
            c.__exit__(None, None, None)


def test_stage_timing_for_students_and_teacher_is_unchanged(client, use_sheet):
    code, token, conns = make_fair_room(client, start=False)
    key = get_projector_key(client, code, token)
    cm, pws, _ = projector_ws(client, code, key)
    try:
        with client.websocket_connect(f"/ws/teacher?token={token}&code={code}") as t:
            t.receive_json()
            _start(client, code, token)
            t_msgs = [t.receive_json() for _ in range(3)]  # phase_changed、question_texts、board
            assert [m["type"] for m in t_msgs] == ["phase_changed", "question_texts", "board"]
        from .test_submission_privacy import flush

        s_msgs = flush(conns[G1][1])
        assert [m["type"] for m in s_msgs] == ["phase_changed", "question_texts"]
        # 學生在倒數事件之後立即可送出，名次與處理序不受影響
        from .conftest import claim

        claim(conns, G1, "1", "a")
        from app.store import store

        sub = store.rooms[code].submissions[0]
        assert (sub.rank, sub.seq) == (1, 1)
        text = json.dumps(s_msgs + t_msgs, ensure_ascii=False)
        assert "countdown" not in text and "projector_state" not in text
    finally:
        cm.__exit__(None, None, None)
        for c, _w in conns.values():
            c.__exit__(None, None, None)
