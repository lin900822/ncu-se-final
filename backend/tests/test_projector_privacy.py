"""Step 12 US2：搶答中投影只顯示匿名進度，零洩漏（憲章原則 III）。"""
import json

from .conftest import (
    claim,
    claim_bundle,
    close_all,
    get_projector_key,
    join_student,
    make_fair_room,
    projector_ws,
    projector_until,
)

G1, G2, G3 = "第 1 組", "第 2 組", "第 3 組"
FORBIDDEN = ["rank", "seq", "submittedAt", "outcome", "Yielded", "Kept", "Behind", "leader", "reason", '"answer"', "SECRET"]
ALLOWED_KEYS = {
    "type", "code", "status", "phase", "round", "groups", "questions", "bundles",
    "progress", "submitted", "result", "scoreboard",
}


def _open(client, **kw):
    code, token, conns = make_fair_room(client, **kw)
    key = get_projector_key(client, code, token)
    cm, ws, first = projector_ws(client, code, key)
    return code, token, conns, cm, ws, first


def _public_text(seen):
    """序列化時排除排行榜（其 rank 是公開的得分名次，與送出名次無關），另外單獨斷言排行榜內容。"""
    for m in seen:
        assert all(set(r) == {"group", "score", "rank"} and r["score"] == 0 for r in m["scoreboard"])
    return json.dumps([{k: v for k, v in m.items() if k != "scoreboard"} for m in seen], ensure_ascii=False)


def _sentinel(client, code, ws):
    """加入一個新組別當哨兵：投影會收到含該組名的狀態，之前排隊的訊息都在它前面。"""
    cm, _w, _ = join_student(client, code, "哨兵組")
    _m, seen = projector_until(ws, lambda m: "哨兵組" in m.get("groups", []))
    cm.__exit__(None, None, None)
    return seen


def test_answering_state_has_only_anonymous_progress(client, use_sheet):
    code, token, conns, cm, ws, first = _open(client, win_cap=2, cooldown=30, bundles=(("3", "4"),))
    try:
        assert first["phase"] == "Answering" and first["progress"] == {"answered": 0, "total": 5}
        assert set(first) == ALLOWED_KEYS
        claim(conns, G1, "1", "SECRET-a1")
        claim(conns, G2, "1", "SECRET-b1")
        claim(conns, G1, "2", "SECRET-a2")
        claim_bundle(conns, G3, "B1", {"3": "SECRET-x3", "4": "SECRET-x4"})
        seen = _sentinel(client, code, ws)
        text = _public_text(seen)
        for word in FORBIDDEN:
            assert word not in text, word
        for m in seen:
            assert set(m) == ALLOWED_KEYS and m["result"] is None
        states = [m for m in seen if m["progress"]]
        # 4 次新送出 → 進度依序 1、1（第 2 組同單位）、2、3；題組整組只算 1 個單位
        assert [m["progress"]["answered"] for m in states[:4]] == [1, 1, 2, 3]
        assert states[-1]["submitted"] == {"1": True, "2": True, "B1": True, "5": False, "6": False}
    finally:
        cm.__exit__(None, None, None)
        close_all(conns)


def test_submission_changes_nothing_but_the_anonymous_flags(client, use_sheet):
    code, token, conns, cm, ws, first = _open(client)
    try:
        claim(conns, G1, "1", "SECRET-a")
        after = ws.receive_json()
        keep = lambda m: {k: v for k, v in m.items() if k not in ("submitted", "progress")}  # noqa: E731
        assert keep(after) == keep(first)  # 組名、得分、名單等與有人送出無關
        assert after["submitted"]["1"] is True and after["progress"]["answered"] == 1
    finally:
        cm.__exit__(None, None, None)
        close_all(conns)


def test_duplicate_submission_sends_nothing_new(client, use_sheet):
    code, token, conns, cm, ws, _ = _open(client)
    try:
        claim(conns, G1, "1", "a")
        ws.receive_json()
        claim(conns, G1, "1", "again")  # 重複送出：不新增紀錄、不推送
        seen = _sentinel(client, code, ws)
        assert all(m["progress"]["answered"] == 1 for m in seen)
        assert len(seen) == 1  # 只有哨兵本身
    finally:
        cm.__exit__(None, None, None)
        close_all(conns)


def test_fairness_rules_do_not_leak_while_answering(client, use_sheet):
    code, token, conns, cm, ws, _ = _open(client, win_cap=1)
    try:
        for q in "123":
            claim(conns, G1, q, f"SECRET-{q}")  # 第 1 組很快達上限，後續送出將讓位
        claim(conns, G2, "3", "SECRET-g2")
        text = _public_text(_sentinel(client, code, ws))
        for word in FORBIDDEN + ["cap", "冷卻", "上限", "讓位", "保留"]:
            assert word not in text, word
    finally:
        cm.__exit__(None, None, None)
        close_all(conns)


def test_students_and_teacher_never_get_projector_messages(client, use_sheet):
    code, token, conns = make_fair_room(client)
    key = get_projector_key(client, code, token)
    try:
        claim(conns, G1, "1", "a")
        for g, (_cm, sws) in conns.items():
            from .test_submission_privacy import flush

            text = json.dumps(flush(sws), ensure_ascii=False)
            for word in ("projector_state", "countdown", "scoreboard", key):
                assert word not in text
    finally:
        close_all(conns)
