"""Step 11 US2：達上限後讓位、保留、題組、審核連動、每輪重算、向下相容與確定性。"""
from app.normalize import normalize_group_name
from app.services import effective, ranking, results
from app.store import store

from .conftest import auth, claim, claim_bundle, close_all, make_fair_room, post_review

N = normalize_group_name


def _end(client, code, token):
    assert client.post(f"/api/rooms/{code}/phase/end", headers=auth(token)).status_code == 200


def _winners(code):
    return {r["questionId"]: r["winnerGroup"] for r in results.build_result(store.rooms[code])["results"]}


def _alloc(code, round_no=1):
    return effective.allocate(store.rooms[code], round_no)


def _status(alloc, unit, group):
    return alloc.status[(unit, N(group))]


G1, G2, G3 = "第 1 組", "第 2 組", "第 3 組"


def test_verification_scenario_cap_two(client, use_sheet):
    code, token, conns = make_fair_room(client, win_cap=2)
    try:
        for q in "12345":  # 第 1 組對 Q1～Q5 都最快送出
            claim(conns, G1, q, f"g1-{q}")
        claim(conns, G2, "3", "g2-3")
        claim(conns, G3, "4", "g3-4")
        _end(client, code, token)
        w = _winners(code)
        assert (w["1"], w["2"], w["3"], w["4"], w["5"]) == (G1, G1, G2, G3, G1)
        a = _alloc(code)
        assert _status(a, "3", G1) == "YieldedCap" and _status(a, "3", G2) == "Won"  # Q3 讓位給第 2 組
        assert _status(a, "4", G1) == "YieldedCap" and _status(a, "4", G3) == "Won"
        assert _status(a, "5", G1) == "Kept"  # 無其他送出者：保留，題目不懸空
        assert a.wins[N(G1)] == 3 and a.wins[N(G2)] == 1 and a.wins[N(G3)] == 1  # Kept 計入第 1 組題數
    finally:
        close_all(conns)


def test_yield_walks_down_the_ranking_to_the_first_group_below_the_cap(client, use_sheet):
    code, token, conns = make_fair_room(client, win_cap=1)
    try:
        claim(conns, G1, "1", "a")  # 第 1 組取得 Q1
        claim(conns, G2, "2", "b")  # 第 2 組取得 Q2
        for g in (G1, G2, G3):  # Q3 原始名次：第 1、2、3 組
            claim(conns, g, "3", f"{g}-3")
        _end(client, code, token)
        a = _alloc(code)
        assert _winners(code)["3"] == G3
        assert _status(a, "3", G1) == "YieldedCap" and _status(a, "3", G2) == "YieldedCap"
        assert _status(a, "3", G3) == "Won"
    finally:
        close_all(conns)


def test_cap_counts_the_two_questions_won_earliest_by_processing_order(client, use_sheet):
    code, token, conns = make_fair_room(client, win_cap=2)
    try:
        for q in ("3", "1", "2"):  # 第 1 組依 Q3、Q1、Q2 的順序送出
            claim(conns, G1, q, f"g1-{q}")
        for q in ("1", "2", "3"):
            claim(conns, G2, q, f"g2-{q}")
        _end(client, code, token)
        w = _winners(code)
        assert (w["3"], w["1"], w["2"]) == (G1, G1, G2)  # 取得的是先送出的兩題，Q2 讓位
    finally:
        close_all(conns)


def test_everyone_capped_keeps_the_best_ranked_so_no_question_is_left_empty(client, use_sheet):
    code, token, conns = make_fair_room(client, win_cap=1, groups=(G1, G2))
    try:
        claim(conns, G1, "1", "a")
        claim(conns, G2, "2", "b")
        claim(conns, G1, "3", "c")  # 兩組此時都已達上限
        claim(conns, G2, "3", "d")
        _end(client, code, token)
        a = _alloc(code)
        assert _winners(code)["3"] == G1  # 名次最前者保留
        assert _status(a, "3", G1) == "Kept" and _status(a, "3", G2) == "YieldedCap"
    finally:
        close_all(conns)


