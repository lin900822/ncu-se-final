"""結果還原：重連、重整、晚加入、同組單一視窗、老師 snapshot。"""
from .conftest import assert_second_window_rejected, auth, join_student, join_student_retry, make_started_room
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
        # (a) 同組已有視窗在線：新視窗被拒絕  (c) 全新組別：可加入並還原結果
        assert_second_window_rejected(client, code, "第 1 組")
        cm, ws, joined = join_student(client, code, "第 9 組")
        try:
            assert joined["phase"] == "Ended" and joined["result"] == published
        finally:
            cm.__exit__(None, None, None)
        # (b) 同組原視窗關閉後重連：可加入並還原結果
        conns[0][0].__exit__(None, None, None)
        cm, ws, joined = join_student_retry(client, code, "第 1 組")
        try:
            assert joined["rejoined"] is True and joined["result"] == published
        finally:
            cm.__exit__(None, None, None)
    finally:
        _close(conns)


def test_offline_during_end_then_rejoin(client, use_sheet):
    code, token, conns = _play(client)
    try:
        conns[2][0].__exit__(None, None, None)  # 第 3 組離線
        _end(client, code, token)
        published = _published(conns)
        cm, ws, joined = join_student_retry(client, code, "第 3 組")
        try:
            assert joined["rejoined"] is True and joined["result"] == published
        finally:
            cm.__exit__(None, None, None)
    finally:
        _close(conns[:2])


def test_same_group_second_window_rejected_original_still_receives(client, use_sheet):
    code, token, conns = _play(client)
    try:
        assert_second_window_rejected(client, code, "第 1 組")
        _end(client, code, token)
        a = [conns[0][1].receive_json() for _ in range(2)]
        assert a[0]["type"] == "phase_changed" and a[1]["type"] == "round_result"
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
