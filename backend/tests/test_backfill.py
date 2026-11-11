"""Step 10 US1：預覽（唯讀）、確認後把各題有效第一名的答案寫回作答格。"""
from app.sheets.a1 import parse_a1
from app.store import store

from .conftest import auth, join_student, make_ranked_room, make_started_room, post_backfill, post_review
from .test_submission_privacy import flush


def _close(conns):
    for cm, _ws in conns:
        cm.__exit__(None, None, None)


def _cell(fake, code, qid):
    q = next(q for q in store.rooms[code].questions if q.id == qid)
    row, col = parse_a1(q.cell)
    return fake.grid.raw(row, col)


def test_preview_is_read_only_and_describes_the_plan(client, fake_sheet):
    code, token, conns = make_ranked_room(client)
    try:
        r = post_backfill(client, code, token, preview=True)
        assert r.status_code == 200
        body = r.json()
        assert body["canBackfill"] is True and body["round"] == 1
        assert body["counts"] == {"write": 1, "skip": 5, "clear": 0, "keep": 0, "overwrite": 0}
        items = {i["questionId"]: i for i in body["items"]}
        assert len(items) == 6
        assert items["1"]["action"] == "write" and items["1"]["answer"] == "ans-1"
        assert all(items[q]["action"] == "skip" and items[q]["answer"] is None for q in "23456")
        assert fake_sheet.writes == [] and store.rooms[code].backfills == []  # 預覽不寫入、不記錄
    finally:
        _close(conns)


def test_confirm_writes_winner_answer_to_the_answer_cell(client, fake_sheet):
    code, token, conns = make_ranked_room(client)
    try:
        before = fake_sheet.snapshot()
        r = post_backfill(client, code, token)
        assert r.status_code == 200
        body = r.json()
        assert body["record"]["result"] == "Success" and body["record"]["written"] == 1
        assert body["counts"] == {"write": 1, "skip": 5, "clear": 0, "keep": 0}
        assert body["sheetUrl"] == store.rooms[code].sheet.url
        assert _cell(fake_sheet, code, "1") == "ans-1"
        # 除了 Q1 的作答格，其餘儲存格與回填前完全相同
        row, col = parse_a1(next(q for q in store.rooms[code].questions if q.id == "1").cell)
        after = fake_sheet.snapshot()
        for r_i, line in enumerate(after):
            for c_i, v in enumerate(line):
                if (r_i, c_i) != (row, col):
                    assert v == (before[r_i][c_i] if r_i < len(before) and c_i < len(before[r_i]) else "")
        assert len(fake_sheet.writes) == 1 and len(fake_sheet.writes[0]) == 1  # 單一批次、一格
    finally:
        _close(conns)


def test_review_promotion_is_what_gets_written(client, fake_sheet):
    code, token, conns = make_ranked_room(client)
    try:
        assert post_review(client, code, token, "1", "第 1 組", "invalid", "答案錯誤").json()["changed"] is True
        assert post_backfill(client, code, token).status_code == 200
        assert _cell(fake_sheet, code, "1") == "ans-2"  # 被駁回的答案不會被寫入
        assert "ans-1" not in [c for line in fake_sheet.grid.rows for c in line]
    finally:
        _close(conns)


def test_question_without_valid_answer_is_not_written(client, fake_sheet):
    code, token, conns = make_ranked_room(client)
    try:
        original = {q: _cell(fake_sheet, code, q) for q in "23456"}
        post_backfill(client, code, token)
        assert {q: _cell(fake_sheet, code, q) for q in "23456"} == original
    finally:
        _close(conns)


def test_bundle_members_get_their_own_answers(client, fake_sheet):
    code, token, conns = make_ranked_room(client, bundles=(("3", "4"),), groups=("第 1 組", "第 2 組"), end=False)
    try:
        for i, (_cm, ws) in enumerate(conns, start=1):
            ws.send_json({"type": "submit_bundle", "bundleId": "B1", "answers": {"3": f"g{i}-3", "4": f"g{i}-4"}})
            flush(ws)
        assert client.post(f"/api/rooms/{code}/phase/end", headers=auth(token)).status_code == 200
        assert post_backfill(client, code, token).status_code == 200
        assert (_cell(fake_sheet, code, "3"), _cell(fake_sheet, code, "4")) == ("g1-3", "g1-4")  # 互不串接
        assert _cell(fake_sheet, code, "1") == "ans-1"
        # 題組被駁回後遞補：整組改為第 2 組各題自己的答案
        post_review(client, code, token, "B1", "第 1 組", "invalid", "整組錯誤")
        assert post_backfill(client, code, token).status_code == 200
        assert (_cell(fake_sheet, code, "3"), _cell(fake_sheet, code, "4")) == ("g2-3", "g2-4")
    finally:
        _close(conns)


def test_subquestions_each_written_to_their_own_cell(client, fake_sheet):
    fake_sheet.use("group.xlsx")
    code, token = make_started_room(client)
    cm, ws, _ = join_student(client, code, "第 1 組")
    try:
        ws.send_json({"type": "submit", "questionId": "1-1", "answer": "甲"})
        flush(ws)
        ws.send_json({"type": "submit", "questionId": "1-2", "answer": "乙"})
        flush(ws)
        assert client.post(f"/api/rooms/{code}/phase/end", headers=auth(token)).status_code == 200
        assert post_backfill(client, code, token).status_code == 200
        assert (_cell(fake_sheet, code, "1-1"), _cell(fake_sheet, code, "1-2")) == ("甲", "乙")
    finally:
        cm.__exit__(None, None, None)
