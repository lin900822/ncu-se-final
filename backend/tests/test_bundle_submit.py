"""Step 7 US2：題組整組一次送出（全有或全無、去重、單題拒絕、新一輪）。"""
import pytest

from app.store import store

from .conftest import auth, join_student, make_bundle_room


def _bundle(answers, bundle_id="B1"):
    return {"type": "submit_bundle", "bundleId": bundle_id, "answers": answers}


def test_bundle_submit_records_each_member_with_shared_rank(client, use_sheet):
    code, _, _ = make_bundle_room(client)
    cm, ws, _ = join_student(client, code, "第 1 組")
    try:
        ws.send_json(_bundle({"3": "CPU", "4": "記憶體"}))
        msg = ws.receive_json()
        assert msg == {
            "type": "bundle_submitted",
            "bundleId": "B1",
            "answers": {"3": "CPU", "4": "記憶體"},
            "round": 1,
        }
        subs = store.rooms[code].submissions
        assert [s.question_id for s in subs] == ["3", "4"]
        assert [s.answer for s in subs] == ["CPU", "記憶體"]
        assert all(s.bundle_id == "B1" for s in subs)
        assert subs[0].seq == subs[1].seq
        assert subs[0].submitted_at == subs[1].submitted_at
        assert subs[0].rank == subs[1].rank == 1
    finally:
        cm.__exit__(None, None, None)


@pytest.mark.parametrize(
    "answers, code, bad",
    [
        ({"3": "CPU", "4": ""}, "BUNDLE_INCOMPLETE", ["4"]),
        ({"3": "CPU", "4": "   "}, "BUNDLE_INCOMPLETE", ["4"]),
        ({"3": "CPU"}, "BUNDLE_INCOMPLETE", ["4"]),
        ({"3": "CPU", "4": "RAM", "5": "x"}, "BUNDLE_INCOMPLETE", ["5"]),
        ({"3": "CPU", "4": "x" * 501}, "ANSWER_TOO_LONG", ["4"]),
    ],
)
def test_all_or_nothing(client, use_sheet, answers, code, bad):
    room_code, _, _ = make_bundle_room(client)
    room = store.rooms[room_code]
    seq_before = room.next_seq
    cm, ws, _ = join_student(client, room_code, "第 1 組")
    try:
        ws.send_json(_bundle(answers))
        e = ws.receive_json()
        assert e["type"] == "error" and e["code"] == code
        assert e["bundleId"] == "B1"
        assert e["details"]["questionIds"] == bad
        assert room.submissions == [] and room.next_seq == seq_before
        # 連線不關閉：之後仍可正常送出
        ws.send_json(_bundle({"3": "CPU", "4": "RAM"}))
        assert ws.receive_json()["type"] == "bundle_submitted"
    finally:
        cm.__exit__(None, None, None)


def test_unknown_bundle(client, use_sheet):
    code, _, _ = make_bundle_room(client)
    cm, ws, _ = join_student(client, code, "第 1 組")
    try:
        ws.send_json(_bundle({"3": "a", "4": "b"}, bundle_id="B9"))
        e = ws.receive_json()
        assert e["code"] == "BUNDLE_NOT_FOUND" and e["bundleId"] == "B9"
        assert store.rooms[code].submissions == []
    finally:
        cm.__exit__(None, None, None)


def test_phase_locked_before_start(client, use_sheet):
    code, _, _ = make_bundle_room(client, start=False)
    cm, ws, _ = join_student(client, code, "第 1 組")
    try:
        ws.send_json(_bundle({"3": "a", "4": "b"}))
        assert ws.receive_json()["code"] == "PHASE_LOCKED"
        assert store.rooms[code].submissions == []
    finally:
        cm.__exit__(None, None, None)


def test_single_submit_of_bundle_member_rejected(client, use_sheet):
    code, _, _ = make_bundle_room(client)
    cm, ws, _ = join_student(client, code, "第 1 組")
    try:
        ws.send_json({"type": "submit", "questionId": "3", "answer": "x"})
        e = ws.receive_json()
        assert e["code"] == "QUESTION_IN_BUNDLE" and e["questionId"] == "3"
        assert store.rooms[code].submissions == []
        # 未綁定題目照常送出，名次不受題組影響
        ws.send_json({"type": "submit", "questionId": "1", "answer": "ok"})
        assert ws.receive_json()["type"] == "submitted"
        ws.send_json(_bundle({"3": "a", "4": "b"}))
        assert ws.receive_json()["type"] == "bundle_submitted"
        ranks = {s.question_id: s.rank for s in store.rooms[code].submissions}
        assert ranks == {"1": 1, "3": 1, "4": 1}
    finally:
        cm.__exit__(None, None, None)


def test_duplicate_returns_existing(client, use_sheet):
    code, _, _ = make_bundle_room(client)
    cm, ws, _ = join_student(client, code, "第 1 組")
    try:
        ws.send_json(_bundle({"3": "first", "4": "first"}))
        assert ws.receive_json()["answers"] == {"3": "first", "4": "first"}
        ws.send_json(_bundle({"3": "second", "4": "second"}))
        again = ws.receive_json()
        assert again["type"] == "bundle_submitted"
        assert again["answers"] == {"3": "first", "4": "first"}
        assert len(store.rooms[code].submissions) == 2
    finally:
        cm.__exit__(None, None, None)


def test_new_round_allows_resubmit(client, use_sheet):
    code, token, _ = make_bundle_room(client)
    cm, ws, _ = join_student(client, code, "第 1 組")
    try:
        ws.send_json(_bundle({"3": "r1", "4": "r1"}))
        assert ws.receive_json()["type"] == "bundle_submitted"
        assert client.post(f"/api/rooms/{code}/phase/end", headers=auth(token)).status_code == 200
        assert client.post(f"/api/rooms/{code}/phase/start", headers=auth(token)).status_code == 200
        # 讀掉階段與結果等事件，直到能送出
        ws.send_json(_bundle({"3": "r2", "4": "r2"}))
        while True:
            m = ws.receive_json()
            if m["type"] == "bundle_submitted":
                break
        assert m["round"] == 2 and m["answers"] == {"3": "r2", "4": "r2"}
        subs = store.rooms[code].submissions
        assert len(subs) == 4  # 舊輪保留
        assert [s.rank for s in subs if s.round == 2] == [1, 1]
    finally:
        cm.__exit__(None, None, None)
