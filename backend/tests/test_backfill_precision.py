"""Step 10 US2：只改作答格、答案純文字原樣、結構變動被攔下、全有或全無。"""
import pytest

from app.models import err
from app.services import sheets as sheets_service
from app.sheets.a1 import parse_a1
from app.store import store

from .conftest import auth, join_student, make_ranked_room, make_started_room, post_backfill
from .test_submission_privacy import flush


def _close(conns):
    for cm, _ws in conns:
        cm.__exit__(None, None, None)


def _target(code, qid):
    return parse_a1(next(q for q in store.rooms[code].questions if q.id == qid).cell)


def _winner_room(client, answers):
    """第 1 組對 answers 的每一題送出答案後結束搶答，回傳 (code, token, cm)。"""
    code, token = make_started_room(client)
    cm, ws, _ = join_student(client, code, "第 1 組")
    for qid, text in answers.items():
        ws.send_json({"type": "submit", "questionId": qid, "answer": text})
        flush(ws)
    assert client.post(f"/api/rooms/{code}/phase/end", headers=auth(token)).status_code == 200
    return code, token, cm


def test_only_target_cells_change_and_merges_untouched(client, fake_sheet):
    code, token, conns = make_ranked_room(client)
    try:
        before, merges = fake_sheet.snapshot(), list(fake_sheet.grid.merges)
        assert post_backfill(client, code, token).status_code == 200
        after = fake_sheet.snapshot()
        row, col = _target(code, "1")
        changed = [
            (r, c)
            for r in range(max(len(before), len(after)))
            for c in range(max(len(before[r]) if r < len(before) else 0, len(after[r]) if r < len(after) else 0))
            if (before[r][c] if r < len(before) and c < len(before[r]) else "")
            != (after[r][c] if r < len(after) and c < len(after[r]) else "")
        ]
        assert changed == [(row, col)]  # 整份試算表只有目標作答格改變（SC-003）
        assert fake_sheet.grid.merges == merges
    finally:
        _close(conns)


@pytest.mark.parametrize(
    "text",
    [
        "=1+1", "+1", "-5", "@SUM(A1)", "007", "3/4",
        '含逗號, 與 "引號"', "第一行\n第二行", "中央處理器", "字" * 500,
    ],
)
def test_answer_text_is_written_verbatim(client, fake_sheet, text):
    code, token, cm = _winner_room(client, {"1": text})
    try:
        assert post_backfill(client, code, token).status_code == 200
        row, col = _target(code, "1")
        assert fake_sheet.grid.raw(row, col) == text  # 逐字相同，未被當成公式或轉型（SC-002、SC-005）
        assert fake_sheet.writes[0][0][2] == text
    finally:
        cm.__exit__(None, None, None)


def test_structure_change_is_rejected_without_any_write(client, fake_sheet):
    code, token, conns = make_ranked_room(client)
    try:
        assert post_backfill(client, code, token, preview=True).status_code == 200
        fake_sheet.insert_row(0)  # 老師在建立房間後改動了試算表：所有作答格位置位移
        before = fake_sheet.snapshot()
        for preview in (True, False):
            r = post_backfill(client, code, token, preview=preview)
            assert r.status_code == 409 and r.json()["error"]["code"] == "SHEET_STRUCTURE_CHANGED"
        assert fake_sheet.writes == [] and fake_sheet.snapshot() == before  # SC-004
    finally:
        _close(conns)


def test_broken_header_counts_as_structure_change(client, fake_sheet):
    code, token, conns = make_ranked_room(client)
    try:
        for r_i, line in enumerate(fake_sheet.grid.rows):
            for c_i, v in enumerate(line):
                if v.strip() == "題號":
                    fake_sheet.set_cell(r_i, c_i, "別的標題")
        r = post_backfill(client, code, token)
        assert r.status_code == 409 and r.json()["error"]["code"] == "SHEET_STRUCTURE_CHANGED"
        assert fake_sheet.writes == []
    finally:
        _close(conns)


def test_deleted_sheet_is_reported_and_nothing_written(client, fake_sheet, monkeypatch):
    code, token, conns = make_ranked_room(client)
    try:
        async def gone(spreadsheet_id, gid):
            raise err("SHEET_NOT_FOUND")

        monkeypatch.setattr(sheets_service, "_fetch", gone)
        r = post_backfill(client, code, token)
        assert r.status_code == 404 and r.json()["error"]["code"] == "SHEET_NOT_FOUND"
        assert fake_sheet.writes == []
    finally:
        _close(conns)


def test_all_or_nothing_when_the_write_fails(client, fake_sheet):
    code, token, cm = _winner_room(client, {"1": "甲", "2": "乙", "3": "丙"})
    try:
        before = fake_sheet.snapshot()
        fake_sheet.fail_next = err("SHEET_WRITE_FAILED")
        r = post_backfill(client, code, token)
        assert r.status_code == 502 and r.json()["error"]["code"] == "SHEET_WRITE_FAILED"
        assert fake_sheet.snapshot() == before  # 沒有任何一格被改動（不會只填一半）
        assert fake_sheet.writes == []
    finally:
        cm.__exit__(None, None, None)


def test_merged_answer_cell_writes_to_recorded_top_left_cell(client, fake_sheet):
    code, token, conns = make_ranked_room(client)
    try:
        row, col = _target(code, "1")
        fake_sheet.grid.merges.append((row, row + 1, col, col + 1))  # 作答格本身是（單格）合併範圍
        merges = list(fake_sheet.grid.merges)
        assert post_backfill(client, code, token).status_code == 200
        assert fake_sheet.grid.raw(row, col) == "ans-1"
        assert fake_sheet.grid.merges == merges
    finally:
        _close(conns)


def test_many_questions_are_written_in_a_single_batch(client, fake_sheet):
    fake_sheet.use("group.xlsx")
    code, token = make_started_room(client)
    questions = store.rooms[code].questions
    cm, ws, _ = join_student(client, code, "第 1 組")
    try:
        for q in questions:
            ws.send_json({"type": "submit", "questionId": q.id, "answer": f"答-{q.id}"})
            flush(ws)
        assert client.post(f"/api/rooms/{code}/phase/end", headers=auth(token)).status_code == 200
        assert post_backfill(client, code, token).status_code == 200
        assert len(fake_sheet.writes) == 1 and len(fake_sheet.writes[0]) == len(questions)
        for q in questions:
            row, col = parse_a1(q.cell)
            assert fake_sheet.grid.raw(row, col) == f"答-{q.id}"
    finally:
        cm.__exit__(None, None, None)
