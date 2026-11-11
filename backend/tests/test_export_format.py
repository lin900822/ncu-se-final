"""Step 8 US2：CSV 格式（BOM／CRLF／跳脫）、公式安全、不外洩內部欄位。"""
import csv
import io
from datetime import datetime, timezone

import pytest

from app.models import Group, Question
from app.services import export, rooms, submissions
from app.store import store

from .conftest import get_export, join_student, make_started_room, parse_csv
from .test_submission_privacy import flush


def _room(pairs):
    """pairs: [(組名, 答案)]，每筆放在各自的題目上；回傳 room。"""
    room = rooms.create_room()
    room.questions = [
        Question(id=str(i), number=i, sub=None, label=f"Q{i}", cell=f"'學習單'!H{i + 5}")
        for i in range(1, len(pairs) + 1)
    ]
    room.phase = "Answering"
    room.round = 1
    for i, (name, answer) in enumerate(pairs, start=1):
        g = Group(name=name, normalized_name=name.lower(), online=True, joined_at=datetime.now(timezone.utc))
        room.groups[g.normalized_name] = g
        submissions.submit(room, g, str(i), answer)
    return room


def _parse(text):
    return list(csv.reader(io.StringIO(text.lstrip("﻿"), newline="")))


def test_bom_and_crlf():
    text = export.render_csv(_room([("甲", "答")]))
    assert text.startswith("﻿")
    assert text.encode("utf-8").startswith(b"\xef\xbb\xbf")
    body = text[1:]
    assert body.endswith("\r\n")
    assert "\n" not in body.replace("\r\n", "")  # 沒有單獨的 LF


def test_special_characters_roundtrip_without_extra_rows():
    answers = ['含逗號, 與 "引號"', "第一行\n第二行", "中央處理器"]
    room = _room([("A,B組", answers[0]), ("乙", answers[1]), ("丙", answers[2])])
    rows = _parse(export.render_csv(room))
    assert len(rows) == 4  # 標題列 + 3 列（換行不增加列數）
    assert [r[4] for r in rows[1:]] == answers
    assert rows[1][3] == "A,B組"
    assert all(len(r) == 7 for r in rows)


def test_500_chars_answer_not_truncated():
    long = "長" * 500
    rows = _parse(export.render_csv(_room([("甲", long)])))
    assert rows[1][4] == long


@pytest.mark.parametrize("text", ["=1+1", "+1", "-5", "@SUM(A1)", "\t=1", "\r=1", "\n=1"])
def test_safe_cell_prefixes_formula_starts(text):
    out = export.safe_cell(text)
    assert out == "'" + text and out[1:] == text


@pytest.mark.parametrize("text", ["CPU", "1=1", " =1", "", "中文", "a-b"])
def test_safe_cell_leaves_plain_text(text):
    assert export.safe_cell(text) == text


def test_endpoint_neutralizes_formulas_in_answer_and_group_name(client, use_sheet):
    code, token = make_started_room(client)
    a, wa, _ = join_student(client, code, "=SUM(1)")
    try:
        wa.send_json({"type": "submit", "questionId": "1", "answer": "=1+1"})
        flush(wa)
        wa.send_json({"type": "submit", "questionId": "2", "answer": "正常答案"})
        flush(wa)
        rows = parse_csv(get_export(client, code, token))
        assert rows[1][3] == "'=SUM(1)" and rows[1][4] == "'=1+1"
        assert rows[2][4] == "正常答案"  # 一般文字不加前綴
    finally:
        a.__exit__(None, None, None)


def test_export_does_not_leak_internal_fields(client, use_sheet):
    code, token = make_started_room(client)
    a, wa, _ = join_student(client, code, "第 1 組")
    try:
        wa.send_json({"type": "submit", "questionId": "1", "answer": "答案甲"})
        flush(wa)
        r = get_export(client, code, token)
        text = r.content.decode("utf-8-sig")
        room = store.rooms[code]
        assert room.teacher_token not in text and room.recovery_code not in text
        assert all(q.cell not in text for q in room.questions)
        rows = parse_csv(r)
        assert rows[0] == ["輪次", "題號", "題組", "組別", "答案", "接收時間", "排名"]
        assert all(len(row) == 7 for row in rows)  # 沒有 seq 等額外欄位
    finally:
        a.__exit__(None, None, None)


def test_unknown_question_id_falls_back_to_id_without_error():
    room = _room([("甲", "答")])
    room.questions = []  # 模擬題目已不在清單中：不應丟例外，題號欄退回使用 id
    rows = _parse(export.render_csv(room))
    assert rows[1][1] == "1"


def test_formula_guard_only_on_group_and_answer_columns():
    room = _room([("甲", "=1+1")])
    rows = export.build_rows(room)
    # 題號、題組、接收時間、排名為系統產生的固定格式，不套用前綴
    assert rows[0][1] == "Q1" and rows[0][2] == "" and rows[0][5].startswith("20")
    assert rows[0][3] == "甲" and rows[0][4] == "'=1+1"