def test_review_cascade_and_restore(client, use_sheet):
    code, token, conns = make_fair_room(client, win_cap=1, groups=(G1, G2))
    try:
        claim(conns, G1, "1", "g1-1")
        claim(conns, G1, "2", "g1-2")  # 第 1 組已達上限 → Q2 讓位
        claim(conns, G2, "2", "g2-2")
        _end(client, code, token)
        before = _winners(code)
        assert (before["1"], before["2"]) == (G1, G2)
        assert post_review(client, code, token, "1", G1, "invalid", "答案錯誤").json()["changed"] is True
        after = _winners(code)  # 被駁回的送出不佔名額 → 第 1 組空出名額，Q2 改回第 1 組
        assert after["1"] is None and after["2"] == G1
        assert post_review(client, code, token, "1", G1, "valid", "誤判").json()["changed"] is True
        assert _winners(code) == before  # 恢復後回到原狀
    finally:
        close_all(conns)


def test_bundle_counts_as_its_member_count_and_may_slightly_exceed_the_cap(client, use_sheet):
    code, token, conns = make_fair_room(client, win_cap=2, bundles=(("3", "4"),))
    try:
        claim(conns, G1, "1", "a")  # 1 題
        claim_bundle(conns, G1, "B1", {"3": "x3", "4": "x4"})  # 取得前 1 < 2 → 可取得，取得後共 3 題
        claim(conns, G1, "2", "b")  # 已達上限 → 讓位
        claim(conns, G2, "2", "c")
        _end(client, code, token)
        a, w = _alloc(code), _winners(code)
        assert w["3"] == w["4"] == G1 and w["1"] == G1 and w["2"] == G2
        assert a.wins[N(G1)] == 3  # 略超過上限一次
        assert _status(a, "2", G1) == "YieldedCap"
    finally:
        close_all(conns)


def test_bundle_larger_than_the_cap_can_still_be_won(client, use_sheet):
    code, token, conns = make_fair_room(client, win_cap=1, bundles=(("3", "4"),))
    try:
        claim_bundle(conns, G1, "B1", {"3": "x3", "4": "x4"})
        claim(conns, G1, "1", "a")  # 已達上限
        claim(conns, G2, "1", "b")
        _end(client, code, token)
        w = _winners(code)
        assert w["3"] == w["4"] == G1 and w["1"] == G2
    finally:
        close_all(conns)


def test_counts_reset_every_round(client, use_sheet):
    code, token, conns = make_fair_room(client, win_cap=2)
    try:
        for q in "123":
            claim(conns, G1, q, f"r1-{q}")
        claim(conns, G2, "3", "r1-g2")
        _end(client, code, token)
        assert (_winners(code)["3"]) == G2
        assert client.post(f"/api/rooms/{code}/phase/start", headers=auth(token)).status_code == 200
        for q in "12":
            claim(conns, G1, q, f"r2-{q}")
        _end(client, code, token)
        room = store.rooms[code]
        assert room.round == 2
        a2 = effective.allocate(room, 2)
        assert a2.winners["1"].group_name == G1 and a2.winners["2"].group_name == G1  # 第二輪題數歸零
    finally:
        close_all(conns)


def test_no_rule_behaves_exactly_like_step_9(client, use_sheet):
    code, token, conns = make_fair_room(client)  # 不設規則
    try:
        for q in "12345":
            claim(conns, G1, q, f"g1-{q}")
        claim(conns, G2, "3", "g2-3")
        _end(client, code, token)
        a, w = _alloc(code), _winners(code)
        assert all(w[q] == G1 for q in "12345")  # 第 1 組全拿，沒有上限
        assert set(a.status.values()) <= {"Won", "Behind"}  # 不會出現讓位或保留
        board = ranking.build_board(store.rooms[code])
        assert {q["questionId"]: q["leader"] for q in board["questions"]}["3"] == G1
    finally:
        close_all(conns)


def test_allocation_never_modifies_submissions_and_is_deterministic(client, use_sheet):
    code, token, conns = make_fair_room(client, win_cap=1)
    try:
        for q in "123":
            claim(conns, G1, q, f"g1-{q}")
            claim(conns, G2, q, f"g2-{q}")
        _end(client, code, token)
        room = store.rooms[code]
        snap = lambda: [(s.group_name, s.question_id, s.answer, s.submitted_at, s.seq, s.rank) for s in room.submissions]  # noqa: E731
        before = snap()
        first = effective.allocate(room, 1)
        for _ in range(100):
            again = effective.allocate(room, 1)
            assert again.status == first.status and again.wins == first.wins
            assert {u: (w.seq if w else None) for u, w in again.winners.items()} == {
                u: (w.seq if w else None) for u, w in first.winners.items()
            }
        assert snap() == before  # 原始答案、時間、處理序、名次完全不變
    finally:
        close_all(conns)
