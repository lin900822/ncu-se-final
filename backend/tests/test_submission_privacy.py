"""原則 III：他組在畫面與所有即時資料中都看不到該組的答案、草稿、組名、組數或時間。"""
import json
import re
from pathlib import Path

from .conftest import join_student, make_started_room

SECRET = "獨特答案ZZ"
APP = Path(__file__).resolve().parents[1] / "app"


def flush(ws):
    """用一個必定回錯誤的訊息當哨兵：FIFO 下，哨兵之前收到的就是先前所有訊息。"""
    ws.send_json({"type": "submit", "questionId": "99", "answer": "x"})
    msgs = []
    while True:
        m = ws.receive_json()
        msgs.append(m)
        if m.get("type") == "error" and m.get("questionId") == "99":
            return msgs[:-1]


def dumps(obj) -> str:
    return json.dumps(obj, ensure_ascii=False)


def test_other_group_sees_only_anonymous_hint(client, use_sheet):
    code, _ = make_started_room(client)
    c1, w1, _ = join_student(client, code, "第 1 組")
    c1b, w1b, _ = join_student(client, code, "第 1 組")
    c2, w2, _ = join_student(client, code, "第 2 組")
    try:
        w1.send_json({"type": "submit", "questionId": "1", "answer": SECRET})
        assert w1.receive_json()["answer"] == SECRET
        # (e) 對照組：同組其他視窗有收到答案
        assert w1b.receive_json()["answer"] == SECRET
        # (a)(b) 他組收到的所有訊息
        received = flush(w2)
        assert len(received) == 1
        assert SECRET not in dumps(received) and "第 1 組" not in dumps(received)
        assert set(received[0].keys()) == {"type", "questionId", "round"}
        assert received[0]["type"] == "question_submitted" and received[0]["questionId"] == "1"
    finally:
        for cm in (c1, c1b, c2):
            cm.__exit__(None, None, None)


def test_teacher_receives_answer(client, use_sheet):
    code, token = make_started_room(client)
    tcm = client.websocket_connect(f"/ws/teacher?code={code}&token={token}")
    tws = tcm.__enter__()
    tws.receive_json()  # snapshot
    c1, w1, _ = join_student(client, code, "第 1 組")
    tws.receive_json()  # group_joined
    try:
        w1.send_json({"type": "submit", "questionId": "1", "answer": SECRET})
        w1.receive_json()
        m = tws.receive_json()
        assert m["type"] == "submission" and m["answer"] == SECRET and m["group"] == "第 1 組"
    finally:
        c1.__exit__(None, None, None)
        tcm.__exit__(None, None, None)


def test_rejoin_of_other_group_gets_only_ids(client, use_sheet):
    code, _ = make_started_room(client)
    c1, w1, _ = join_student(client, code, "第 1 組")
    c2, w2, _ = join_student(client, code, "第 2 組")
    try:
        w1.send_json({"type": "submit", "questionId": "1", "answer": SECRET})
        w1.receive_json()
        c3, w3, joined = join_student(client, code, "第 2 組")
        try:
            assert joined["mySubmissions"] == {}
            assert joined["submittedByOthers"] == ["1"]
            text = dumps(joined)
            assert SECRET not in text and "第 1 組" not in text
        finally:
            c3.__exit__(None, None, None)
    finally:
        c1.__exit__(None, None, None)
        c2.__exit__(None, None, None)


def test_drafts_never_leave_the_browser(client, use_sheet):
    code, _ = make_started_room(client)
    c1, w1, _ = join_student(client, code, "第 1 組")
    c2, w2, _ = join_student(client, code, "第 2 組")
    try:
        # 第 1 組只在輸入（即使客戶端亂送草稿訊息，伺服器也不轉發）
        w1.send_json({"type": "draft", "questionId": "1", "answer": "草稿內容"})
        w1.send_json({"type": "typing", "questionId": "1"})
        assert flush(w1) == []
        assert flush(w2) == []  # 第 2 組完全沒收到任何新訊息
    finally:
        c1.__exit__(None, None, None)
        c2.__exit__(None, None, None)


def test_broadcast_call_sites_are_restricted():
    """審查：向「所有學生」與「他組」廣播的呼叫點只傳房間層級訊息或匿名提示。"""
    students, others = [], []
    for path in APP.rglob("*.py"):
        if path.name == "realtime.py":
            continue
        text = path.read_text(encoding="utf-8")
        rel = path.relative_to(APP).as_posix()
        for m in re.finditer(r"broadcast_to_students\(", text):
            students.append(rel)
        for m in re.finditer(r"broadcast_to_other_groups\([^)]*\)", text, flags=re.S):
            others.append((rel, m.group(0)))
    # 向所有學生廣播只出現在階段服務（階段與題目文字）
    assert set(students) == {"services/phase.py"}
    # 向他組廣播只送匿名提示事件（單題：to_other_groups_event；題組：to_bundle_hint_event）
    assert len(others) == 2
    assert all(rel == "api/ws.py" for rel, _ in others)
    assert sorted(
        "to_other_groups_event" if "to_other_groups_event" in call else
        "to_bundle_hint_event" if "to_bundle_hint_event" in call else call
        for _, call in others
    ) == ["to_bundle_hint_event", "to_other_groups_event"]
    # 題組匿名提示只含題組識別碼與輪次
    sub_src = (APP / "services" / "submissions.py").read_text(encoding="utf-8")
    hint = sub_src.split("def to_bundle_hint_event")[1].split("\ndef ")[0]
    assert "answer" not in hint and "group_name" not in hint and "rank" not in hint
