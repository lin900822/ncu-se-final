"""Step 11 US3：結算結果、看板、匯出、回填的一致性，即時更新、保密與審核連動提示。"""
import json

from app.store import store

from .conftest import (
    auth,
    claim,
    claim_bundle,
    close_all,
    get_export,
    make_fair_room,
    parse_csv,
    post_backfill,
    post_review,
)

G1, G2, G3 = "第 1 組", "第 2 組", "第 3 組"
SECRET_WORDS = ["outcome", "YieldedCap", "YieldedCooldown", "Kept", "Behind", "changedUnits", "board", "leadTally", "winCounts"]


def _scenario(client, **kw):
    """驗證效果情境：第 1 組最快送 Q1～Q5，第 2 組送 Q3，第 3 組送 Q4。回傳 (code, token, conns, student_msgs)。"""
    code, token, conns = make_fair_room(client, win_cap=2, **kw)
    msgs = {g: [] for g in conns}
    for q in "12345":
        msgs[G1] += claim(conns, G1, q, f"g1-{q}")
    msgs[G2] += claim(conns, G2, "3", "g2-3")
    msgs[G3] += claim(conns, G3, "4", "g3-4")
    return code, token, conns, msgs


def _end(client, code, token):
    assert client.post(f"/api/rooms/{code}/phase/end", headers=auth(token)).status_code == 200


def _teacher_snapshot(client, code, token):
    with client.websocket_connect(f"/ws/teacher?token={token}&code={code}") as t:
        return t.receive_json()["room"]


def test_every_surface_agrees_on_each_winner(client, fake_sheet):
    code, token, conns, _ = _scenario(client)
    try:
        _end(client, code, token)
        room = _teacher_snapshot(client, code, token)
        expect = {r["questionId"]: (r["winnerGroup"], r["answer"]) for r in room["result"]["results"]}
        assert expect["3"][0] == G2 and expect["4"][0] == G3 and expect["1"][0] == G1
        # 看板 leader
        assert {q["questionId"]: q["leader"] for q in room["board"]["questions"]} == {k: v[0] for k, v in expect.items()}
        # leadTally 與逐題贏家一致
        tally = {}
        for g, _a in expect.values():
            if g:
                tally[g] = tally.get(g, 0) + 1
        assert {t["group"]: t["leadCount"] for t in room["board"]["leadTally"]} == tally
        # 學生端結算 round_result 與老師的逐題結果一致
        for _g, (_cm, ws) in conns.items():
            m = _wait(ws, "round_result")
            assert {r["questionId"]: (r["winnerGroup"], r["answer"]) for r in m["results"]} == expect
    finally:
        close_all(conns)


def test_export_and_backfill_follow_the_same_winners(client, fake_sheet):
    code, token, conns, _ = _scenario(client)
    try:
        _end(client, code, token)
        expect = {
            r["questionId"]: r["answer"]
            for r in _teacher_snapshot(client, code, token)["result"]["results"]
        }
        rows = parse_csv(get_export(client, code, token))
        assert rows[0][-2:] == ["獲勝狀態", "未獲勝原因"]
        wins = {(r[1], r[3]): r[11] for r in rows[1:]}
        assert wins[("Q3", G2)] == "獲勝" and wins[("Q3", G1)] == "未獲勝"
        assert wins[("Q4", G3)] == "獲勝" and wins[("Q4", G1)] == "未獲勝"
        assert wins[("Q5", G1)] == "獲勝"  # Kept
        winner_answers = {a for a in expect.values() if a}
        r = post_backfill(client, code, token)
        assert r.status_code == 200, r.json()
        cells = {c for row in fake_sheet.snapshot() for c in row}
        assert winner_answers <= cells
        assert not ({"g1-3", "g1-4"} & cells)  # 讓位者的答案不寫入
    finally:
        close_all(conns)


def test_board_fields_and_lead_counts(client, use_sheet):
    code, token, conns, _ = _scenario(client)
    try:
        _end(client, code, token)
        board = _teacher_snapshot(client, code, token)["board"]
        assert board["fairness"] == {"winCap": 2, "cooldownSeconds": 0}
        by_q = {q["questionId"]: q["ranking"] for q in board["questions"]}
        q3 = {r["group"]: r for r in by_q["3"]}
        assert q3[G1]["outcome"] == "YieldedCap" and q3[G2]["outcome"] == "Won"
        assert {"rank", "status", "successionRank", "reason"} <= set(q3[G1])  # 原有欄位仍在
        assert by_q["5"][0]["outcome"] == "Kept"
        counts = {t["group"]: t["leadCount"] for t in board["leadTally"]}
        assert counts == {G1: 3, G2: 1, G3: 1}  # Kept 的 Q5 仍計入第 1 組
    finally:
        close_all(conns)


