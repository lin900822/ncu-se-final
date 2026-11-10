"""原則 III：結果公布前不外洩；公布後只含各題第 1 名。"""
import json
import re
from pathlib import Path

from app.store import store

from .conftest import auth, join_student, make_started_room
from .test_submission_privacy import flush

APP = Path(__file__).resolve().parents[1] / "app"
LEAK = ["rank", "seq", "board", "leader", "leadTally", "ranking", "submittedCount", "submittedAt"]


def dumps(o):
    return json.dumps(o, ensure_ascii=False)


def test_no_result_before_end_and_only_winners_after(client, use_sheet):
    code, token = make_started_room(client)
    a1, wa1, ja1 = join_student(client, code, "甲組")
    a2, wa2, _ = join_student(client, code, "甲組")
    b, wb, jb = join_student(client, code, "乙組")
    c, wc, jc = join_student(client, code, "丙組")
    try:
        wa1.send_json({"type": "submit", "questionId": "1", "answer": "甲答案"})
        wb.send_json({"type": "submit", "questionId": "1", "answer": "乙答案"})
        wc.send_json({"type": "submit", "questionId": "2", "answer": "丙答案"})
        before = {n: flush(w) for n, w in [("a1", wa1), ("a2", wa2), ("b", wb), ("c", wc)]}
        for n, msgs in before.items():
            t = dumps(msgs)
            assert "round_result" not in t and "winnerGroup" not in t, n
        for j in (ja1, jb, jc):
            assert j["result"] is None
        # 公布
        client.post(f"/api/rooms/{code}/phase/end", headers=auth(token))
        after = {}
        for n, w in [("a1", wa1), ("a2", wa2), ("b", wb), ("c", wc)]:
            after[n] = flush(w)
        res = [m for m in after["c"] if m["type"] == "round_result"][0]
        # (b) 非第一名的乙組與其答案不出現在任何學生收到的內容
        for n, msgs in after.items():
            t = dumps([m for m in msgs if m["type"] == "round_result"])
            assert "乙組" not in t and "乙答案" not in t, n
            for word in LEAK:
                assert f'"{word}"' not in dumps(msgs), (n, word)
        assert res["results"][0] == {"questionId": "1", "winnerGroup": "甲組", "answer": "甲答案"}
        # (d) 鍵集合
        assert set(res) == {"type", "round", "results"}
        assert all(set(r) == {"questionId", "winnerGroup", "answer"} for r in res["results"])
        # (e) 新一輪
        client.post(f"/api/rooms/{code}/phase/start", headers=auth(token))
        d, wd, jd = join_student(client, code, "丁組")
        try:
            assert jd["result"] is None and jd["phase"] == "Answering"
        finally:
            d.__exit__(None, None, None)
        assert len(store.rooms[code].submissions) == 3  # 舊紀錄保留
        msgs = flush(wa1)
        assert any(m.get("type") == "phase_changed" and m["phase"] == "Answering" for m in msgs)
    finally:
        for x in (a1, a2, b, c):
            x.__exit__(None, None, None)


def test_static_scan_result_channels():
    all_src = {p: p.read_text() for p in APP.rglob("*.py")}
    users = [p.name for p, s in all_src.items() if "broadcast_result(" in s and p.name != "realtime.py"]
    assert users == ["phase.py"]
    for p, s in all_src.items():
        for m in re.finditer(r"broadcast_to_(students|group|other_groups)\(", s):
            call = s[m.start(): m.start() + 200]
            assert "round_result" not in call and "build_result" not in call, p
