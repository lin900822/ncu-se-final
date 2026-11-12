"""Step 12 US3：結算後的得主看板內容、與學生／老師結果一致、審核即時更新、階段切換、無題目房間。"""
import json

from app.services import projector
from app.store import store

from .conftest import (
    auth,
    claim,
    claim_bundle,
    close_all,
    get_projector_key,
    join_student,
    make_fair_room,
    post_review,
    projector_ws,
    projector_until,
)

G1, G2, G3 = "第 1 組", "第 2 組", "第 3 組"
FORBIDDEN = ["seq", "submittedAt", "outcome", "Yielded", "Kept", "Behind", "reason", "successionRank"]


def _end(client, code, token):
    assert client.post(f"/api/rooms/{code}/phase/end", headers=auth(token)).status_code == 200


def _student_result(ws):
    while True:
        m = ws.receive_json()
        if m["type"] == "round_result":
            return {"round": m["round"], "results": m["results"]}


def _scenario(client, **kw):
    code, token, conns = make_fair_room(client, bundles=(("3", "4"),), **kw)
    claim(conns, G1, "1", "g1-1")
    claim(conns, G2, "1", "g2-1")
    claim_bundle(conns, G2, "B1", {"3": "g2-3", "4": "g2-4"})
    claim(conns, G3, "5", "g3-5")
    return code, token, conns


def test_ended_result_equals_student_and_teacher_results(client, use_sheet):
    code, token, conns = _scenario(client)
    key = get_projector_key(client, code, token)
    cm, ws, _ = projector_ws(client, code, key)
    try:
        _end(client, code, token)
        state, _ = projector_until(ws, lambda m: m.get("phase") == "Ended")
        student = _student_result(conns[G1][1])
        with client.websocket_connect(f"/ws/teacher?token={token}&code={code}") as t:
            teacher = t.receive_json()["room"]["result"]
        assert state["result"] == student == teacher  # SC-002：逐題完全相等
        by_q = {r["questionId"]: r for r in state["result"]["results"]}
        assert by_q["3"]["winnerGroup"] == by_q["4"]["winnerGroup"] == G2  # 題組整組
        assert by_q["2"]["winnerGroup"] is None and by_q["6"]["winnerGroup"] is None  # 無人搶答
        text = json.dumps({k: v for k, v in state.items() if k != "scoreboard"}, ensure_ascii=False)
        for word in FORBIDDEN:
            assert word not in text, word
        assert state["progress"] is None and state["submitted"] is None
    finally:
        cm.__exit__(None, None, None)
        close_all(conns)


def test_review_updates_projector_and_matches_students(client, use_sheet):
    code, token, conns = _scenario(client)
    key = get_projector_key(client, code, token)
    cm, ws, _ = projector_ws(client, code, key)
    try:
        _end(client, code, token)
        projector_until(ws, lambda m: m.get("phase") == "Ended")
        assert post_review(client, code, token, "1", G1, "invalid", "答案錯誤").status_code == 200
        state = ws.receive_json()
        by_q = {r["questionId"]: r for r in state["result"]["results"]}
        assert by_q["1"]["winnerGroup"] == G2  # 次順位遞補
        assert {r["group"]: r["score"] for r in state["scoreboard"]}[G2] == 3  # Q1 + 題組 2 題
        # 全被駁回：noValid
        assert post_review(client, code, token, "5", G3, "invalid", "亂填").status_code == 200
        state = ws.receive_json()
        item = next(r for r in state["result"]["results"] if r["questionId"] == "5")
        assert item["winnerGroup"] is None and item.get("noValid") is True
        assert "亂填" not in json.dumps(state, ensure_ascii=False)  # 不含理由
        from .test_submission_privacy import flush

        latest = [m for m in flush(conns[G1][1]) if m["type"] == "round_result"][-1]
        assert latest["results"] == state["result"]["results"]  # 學生最新結果與投影逐題相同
    finally:
        cm.__exit__(None, None, None)
        close_all(conns)


def test_fairness_yield_is_reflected(client, use_sheet):
    code, token, conns = make_fair_room(client, win_cap=1, groups=(G1, G2))
    key = get_projector_key(client, code, token)
    cm, ws, _ = projector_ws(client, code, key)
    try:
        claim(conns, G1, "1", "a")
        claim(conns, G1, "2", "b")
        claim(conns, G2, "2", "c")
        _end(client, code, token)
        state, _ = projector_until(ws, lambda m: m.get("phase") == "Ended")
        by_q = {r["questionId"]: r["winnerGroup"] for r in state["result"]["results"]}
        assert by_q["1"] == G1 and by_q["2"] == G2
        assert {r["group"]: r["score"] for r in state["scoreboard"]} == {G1: 1, G2: 1}
    finally:
        cm.__exit__(None, None, None)
        close_all(conns)


def test_next_round_returns_to_anonymous_progress_but_keeps_cumulative_scores(client, use_sheet):
    code, token, conns = make_fair_room(client, groups=(G1, G2))
    key = get_projector_key(client, code, token)
    cm, ws, _ = projector_ws(client, code, key)
    try:
        claim(conns, G1, "1", "a")
        _end(client, code, token)
        projector_until(ws, lambda m: m.get("phase") == "Ended")
        assert client.post(f"/api/rooms/{code}/phase/start", headers=auth(token)).status_code == 200
        state, _ = projector_until(ws, lambda m: m["type"] == "projector_state" and m["phase"] == "Answering")
        assert state["result"] is None and state["progress"]["answered"] == 0
        assert {r["group"]: r["score"] for r in state["scoreboard"]} == {G1: 1, G2: 0}
    finally:
        cm.__exit__(None, None, None)
        close_all(conns)


def test_room_without_questions(client):
    r = client.post("/api/rooms")
    assert r.status_code == 201
    code, token = r.json()["code"], r.json()["teacherToken"]
    key = get_projector_key(client, code, token)
    cm, ws, first = projector_ws(client, code, key)
    try:
        assert first["questions"] == [] and first["bundles"] == [] and first["scoreboard"] == []
        scm, _sws, _ = join_student(client, code, G1)
        assert ws.receive_json()["groups"] == [G1]
        assert client.post(f"/api/rooms/{code}/phase/start", headers=auth(token)).status_code == 200
        started, _ = projector_until(ws, lambda m: m["type"] == "projector_state" and m["phase"] == "Answering")
        assert started["progress"] == {"answered": 0, "total": 0} and started["submitted"] == {}
        _end(client, code, token)
        ended, _ = projector_until(ws, lambda m: m.get("phase") == "Ended")
        assert ended["result"]["results"] == [] and ended["scoreboard"] == [{"group": G1, "score": 0, "rank": 1}]
        scm.__exit__(None, None, None)
    finally:
        cm.__exit__(None, None, None)


def test_reconnect_restores_the_same_whole_state(client, use_sheet):
    code, token, conns = _scenario(client)
    key = get_projector_key(client, code, token)
    cm, ws, first = projector_ws(client, code, key)
    cm.__exit__(None, None, None)
    cm2, _w2, second = projector_ws(client, code, key)
    try:
        assert second == first == projector.build_state(store.rooms[code])
    finally:
        cm2.__exit__(None, None, None)
        close_all(conns)
