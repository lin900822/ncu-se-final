"""Step 9 US1：老師駁回答案、由次順位遞補（核心行為、驗證、原始資料不變）。"""
from app.models import utcnow
from app.services import ranking, results
from app.store import store

from .conftest import make_ranked_room, post_review
from .test_submission_privacy import flush

UNIT = "1"


def _close(conns):
    for cm, _ws in conns:
        cm.__exit__(None, None, None)


def _res(code):
    room = store.rooms[code]
    return {r["questionId"]: r for r in results.build_result(room)["results"]}


def _board_q(code, qid):
    board = ranking.build_board(store.rooms[code])
    return board, {q["questionId"]: q for q in board["questions"]}[qid]


def test_reject_first_place_promotes_second(client, use_sheet):
    code, token, conns = make_ranked_room(client)
    try:
        assert _res(code)["1"]["winnerGroup"] == "第 1 組"
        r = post_review(client, code, token, UNIT, "第 1 組", "invalid", "答案錯誤")
        assert r.status_code == 200 and r.json()["changed"] is True
        q1 = _res(code)["1"]
        assert q1["winnerGroup"] == "第 2 組" and q1["answer"] == "ans-2"
    finally:
        _close(conns)


def test_chain_rejections_and_all_rejected(client, use_sheet):
    code, token, conns = make_ranked_room(client)
    try:
        post_review(client, code, token, UNIT, "第 1 組", "invalid", "亂填")
        post_review(client, code, token, UNIT, "第 2 組", "invalid", "錯字")
        assert _res(code)["1"]["winnerGroup"] == "第 3 組"
        post_review(client, code, token, UNIT, "第 3 組", "invalid", "亂填")
        q1 = _res(code)["1"]
        assert q1["winnerGroup"] is None and q1["answer"] is None
    finally:
        _close(conns)


def test_rejecting_second_place_does_not_change_leader_then_skipped(client, use_sheet):
    code, token, conns = make_ranked_room(client)
    try:
        post_review(client, code, token, UNIT, "第 2 組", "invalid", "亂填")
        assert _res(code)["1"]["winnerGroup"] == "第 1 組"
        post_review(client, code, token, UNIT, "第 1 組", "invalid", "答案錯誤")
        assert _res(code)["1"]["winnerGroup"] == "第 3 組"  # 略過已被駁回的第 2 名
    finally:
        _close(conns)


def test_board_shows_status_succession_rank_reason_and_lead_tally(client, use_sheet):
    code, token, conns = make_ranked_room(client)
    try:
        post_review(client, code, token, UNIT, "第 1 組", "invalid", "答案錯誤")
        board, q1 = _board_q(code, "1")
        rows = {r["group"]: r for r in q1["ranking"]}
        assert rows["第 1 組"]["status"] == "Invalid"
        assert rows["第 1 組"]["successionRank"] is None
        assert rows["第 1 組"]["reason"] == "答案錯誤"
        assert rows["第 1 組"]["rank"] == 1  # 原始名次不變
        assert (rows["第 2 組"]["rank"], rows["第 2 組"]["successionRank"]) == (2, 1)
        assert (rows["第 3 組"]["rank"], rows["第 3 組"]["successionRank"]) == (3, 2)
        assert rows["第 2 組"]["status"] == "Valid" and rows["第 2 組"]["reason"] is None
        assert q1["leader"] == "第 2 組"
        assert {t["group"]: t["leadCount"] for t in board["leadTally"]} == {"第 2 組": 1}
    finally:
        _close(conns)


def test_bundle_rejected_as_a_whole(client, use_sheet):
    code, token, conns = make_ranked_room(client, bundles=(("3", "4"),), groups=("第 1 組", "第 2 組"), end=False)
    try:
        for i, (_cm, ws) in enumerate(conns, start=1):
            ws.send_json({"type": "submit_bundle", "bundleId": "B1", "answers": {"3": f"g{i}-3", "4": f"g{i}-4"}})
            flush(ws)
        from .conftest import auth

        assert client.post(f"/api/rooms/{code}/phase/end", headers=auth(token)).status_code == 200
        assert _res(code)["3"]["winnerGroup"] == _res(code)["4"]["winnerGroup"] == "第 1 組"
        r = post_review(client, code, token, "B1", "第 1 組", "invalid", "整組錯誤")
        assert r.status_code == 200 and r.json()["changed"] is True
        res = _res(code)
        assert res["3"]["winnerGroup"] == res["4"]["winnerGroup"] == "第 2 組"
        assert (res["3"]["answer"], res["4"]["answer"]) == ("g2-3", "g2-4")  # 各題自己的答案
        # 題組成員題不能單獨審核
        bad = post_review(client, code, token, "3", "第 2 組", "invalid", "x")
        assert bad.status_code == 400 and bad.json()["error"]["code"] == "UNIT_NOT_FOUND"
        assert len(store.rooms[code].reviews) == 1
    finally:
        _close(conns)


def test_reason_validation(client, use_sheet):
    code, token, conns = make_ranked_room(client)
    try:
        room = store.rooms[code]
        for bad, expected in (("", "REASON_REQUIRED"), ("   ", "REASON_REQUIRED"), ("字" * 101, "REASON_TOO_LONG")):
            r = post_review(client, code, token, UNIT, "第 1 組", "invalid", bad)
            assert r.status_code == 400 and r.json()["error"]["code"] == expected
            assert room.reviews == []  # 失敗不寫入
        ok = post_review(client, code, token, UNIT, "第 1 組", "invalid", "字" * 100)
        assert ok.status_code == 200 and len(room.reviews) == 1
    finally:
        _close(conns)


def test_original_submissions_never_modified(client, use_sheet):
    code, token, conns = make_ranked_room(client)
    try:
        room = store.rooms[code]
        snap = lambda: [(s.group_name, s.question_id, s.answer, s.submitted_at, s.seq, s.rank, s.round) for s in room.submissions]  # noqa: E731
        before = snap()
        post_review(client, code, token, UNIT, "第 1 組", "invalid", "答案錯誤")
        post_review(client, code, token, UNIT, "第 1 組", "valid", "誤判")
        post_review(client, code, token, UNIT, "第 2 組", "invalid", "亂填")
        assert snap() == before
    finally:
        _close(conns)


def test_review_record_fields(client, use_sheet):
    code, token, conns = make_ranked_room(client)
    try:
        t0 = utcnow()
        post_review(client, code, token, UNIT, "第 1 組", "invalid", "  答案錯誤  ")
        rec = store.rooms[code].reviews[0]
        assert (rec.round, rec.unit_id, rec.group_name, rec.action, rec.reason, rec.by) == (
            1, UNIT, "第 1 組", "Invalid", "答案錯誤", "Teacher",
        )
        assert rec.reviewed_at.tzinfo is not None and t0 <= rec.reviewed_at <= utcnow()  # 後端 UTC
    finally:
        _close(conns)
