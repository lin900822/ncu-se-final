"""Step 9 US4：恢復、稽核紀錄（僅追加）與老師端還原。"""
from app.services import results
from app.store import store

from .conftest import auth, make_ranked_room, post_review
from .test_submission_privacy import flush

UNIT = "1"
REVIEW_KEYS = {"round", "unitId", "group", "action", "reason", "by", "reviewedAt"}


def _close(conns):
    for cm, _ws in conns:
        cm.__exit__(None, None, None)


def _q1(code):
    return {x["questionId"]: x for x in results.build_result(store.rooms[code])["results"]}["1"]


def test_restore_returns_to_original_ranking(client, use_sheet):
    code, token, conns = make_ranked_room(client)
    try:
        post_review(client, code, token, UNIT, "第 1 組", "invalid", "答案錯誤")
        assert _q1(code)["winnerGroup"] == "第 2 組"
        r = post_review(client, code, token, UNIT, "第 1 組", "valid", "誤判")
        assert r.status_code == 200 and r.json()["changed"] is True and r.json()["action"] == "valid"
        assert _q1(code)["winnerGroup"] == "第 1 組"
        from app.services import ranking

        rows = {x["group"]: x for x in {q["questionId"]: q for q in ranking.build_board(store.rooms[code])["questions"]}["1"]["ranking"]}
        assert [(rows[g]["rank"], rows[g]["successionRank"]) for g in ("第 1 組", "第 2 組", "第 3 組")] == [(1, 1), (2, 2), (3, 3)]
    finally:
        _close(conns)


def test_restore_requires_reason(client, use_sheet):
    code, token, conns = make_ranked_room(client)
    try:
        post_review(client, code, token, UNIT, "第 1 組", "invalid", "答案錯誤")
        r = post_review(client, code, token, UNIT, "第 1 組", "valid", "  ")
        assert r.status_code == 400 and r.json()["error"]["code"] == "REASON_REQUIRED"
        assert len(store.rooms[code].reviews) == 1
    finally:
        _close(conns)


def test_reviews_are_append_only_with_full_fields(client, use_sheet):
    code, token, conns = make_ranked_room(client)
    try:
        room = store.rooms[code]
        seen = []
        for action, reason in (("invalid", "答案錯誤"), ("valid", "誤判"), ("invalid", "亂填")):
            assert post_review(client, code, token, UNIT, "第 1 組", action, reason).json()["changed"] is True
            seen.append([(r.round, r.unit_id, r.group_name, r.action, r.reason, r.by, r.reviewed_at) for r in room.reviews])
            assert len(room.reviews) == len(seen)  # 只增不減
            for i, earlier in enumerate(seen[:-1]):
                assert seen[-1][: len(earlier)] == earlier  # 既有紀錄內容不被修改
        assert [r.action for r in room.reviews] == ["Invalid", "Valid", "Invalid"]
        assert all(r.by == "Teacher" and r.round == 1 and r.unit_id == UNIT and r.group_name == "第 1 組" for r in room.reviews)
        times = [r.reviewed_at for r in room.reviews]
        assert times == sorted(times)
    finally:
        _close(conns)


def test_snapshot_and_update_message_share_the_same_review_shape(client, use_sheet):
    code, token, conns = make_ranked_room(client)
    try:
        for _c, w in conns:
            flush(w)
        with client.websocket_connect(f"/ws/teacher?token={token}&code={code}") as t:
            t.receive_json()
            post_review(client, code, token, UNIT, "第 1 組", "invalid", "答案錯誤")
            while True:
                m = t.receive_json()
                if m["type"] == "review_updated":
                    break
        assert [set(x) for x in m["reviews"]] == [REVIEW_KEYS]
        assert m["reviews"][0]["action"] == "invalid"
        with client.websocket_connect(f"/ws/teacher?token={token}&code={code}") as t2:
            snap = t2.receive_json()["room"]
        assert snap["reviews"] == m["reviews"]
    finally:
        _close(conns)


def test_history_survives_new_round_and_teacher_recovery(client, use_sheet):
    code, token, conns = make_ranked_room(client)
    try:
        post_review(client, code, token, UNIT, "第 1 組", "invalid", "第一輪")
        assert client.post(f"/api/rooms/{code}/phase/start", headers=auth(token)).status_code == 200
        assert client.post(f"/api/rooms/{code}/phase/end", headers=auth(token)).status_code == 200  # 第二輪無人送出
        room = store.rooms[code]
        assert room.round == 2 and len(room.reviews) == 1  # 舊輪紀錄保留
        new = client.post("/api/rooms/recover", json={"recoveryCode": room.recovery_code}).json()["teacherToken"]
        with client.websocket_connect(f"/ws/teacher?token={new}&code={code}") as t:
            snap = t.receive_json()["room"]
        assert [(x["round"], x["group"], x["action"], x["reason"]) for x in snap["reviews"]] == [
            (1, "第 1 組", "invalid", "第一輪")
        ]
        # 第二輪的結果不受第一輪審核影響（沒有人送出）
        assert all(x["winnerGroup"] is None and "noValid" not in x for x in snap["result"]["results"])
    finally:
        _close(conns)
