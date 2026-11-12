"""Step 12 US3：累計得分排行榜（多輪、題組、保留、審核連動、並列、確定性、唯讀、規模）。"""
import time
from datetime import datetime, timedelta, timezone

from app.models import Group, Question, Room, Submission
from app.services import effective, projector
from app.store import store

from .conftest import (
    auth,
    claim,
    claim_bundle,
    close_all,
    get_projector_key,
    make_fair_room,
    post_review,
    projector_ws,
)

G1, G2, G3, G4 = "第 1 組", "第 2 組", "第 3 組", "第 4 組"


def _end(client, code, token):
    assert client.post(f"/api/rooms/{code}/phase/end", headers=auth(token)).status_code == 200


def _start(client, code, token):
    assert client.post(f"/api/rooms/{code}/phase/start", headers=auth(token)).status_code == 200


def _scores(code):
    return {r["group"]: r["score"] for r in projector.build_state(store.rooms[code])["scoreboard"]}


def test_scores_accumulate_over_settled_rounds_only(client, use_sheet):
    code, token, conns = make_fair_room(client, groups=(G1, G2))
    try:
        for q in "123":
            claim(conns, G1, q, "a")
        _end(client, code, token)
        assert _scores(code) == {G1: 3, G2: 0}
        _start(client, code, token)
        claim(conns, G1, "1", "b")
        assert _scores(code) == {G1: 3, G2: 0}  # 進行中的新一輪不計入
        claim(conns, G2, "2", "c")
        _end(client, code, token)
        assert _scores(code) == {G1: 4, G2: 1}
    finally:
        close_all(conns)


def test_each_round_uses_its_own_reviews(client, use_sheet):
    code, token, conns = make_fair_room(client, groups=(G1, G2))
    try:
        claim(conns, G1, "1", "a")
        _end(client, code, token)
        _start(client, code, token)
        claim(conns, G1, "1", "b")
        _end(client, code, token)
        assert _scores(code)[G1] == 2
        assert post_review(client, code, token, "1", G1, "invalid", "答案錯誤", round_no=2).status_code == 200
        assert _scores(code)[G1] == 1  # 只影響第 2 輪
    finally:
        close_all(conns)


def test_bundle_counts_n_and_kept_counts(client, use_sheet):
    code, token, conns = make_fair_room(client, bundles=(("3", "4"),), groups=(G1, G2))
    try:
        claim_bundle(conns, G1, "B1", {"3": "x", "4": "y"})
        claim(conns, G1, "1", "a")
        _end(client, code, token)
        assert _scores(code)[G1] == 3  # 題組 2 題 + 單題 1 題
    finally:
        close_all(conns)
    code, token, conns = make_fair_room(client, win_cap=1, groups=(G1,))
    try:
        claim(conns, G1, "1", "a")
        claim(conns, G1, "2", "b")  # 已達上限但無人可遞補 → 保留，仍計分
        _end(client, code, token)
        assert _scores(code)[G1] == 2
        alloc = effective.allocate(store.rooms[code], 1)
        assert alloc.wins[next(iter(alloc.wins))] == 2
    finally:
        close_all(conns)


def test_review_and_fairness_rebalance_scores(client, use_sheet):
    code, token, conns = make_fair_room(client, win_cap=1, groups=(G1, G2))
    try:
        claim(conns, G1, "1", "a")
        claim(conns, G1, "2", "b")  # 達上限 → 讓位
        claim(conns, G2, "2", "c")
        _end(client, code, token)
        assert _scores(code) == {G1: 1, G2: 1}
        post_review(client, code, token, "1", G1, "invalid", "答案錯誤")
        assert _scores(code) == {G1: 1, G2: 0}  # 第 1 組空出名額，Q2 改回第 1 組
        post_review(client, code, token, "1", G1, "valid", "誤判")
        assert _scores(code) == {G1: 1, G2: 1}
    finally:
        close_all(conns)


def test_ties_share_rank_and_order_is_stable(client, use_sheet):
    code, token, conns = make_fair_room(client, groups=(G1, G2, G3, G4))
    try:
        claim(conns, G2, "3", "a")
        claim(conns, G2, "4", "a")
        claim(conns, G1, "1", "a")
        claim(conns, G1, "2", "a")
        claim(conns, G3, "5", "a")
        _end(client, code, token)
        rows = projector.build_state(store.rooms[code])["scoreboard"]
        assert [(r["group"], r["score"], r["rank"]) for r in rows] == [
            (G1, 2, 1), (G2, 2, 1), (G3, 1, 3), (G4, 0, 4),
        ]  # 同分以組名排序；0 分也列出
    finally:
        close_all(conns)


def test_deterministic_and_read_only(client, use_sheet):
    code, token, conns = make_fair_room(client, win_cap=2, groups=(G1, G2))
    try:
        for q in "1234":
            claim(conns, G1, q, "a")
            claim(conns, G2, q, "b")
        _end(client, code, token)
        room = store.rooms[code]

        def snap():
            return (
                [(s.group_name, s.question_id, s.answer, s.seq, s.rank, s.submitted_at) for s in room.submissions],
                list(room.reviews), list(room.phase_log), sorted(room.groups), room.round, room.phase,
            )

        before = snap()
        first = projector.build_state(room)
        for _ in range(100):
            assert projector.build_state(room) == first
        assert snap() == before
    finally:
        close_all(conns)


def _big_room():
    t0 = datetime(2026, 1, 1, tzinfo=timezone.utc)
    room = Room(code="BIG", created_at=t0, last_activity_at=t0, teacher_token="t", recovery_code="r", projector_key="k")
    room.questions = [Question(id=str(i), number=i, sub=None, label=f"Q{i}", cell="A1") for i in range(1, 31)]
    for g in range(20):
        name = f"第 {g + 1} 組"
        room.groups[name] = Group(name, name, True, t0 + timedelta(seconds=g))
    seq = 0
    for rnd in (1, 2, 3):
        for q in range(1, 31):
            for g in range(20):
                seq += 1
                name = f"第 {g + 1} 組"
                room.submissions.append(Submission(name, name, str(q), rnd, "a", t0 + timedelta(seconds=seq), seq, g + 1))
    room.round, room.phase = 3, "Ended"
    return room


def test_scale_30_questions_20_groups_3_rounds(client):
    room = _big_room()
    t = time.perf_counter()
    state = projector.build_state(room)
    assert time.perf_counter() - t < 0.2
    assert sum(r["score"] for r in state["scoreboard"]) == 90  # 3 輪 × 30 題，每題恰有一個得主


def test_twenty_projectors_receive_a_broadcast_quickly(client, use_sheet):
    code, token, conns = make_fair_room(client, start=False, groups=(G1,))
    key = get_projector_key(client, code, token)
    ps = [projector_ws(client, code, key) for _ in range(20)]
    try:
        t = time.perf_counter()
        _start(client, code, token)
        for _cm, ws, _ in ps:
            assert ws.receive_json()["phase"] == "Answering"
        assert time.perf_counter() - t < 1.0
    finally:
        for cm, _ws, _ in ps:
            cm.__exit__(None, None, None)
        close_all(conns)
