"""Step 9 US2：審核後全班結果同步、被駁回者不外洩（原則 III）、重連還原。"""
import json

from app.store import store

from .conftest import join_student, make_ranked_room, post_review
from .test_submission_privacy import flush

UNIT = "1"
FORBIDDEN = ["review_updated", "reviews", "status", "successionRank", "reason", "rank", "board"]


def _close(conns):
    for cm, _ws in conns:
        cm.__exit__(None, None, None)


def _setup(client):
    """三組各一視窗（第 3 組另開第二視窗）、老師 WebSocket 已連線；已結束搶答並清空待讀訊息。"""
    code, token, conns = make_ranked_room(client)
    cm, ws, _ = join_student(client, code, "第 3 組")
    conns.append((cm, ws))
    for _c, w in conns:
        flush(w)
    tcm = client.websocket_connect(f"/ws/teacher?token={token}&code={code}")
    t = tcm.__enter__()
    t.receive_json()  # snapshot
    return code, token, conns, tcm, t


def _next_review_updated(t):
    while True:
        m = t.receive_json()
        if m["type"] == "review_updated":
            return m
        assert m["type"] != "round_result", "老師不應另收 round_result"


def _round_results(msgs):
    return [m for m in msgs if m["type"] == "round_result"]


def test_all_student_windows_get_updated_result_and_teacher_matches(client, use_sheet):
    code, token, conns, tcm, t = _setup(client)
    try:
        r = post_review(client, code, token, UNIT, "第 1 組", "invalid", "答案錯誤")
        assert r.json()["changed"] is True
        got = [_round_results(flush(w)) for _c, w in conns]
        assert all(len(g) == 1 for g in got)
        first = got[0][0]
        assert first["reviewed"] is True and first["round"] == 1
        q1 = {x["questionId"]: x for x in first["results"]}["1"]
        assert q1["winnerGroup"] == "第 2 組" and q1["answer"] == "ans-2"
        assert all(g[0] == first for g in got)  # 每個視窗（含被駁回組、遞補組、同組第二視窗）內容完全相同
        upd = _next_review_updated(t)
        assert upd["result"]["results"] == first["results"]  # 老師與學生一致（FR-016）
        assert {q["questionId"]: q for q in upd["board"]["questions"]}["1"]["leader"] == "第 2 組"
        assert [x["action"] for x in upd["reviews"]] == ["invalid"]
    finally:
        tcm.__exit__(None, None, None)
        _close(conns)


def test_rejected_group_name_answer_reason_never_reach_students(client, use_sheet):
    code, token, conns, tcm, t = _setup(client)
    try:
        post_review(client, code, token, UNIT, "第 1 組", "invalid", "答案錯誤")
        msgs = [m for _c, w in conns for m in flush(w)]
        text = json.dumps(msgs, ensure_ascii=False)
        for secret in ("第 1 組", "ans-1", "答案錯誤"):
            assert secret not in text, secret
        for word in FORBIDDEN:
            assert word not in text, word
        # 之後新加入／重連的學生同樣看不到
        cm, _ws, joined = join_student(client, code, "第 2 組")
        try:
            jtext = json.dumps(joined, ensure_ascii=False)
            assert "第 1 組" not in jtext and "ans-1" not in jtext and "答案錯誤" not in jtext
            assert "reviewed" not in joined and not any(w in jtext for w in ("review_updated", "reviews", "successionRank"))
        finally:
            cm.__exit__(None, None, None)
    finally:
        tcm.__exit__(None, None, None)
        _close(conns)


def test_duplicate_does_not_broadcast_and_restore_updates_everyone(client, use_sheet):
    code, token, conns, tcm, t = _setup(client)
    try:
        post_review(client, code, token, UNIT, "第 1 組", "invalid", "答案錯誤")
        _next_review_updated(t)
        for _c, w in conns:
            flush(w)
        dup = post_review(client, code, token, UNIT, "第 1 組", "invalid", "答案錯誤")
        assert dup.json()["changed"] is False
        assert all(_round_results(flush(w)) == [] for _c, w in conns)  # 重複：學生不再收到
        back = post_review(client, code, token, UNIT, "第 1 組", "valid", "誤判")
        assert back.json()["changed"] is True
        got = [_round_results(flush(w)) for _c, w in conns]
        assert all(len(g) == 1 and g[0]["reviewed"] is True for g in got)
        q1 = {x["questionId"]: x for x in got[0][0]["results"]}["1"]
        assert q1["winnerGroup"] == "第 1 組"
        # 老師的下一則就是恢復後的更新（證明重複動作沒有多送一則）
        upd = _next_review_updated(t)
        assert [x["action"] for x in upd["reviews"]] == ["invalid", "valid"]
    finally:
        tcm.__exit__(None, None, None)
        _close(conns)


def test_no_valid_flag_only_when_everything_rejected(client, use_sheet):
    code, token, conns, tcm, t = _setup(client)
    try:
        for g in ("第 1 組", "第 2 組", "第 3 組"):
            post_review(client, code, token, UNIT, g, "invalid", "亂填")
        last = _round_results(flush(conns[0][1]))[-1]
        items = {x["questionId"]: x for x in last["results"]}
        assert items["1"]["winnerGroup"] is None and items["1"]["answer"] is None
        assert items["1"]["noValid"] is True
        assert "noValid" not in items["2"]  # 從沒有人送出的題目不帶旗標
    finally:
        tcm.__exit__(None, None, None)
        _close(conns)


def test_rejoin_and_teacher_recovery_restore_reviewed_state(client, use_sheet):
    code, token, conns = make_ranked_room(client)  # 不事先連老師：換裝置回復會關閉舊的老師連線
    for _c, w in conns:
        flush(w)
    try:
        post_review(client, code, token, UNIT, "第 1 組", "invalid", "答案錯誤")
        broadcast = _round_results(flush(conns[1][1]))[-1]["results"]
        cm, _ws, joined = join_student(client, code, "第 2 組")
        try:
            assert joined["result"]["results"] == broadcast  # 重連與廣播相同（SC-005）
        finally:
            cm.__exit__(None, None, None)
        rec = client.post("/api/rooms/recover", json={"recoveryCode": store.rooms[code].recovery_code}).json()
        with client.websocket_connect(f"/ws/teacher?token={rec['teacherToken']}&code={code}") as t2:
            snap = t2.receive_json()["room"]
        assert [(x["unitId"], x["group"], x["action"], x["reason"]) for x in snap["reviews"]] == [
            (UNIT, "第 1 組", "invalid", "答案錯誤")
        ]
        assert snap["result"]["results"] == broadcast
    finally:
        _close(conns)


def test_student_cannot_send_review_messages(client, use_sheet):
    code, token, conns = make_ranked_room(client)
    try:
        ws = conns[0][1]
        flush(ws)
        ws.send_json({"type": "review", "round": 1, "unitId": UNIT, "group": "第 2 組", "action": "invalid", "reason": "x"})
        ws.send_json({"type": "reviews"})
        flush(ws)
        assert store.rooms[code].reviews == []
    finally:
        _close(conns)
