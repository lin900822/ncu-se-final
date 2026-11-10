from app.store import store

from .conftest import auth, create_room, join_student

PHASE_KEYS = {"type", "phase", "round", "changedAt"}


def start(client, code, token):
    return client.post(f"/api/rooms/{code}/phase/start", headers=auth(token))


def end(client, code, token):
    return client.post(f"/api/rooms/{code}/phase/end", headers=auth(token))


def teacher_ws(client, code, token):
    cm = client.websocket_connect(f"/ws/teacher?code={code}&token={token}")
    ws = cm.__enter__()
    snap = ws.receive_json()
    return cm, ws, snap


# ---- US1：初始等待且鎖定 ----

def test_initial_phase_waiting_and_submit_locked(client):
    code, _ = create_room(client)
    cm, ws, joined = join_student(client, code, "第 1 組")
    try:
        assert joined["type"] == "joined"
        assert joined["phase"] == "Waiting"
        assert joined["round"] == 0
        ws.send_json({"type": "submit"})
        err = ws.receive_json()
        assert err["type"] == "error" and err["code"] == "PHASE_LOCKED"
        # 連線仍開啟：再送一次仍得到回應
        ws.send_json({"type": "submit"})
        assert ws.receive_json()["code"] == "PHASE_LOCKED"
    finally:
        cm.__exit__(None, None, None)


# ---- US2：開始搶答 ----

def test_start_broadcasts_only_phase_info(client):
    code, token = create_room(client)
    tcm, tws, snap = teacher_ws(client, code, token)
    assert snap["room"]["phase"] == "Waiting"
    c1, w1, _ = join_student(client, code, "第 1 組")
    tws.receive_json()  # group_joined
    c2, w2, _ = join_student(client, code, "第 2 組")
    tws.receive_json()
    try:
        r = start(client, code, token)
        assert r.status_code == 200
        assert r.json() == {"phase": "Answering", "round": 1, "changed": True}
        for ws in (tws, w1, w2):
            m = ws.receive_json()
            assert set(m.keys()) == PHASE_KEYS  # 不含任何組別資料（原則 III）
            assert m["phase"] == "Answering" and m["round"] == 1
        # 冪等：重複 start 不改變、不廣播
        r2 = start(client, code, token)
        assert r2.json()["changed"] is False
        assert len(store.rooms[code].phase_log) == 1
    finally:
        for cm in (c1, c2, tcm):
            cm.__exit__(None, None, None)


def test_start_requires_teacher_token(client):
    code, token = create_room(client)
    assert client.post(f"/api/rooms/{code}/phase/start").status_code == 401
    assert start(client, code, "wrong").status_code == 401
    assert store.rooms[code].phase == "Waiting"


def test_start_without_any_group_then_late_joiner_unlocked(client):
    code, token = create_room(client)
    assert start(client, code, token).json()["phase"] == "Answering"
    cm, ws, joined = join_student(client, code, "第 1 組")
    try:
        assert joined["phase"] == "Answering" and joined["round"] == 1
    finally:
        cm.__exit__(None, None, None)


# ---- US3：結束搶答 ----

def test_end_locks_and_rounds_and_log(client):
    code, token = create_room(client)
    cm, ws, _ = join_student(client, code, "第 1 組")
    try:
        start(client, code, token)
        assert ws.receive_json()["phase"] == "Answering"
        r = end(client, code, token)
        assert r.json() == {"phase": "Ended", "round": 1, "changed": True}
        m = ws.receive_json()
        assert set(m.keys()) == PHASE_KEYS and m["phase"] == "Ended"
        assert ws.receive_json()["type"] == "round_result"  # Step 6：結算公布
        ws.send_json({"type": "submit"})
        assert ws.receive_json()["code"] == "PHASE_LOCKED"
        # 冪等
        assert end(client, code, token).json()["changed"] is False
        # 再開始 → round 2
        assert start(client, code, token).json()["round"] == 2
        log = store.rooms[code].phase_log
        assert [(c.phase, c.round) for c in log] == [
            ("Answering", 1),
            ("Ended", 1),
            ("Answering", 2),
        ]
        assert all(c.changed_at is not None for c in log)
    finally:
        cm.__exit__(None, None, None)


def test_end_when_waiting_is_noop(client):
    code, token = create_room(client)
    r = end(client, code, token)
    assert r.status_code == 200
    assert r.json() == {"phase": "Waiting", "round": 0, "changed": False}
    assert store.rooms[code].phase_log == []


# ---- US4：重連還原 ----

def test_rejoin_gets_current_phase(client):
    code, token = create_room(client)
    cm, ws, _ = join_student(client, code, "第 1 組")
    start(client, code, token)
    cm.__exit__(None, None, None)
    # 離線期間結束
    end(client, code, token)
    cm2, ws2, joined = join_student(client, code, "第 1 組")
    try:
        assert joined["rejoined"] is True
        assert joined["phase"] == "Ended" and joined["round"] == 1
    finally:
        cm2.__exit__(None, None, None)


def test_teacher_snapshot_has_phase(client):
    code, token = create_room(client)
    start(client, code, token)
    cm, ws, snap = teacher_ws(client, code, token)
    try:
        assert snap["room"]["phase"] == "Answering"
        assert snap["room"]["round"] == 1
    finally:
        cm.__exit__(None, None, None)


def test_closed_room_rejects_phase_ops(client):
    code, token = create_room(client)
    cm, ws, _ = join_student(client, code, "第 1 組")
    try:
        client.post(f"/api/rooms/{code}/close", headers=auth(token))
        assert ws.receive_json()["type"] == "room_closed"
    finally:
        cm.__exit__(None, None, None)
    r = start(client, code, token)
    assert r.status_code == 409 and r.json()["error"]["code"] == "ROOM_CLOSED"
    assert end(client, code, token).status_code == 409


# ---- SC-002 / SC-003：40 組廣播 ----

def test_broadcast_reaches_40_groups_within_2_seconds(client):
    import time

    code, token = create_room(client)
    conns = [join_student(client, code, f"第 {i} 組") for i in range(1, 41)]
    try:
        t0 = time.monotonic()
        assert start(client, code, token).status_code == 200
        for _, ws, _ in conns:
            m = ws.receive_json()
            assert m["type"] == "phase_changed" and m["phase"] == "Answering"
        assert time.monotonic() - t0 < 2
        t1 = time.monotonic()
        assert end(client, code, token).status_code == 200
        for _, ws, _ in conns:
            m = ws.receive_json()
            assert m["type"] == "phase_changed" and m["phase"] == "Ended"
        assert time.monotonic() - t1 < 2
    finally:
        for cm, _, _ in conns:
            cm.__exit__(None, None, None)