def test_board_without_rule_has_no_fairness(client, use_sheet):
    from .conftest import make_ranked_room

    code, token, conns = make_ranked_room(client)
    try:
        board = _teacher_snapshot(client, code, token)["board"]
        assert board["fairness"] is None
        assert [r["outcome"] for r in board["questions"][0]["ranking"]] == ["Won", "Behind", "Behind"]
    finally:
        close_all({i: c for i, c in enumerate(conns)})


def test_board_updates_live_while_answering(client, use_sheet):
    code, token, conns = make_fair_room(client, win_cap=2)
    try:
        with client.websocket_connect(f"/ws/teacher?token={token}&code={code}") as t:
            t.receive_json()
            for q in "123":
                claim(conns, G1, q, f"g1-{q}")
                claim(conns, G2, q, f"g2-{q}") if q == "3" else None
            last = None
            room = store.rooms[code]
            n_events = len(room.submissions)
            seen = 0
            while seen < n_events:  # 每筆送出各有一則 submission 與一則 board
                m = t.receive_json()
                if m["type"] == "board":
                    last = m
                    seen += 1
            q3 = {r["group"]: r["outcome"] for q in last["questions"] if q["questionId"] == "3" for r in q["ranking"]}
            assert q3[G1] == "YieldedCap"
    finally:
        close_all(conns)


def test_students_never_see_fairness_internals(client, use_sheet):
    code, token, conns, msgs = _scenario(client)
    try:
        text = json.dumps(msgs, ensure_ascii=False)
        for word in SECRET_WORDS:
            assert word not in text, word
        _end(client, code, token)
        for g, (_cm, ws) in conns.items():
            while True:
                m = ws.receive_json()
                if m["type"] == "round_result":
                    break
            t = json.dumps(m, ensure_ascii=False)
            for word in SECRET_WORDS:
                assert word not in t, (g, word)
    finally:
        close_all(conns)


def test_changed_units_reports_only_cascaded_units(client, use_sheet):
    code, token, conns = make_fair_room(client, win_cap=1, groups=(G1, G2))
    try:
        claim(conns, G1, "1", "a")
        claim(conns, G1, "2", "b")
        claim(conns, G2, "2", "c")
        _end(client, code, token)
        with client.websocket_connect(f"/ws/teacher?token={token}&code={code}") as t:
            t.receive_json()
            post_review(client, code, token, "1", G1, "invalid", "答案錯誤")
            m = _wait(t, "review_updated")
            assert m["changedUnits"] == ["2"]  # 第 1 組空出名額 → Q2 改回第 1 組
            post_review(client, code, token, "1", G1, "valid", "誤判")
            assert _wait(t, "review_updated")["changedUnits"] == ["2"]
            post_review(client, code, token, "2", G2, "invalid", "答案錯誤")
            assert _wait(t, "review_updated")["changedUnits"] == []
        # 學生端的 round_result 不帶 changedUnits
        for _g, (_cm, ws) in conns.items():
            while True:
                m = ws.receive_json()
                if m["type"] == "round_result" and m.get("reviewed"):
                    assert "changedUnits" not in m
                    break
    finally:
        close_all(conns)


def _wait(t, kind):
    while True:
        m = t.receive_json()
        if m["type"] == kind:
            return m


def test_export_status_and_reasons(client, use_sheet):
    code, token, conns = make_fair_room(client, win_cap=1, groups=(G1, G2, G3))
    try:
        claim(conns, G1, "1", "a")
        claim(conns, G1, "2", "b")  # 達上限後讓位
        claim(conns, G2, "2", "c")
        claim(conns, G3, "2", "d")  # 名次落後
        claim(conns, G3, "3", "e")
        _end(client, code, token)
        post_review(client, code, token, "3", G3, "invalid", "答案錯誤")
        rows = parse_csv(get_export(client, code, token))
        got = {(r[1], r[3]): (r[11], r[12]) for r in rows[1:]}
        assert got[("Q1", G1)] == ("獲勝", "")
        assert got[("Q2", G1)] == ("未獲勝", "已達上限")
        assert got[("Q2", G2)] == ("獲勝", "")
        assert got[("Q2", G3)] == ("未獲勝", "名次落後")
        assert got[("Q3", G3)] == ("未獲勝", "被駁回")
    finally:
        close_all(conns)
