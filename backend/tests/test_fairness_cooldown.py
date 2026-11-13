"""Step 11 US4：搶得後的冷卻限制（時間一律取後端記錄的 submitted_at）。"""
from app.normalize import normalize_group_name
from app.services import effective, results
from app.store import store

from .conftest import auth, claim, claim_bundle, close_all, make_fair_room, post_review

N = normalize_group_name
G1, G2 = "第 1 組", "第 2 組"


def _end(client, code, token):
    assert client.post(f"/api/rooms/{code}/phase/end", headers=auth(token)).status_code == 200


def _w(code):
    return {r["questionId"]: r["winnerGroup"] for r in results.build_result(store.rooms[code])["results"]}


def _st(code, unit, group):
    return effective.allocate(store.rooms[code], 1).status[(unit, N(group))]


def at(clock, conns, seconds, group, qid, answer="a"):
    clock.set(seconds)
    claim(conns, group, qid, f"{answer}-{qid}")


def test_cooldown_yields_then_expires(client, use_sheet, fake_clock):
    code, token, conns = make_fair_room(client, cooldown=30, groups=(G1, G2))
    try:
        at(fake_clock, conns, 0, G1, "1")
        at(fake_clock, conns, 10, G1, "2", "g1")
        at(fake_clock, conns, 11, G2, "2", "g2")
        at(fake_clock, conns, 50, G1, "3", "g1")
        at(fake_clock, conns, 51, G2, "3", "g2")
        _end(client, code, token)
        assert _w(code)["1"] == G1 and _w(code)["2"] == G2 and _w(code)["3"] == G1
        assert _st(code, "2", G1) == "YieldedCooldown"
    finally:
        close_all(conns)


def test_boundary_exactly_cooldown_is_eligible_but_just_under_yields(client, use_sheet, fake_clock):
    code, token, conns = make_fair_room(client, cooldown=30, groups=(G1, G2))
    try:
        at(fake_clock, conns, 0, G1, "1")
        at(fake_clock, conns, 30, G1, "2", "g1")  # 恰好 30 秒：符合資格
        at(fake_clock, conns, 59.9, G1, "3", "g1")  # 距上次取得（30 秒）29.9 秒：讓位
        at(fake_clock, conns, 60, G2, "3", "g2")
        _end(client, code, token)
        assert {q: _w(code)[q] for q in "123"} == {"1": G1, "2": G1, "3": G2}
        assert _st(code, "3", G1) == "YieldedCooldown"
    finally:
        close_all(conns)


def test_yielded_claims_do_not_restart_the_cooldown(client, use_sheet, fake_clock):
    code, token, conns = make_fair_room(client, cooldown=30, groups=(G1, G2))
    try:
        at(fake_clock, conns, 0, G1, "1")
        at(fake_clock, conns, 10, G1, "2", "g1")  # 讓位，不啟動冷卻
        at(fake_clock, conns, 11, G2, "2", "g2")
        at(fake_clock, conns, 35, G1, "3", "g1")  # 距 0 秒已 35 秒，符合資格
        _end(client, code, token)
        assert _w(code)["3"] == G1
        # 駁回 Q1 後，第 1 組不再有冷卻 → Q2 改由第 1 組取得
        post_review(client, code, token, "1", G1, "invalid", "答案錯誤")
        assert _w(code)["2"] == G1
    finally:
        close_all(conns)


def test_cap_takes_precedence_over_cooldown(client, use_sheet, fake_clock):
    code, token, conns = make_fair_room(client, win_cap=2, cooldown=30, groups=(G1, G2))
    try:
        at(fake_clock, conns, 0, G1, "1")
        at(fake_clock, conns, 40, G1, "2", "g1")
        at(fake_clock, conns, 41, G1, "3", "g1")  # 已達上限，同時在冷卻內 → 原因為上限
        at(fake_clock, conns, 42, G2, "3", "g2")
        _end(client, code, token)
        assert {q: _w(code)[q] for q in "123"} == {"1": G1, "2": G1, "3": G2}
        assert _st(code, "3", G1) == "YieldedCap"
    finally:
        close_all(conns)


def test_zero_cooldown_never_yields_for_cooldown(client, use_sheet, fake_clock):
    code, token, conns = make_fair_room(client, win_cap=2, cooldown=0, groups=(G1, G2))
    try:
        for i, q in enumerate("1234"):
            at(fake_clock, conns, i, G1, q, "g1")
        at(fake_clock, conns, 10, G2, "3", "g2")
        _end(client, code, token)
        assert "YieldedCooldown" not in set(effective.allocate(store.rooms[code], 1).status.values())
        assert _w(code)["2"] == G1 and _w(code)["3"] == G2
    finally:
        close_all(conns)


def test_client_supplied_time_is_ignored(client, use_sheet, fake_clock):
    code, token, conns = make_fair_room(client, cooldown=30, groups=(G1, G2))
    try:
        at(fake_clock, conns, 0, G1, "1")
        fake_clock.set(10)
        ws = conns[G1][1]
        ws.send_json({"type": "submit", "questionId": "2", "answer": "x", "clientTime": "2099-01-01T00:00:00Z", "submittedAt": 99999})
        from .test_submission_privacy import flush

        flush(ws)
        at(fake_clock, conns, 11, G2, "2", "g2")
        _end(client, code, token)
        assert _w(code)["2"] == G2 and _st(code, "2", G1) == "YieldedCooldown"
    finally:
        close_all(conns)


def test_bundle_win_starts_cooldown_from_its_submission_time(client, use_sheet, fake_clock):
    code, token, conns = make_fair_room(client, cooldown=30, bundles=(("3", "4"),), groups=(G1, G2))
    try:
        fake_clock.set(0)
        claim_bundle(conns, G1, "B1", {"3": "x3", "4": "x4"})
        at(fake_clock, conns, 20, G1, "1", "g1")  # 題組取得後 20 秒：讓位
        at(fake_clock, conns, 21, G2, "1", "g2")
        _end(client, code, token)
        assert _w(code)["3"] == G1 and _w(code)["1"] == G2
    finally:
        close_all(conns)


def test_kept_win_does_not_start_a_cooldown(client, use_sheet, fake_clock):
    code, token, conns = make_fair_room(client, win_cap=1, cooldown=30, groups=(G1,))
    try:
        at(fake_clock, conns, 0, G1, "1")
        at(fake_clock, conns, 5, G1, "2", "g1")  # 達上限＋冷卻：無其他人 → 保留
        _end(client, code, token)
        assert _w(code)["2"] == G1 and _st(code, "2", G1) == "Kept"
    finally:
        close_all(conns)
