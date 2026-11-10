"""原則 III：名次、看板、領先資訊不得出現在任何學生連線。"""
import json
import re
from pathlib import Path

from .conftest import join_student, make_started_room
from .test_submission_privacy import flush

APP = Path(__file__).resolve().parents[1] / "app"
FORBIDDEN = ["rank", "seq", "board", "leader", "leadTally", "ranking", "submittedCount"]


def dumps(o):
    return json.dumps(o, ensure_ascii=False)


def test_students_never_receive_rank_or_board(client, use_sheet):
    code, _ = make_started_room(client)
    a1, wa1, ja1 = join_student(client, code, "甲組")
    a2, wa2, _ = join_student(client, code, "甲組")
    b, wb, jb = join_student(client, code, "乙組")
    c, wc, _ = join_student(client, code, "丙組")
    try:
        wa1.send_json({"type": "submit", "questionId": "1", "answer": "A1"})
        wb.send_json({"type": "submit", "questionId": "1", "answer": "B1"})
        wc.send_json({"type": "submit", "questionId": "2", "answer": "C2"})
        got = {name: flush(ws) for name, ws in [("a1", wa1), ("a2", wa2), ("b", wb), ("c", wc)]}
        for name, msgs in got.items():
            text = dumps(msgs)
            for word in FORBIDDEN:
                assert f'"{word}"' not in text, (name, word)
        # 他組看不到組名
        assert "甲組" not in dumps(got["b"]) + dumps(got["c"])
        assert "乙組" not in dumps(got["a1"]) + dumps(got["a2"]) + dumps(got["c"])
        # 事件格式與 Step 4 相同
        for m in got["a2"]:
            if m["type"] == "submitted":
                assert set(m) == {"type", "questionId", "answer", "round"}
        for m in got["c"]:
            if m["type"] == "question_submitted":
                assert set(m) == {"type", "questionId", "round"}
        for j in (ja1, jb):
            for word in FORBIDDEN:
                assert f'"{word}"' not in dumps(j)
    finally:
        for x in (a1, a2, b, c):
            x.__exit__(None, None, None)


def test_rank_outputs_only_on_teacher_paths():
    """靜態掃描：ranking／rank 只出現在老師路徑，不在學生廣播呼叫附近。"""
    ws_src = (APP / "api" / "ws.py").read_text()
    for m in re.finditer(r"broadcast_to_(group|other_groups|students)\(", ws_src):
        call = ws_src[m.start(): m.start() + 200]
        assert "ranking" not in call and "rank" not in call.replace("broadcast_to_other_groups", "")
    for f in ["services/groups.py", "services/phase.py"]:
        src = (APP / f).read_text()
        for m in re.finditer(r"broadcast_to_students\(", src):
            assert "build_board" not in src[m.start(): m.start() + 200]
    # to_group_event / to_other_groups_event 不含 rank
    sub_src = (APP / "services" / "submissions.py").read_text()
    for fn in ("to_group_event", "to_other_groups_event"):
        body = sub_src.split(f"def {fn}")[1].split("\ndef ")[0]
        assert "rank" not in body
