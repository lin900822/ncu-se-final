"""結果還原：重連、重整、晚加入、同組多視窗、老師 snapshot。"""
from .conftest import auth, join_student, make_started_room
from .test_results import _close, _end, _play, _teacher


def _published(conns):
    ws = conns[0][1]
    assert ws.receive_json()["type"] == "phase_changed"
    m = ws.receive_json()
    return {"round": m["round"], "results": m["results"]}


def test_rejoin_after_end_restores_result(client, use_sheet):
    code, token, conns = _play(client)
    try:
        _end(client, code, token)
        published = _published(conns)
        # (a) 同組新視窗  (c) 全新組別
        for name in ("第 1 組", "第 9 組"):
            cm, ws, joined = join_student(client, code, name)
            try:
                assert joined["phase"] == "Ended" and joined["result"] == published
            finally:
                cm.__exit__(None, None, None)
    finally:
        _close(conns)


def test_offline_during_end_then_rejoin(client, use_sheet):
    code, token, conns = _play(client)
    try:
        conns[3][0].__exit__(None, None, None)  # 第 3 組離線
        _end(client, code, token)
        published = _published(conns)
        cm, ws, joined = join_student(client, code, "第 3 組")
        try:
            assert joined["rejoined"] is True and joined["result"] == published
        finally:
            cm.__exit__(None, None, None)
    finally:
        _close(conns[:3])


def test_same_group_windows_both_receive(client, use_sheet):
    code, token, conns = _play(client)
    try:
        _end(client, code, token)
        a = [conns[0][1].receive_json() for _ in range(2)]
        b = [conns[1][1].receive_json() for _ in range(2)]
        assert a == b and a[1]["type"] == "round_result"
    finally:
        _close(conns)


def test_result_none_before_end(client, use_sheet):
    code, token = make_started_room(client, start=False)
    cm, ws, joined = join_student(client, code, "第 1 組")  # Waiting
    try:
        assert joined["result"] is None
    finally:
        cm.__exit__(None, None, None)
    client.post(f"/api/rooms/{code}/phase/start", headers=auth(token))
    cm, ws, joined = join_student(client, code, "第 2 組")  # Answering
    try:
        assert joined["result"] is None
    finally:
        cm.__exit__(None, None, None)


def test_teacher_snapshot_and_recover(client, use_sheet, ):
    from app.store import store

    code, token, conns = _play(client)
    try:
        _end(client, code, token)
        published = _published(conns)
        rec = client.post(
            "/api/rooms/recover", json={"recoveryCode": store.rooms[code].recovery_code}
        ).json()
        tcm, tws, snap = _teacher(client, code, rec["teacherToken"])
        try:
            assert snap["room"]["result"] == published
        finally:
            tcm.__exit__(None, None, None)
    finally:
        _close(conns)
