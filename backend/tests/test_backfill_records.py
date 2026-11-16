"""Step 10 US4：覆寫計數、重新回填、清空與保留、互斥、回填紀錄與還原。"""
import asyncio
import json

from app.services import backfill
from app.sheets.a1 import parse_a1
from app.store import store

from .conftest import auth, join_student, make_ranked_room, make_started_room, post_backfill, post_review
from .test_submission_privacy import flush


def _close(conns):
    for cm, _ws in conns:
        cm.__exit__(None, None, None)


def _pos(code, qid):
    return parse_a1(next(q for q in store.rooms[code].questions if q.id == qid).cell)


def _winner_room(client, answers):
    """第 1 組送出 answers 後結束搶答：回傳 (code, token, cm)。"""
    code, token = make_started_room(client)
    cm, ws, _ = join_student(client, code, "第 1 組")
    for qid, text in answers.items():
        ws.send_json({"type": "submit", "questionId": qid, "answer": text})
        flush(ws)
    assert client.post(f"/api/rooms/{code}/phase/end", headers=auth(token)).status_code == 200
    return code, token, cm


def test_overwrite_count_only_counts_cells_with_different_content(client, fake_sheet):
    code, token, conns = make_ranked_room(client)
    try:
        row, col = _pos(code, "1")
        fake_sheet.set_cell(row, col, "老師先打的字")
        body = post_backfill(client, code, token, preview=True).json()
        assert body["counts"]["overwrite"] == 1
        assert {i["questionId"]: i for i in body["items"]}["1"]["overwrite"] is True
        fake_sheet.set_cell(row, col, "ans-1")  # 內容已等於答案：不算覆寫
        assert post_backfill(client, code, token, preview=True).json()["counts"]["overwrite"] == 0
    finally:
        _close(conns)


def test_preview_alone_never_writes_or_records(client, fake_sheet):
    code, token, conns = make_ranked_room(client)
    try:
        for _ in range(3):
            assert post_backfill(client, code, token, preview=True).status_code == 200
        assert fake_sheet.writes == [] and store.rooms[code].backfills == []  # 取消＝只預覽，不寫入
    finally:
        _close(conns)


def test_rebackfill_after_review_and_unchanged_rebackfill(client, fake_sheet):
    code, token, conns = make_ranked_room(client)
    try:
        row, col = _pos(code, "1")
        assert post_backfill(client, code, token).status_code == 200
        assert fake_sheet.grid.raw(row, col) == "ans-1"
        post_review(client, code, token, "1", "第 1 組", "invalid", "答案錯誤")
        assert post_backfill(client, code, token).status_code == 200
        assert fake_sheet.grid.raw(row, col) == "ans-2"  # 更新為遞補者，沒有殘留舊答案（SC-006）
        before = fake_sheet.snapshot()
        r = post_backfill(client, code, token)  # 結果沒變：不報錯、內容不變
        assert r.status_code == 200 and fake_sheet.snapshot() == before
        assert len(store.rooms[code].backfills) == 3 and len(fake_sheet.writes) == 3
    finally:
        _close(conns)


def test_cell_is_cleared_when_the_answer_it_holds_no_longer_has_a_valid_winner(client, fake_sheet):
    code, token, cm = _winner_room(client, {"1": "甲"})
    try:
        row, col = _pos(code, "1")
        assert post_backfill(client, code, token).status_code == 200
        assert fake_sheet.grid.raw(row, col) == "甲"
        post_review(client, code, token, "1", "第 1 組", "invalid", "答案錯誤")  # Q1 變成沒有有效答案
        prev = post_backfill(client, code, token, preview=True).json()
        assert prev["canBackfill"] is True and prev["counts"]["clear"] == 1 and prev["counts"]["write"] == 0
        r = post_backfill(client, code, token)
        assert r.status_code == 200 and r.json()["record"]["cleared"] == 1
        assert fake_sheet.grid.raw(row, col) == ""  # 清空回空白
        # 之後該格已不在「先前寫入」集合：不再清空，也沒有可做的事
        again = post_backfill(client, code, token)
        assert again.status_code == 400 and again.json()["error"]["code"] == "BACKFILL_NOTHING"
    finally:
        cm.__exit__(None, None, None)


def test_cell_edited_by_teacher_is_kept_and_unwritten_cells_are_never_touched(client, fake_sheet):
    code, token, cm = _winner_room(client, {"1": "甲", "2": "乙"})
    try:
        r1, c1 = _pos(code, "1")
        r3, c3 = _pos(code, "3")
        fake_sheet.set_cell(r3, c3, "既有內容")  # 沒人答 Q3、也從未由本系統寫入
        assert post_backfill(client, code, token).status_code == 200
        fake_sheet.set_cell(r1, c1, "老師自己寫的")  # 老師改過本系統寫的格
        post_review(client, code, token, "1", "第 1 組", "invalid", "答案錯誤")
        prev = post_backfill(client, code, token, preview=True).json()
        assert prev["counts"]["keep"] == 1 and prev["counts"]["clear"] == 0
        r = post_backfill(client, code, token)
        assert r.status_code == 200 and r.json()["record"]["kept"] == 1
        assert fake_sheet.grid.raw(r1, c1) == "老師自己寫的"  # 不被清空
        assert fake_sheet.grid.raw(r3, c3) == "既有內容"  # 沒被本系統寫過的格絕不碰
    finally:
        cm.__exit__(None, None, None)


def test_nothing_to_backfill_is_not_an_attempt(client, fake_sheet):
    code, token = make_started_room(client)
    assert client.post(f"/api/rooms/{code}/phase/end", headers=auth(token)).status_code == 200
    prev = post_backfill(client, code, token, preview=True).json()
    assert prev["canBackfill"] is False and prev["counts"]["write"] == 0
    r = post_backfill(client, code, token)
    assert r.status_code == 400 and r.json()["error"]["code"] == "BACKFILL_NOTHING"
    assert store.rooms[code].backfills == [] and fake_sheet.writes == []


def test_concurrent_confirms_write_once_and_record_once_100_times(client, fake_sheet, monkeypatch):
    code, token, conns = make_ranked_room(client)
    try:
        room = store.rooms[code]
        orig = fake_sheet.write_batch

        async def slow(spreadsheet_id, sheet_id, updates):
            await asyncio.sleep(0)  # 讓兩個確認在寫入途中交錯
            await orig(spreadsheet_id, sheet_id, updates)

        monkeypatch.setattr(backfill, "_write_batch", slow)

        async def run():
            for i in range(100):
                res = await asyncio.gather(
                    backfill.execute(room, 1), backfill.execute(room, 1), return_exceptions=True
                )
                ok = [x for x in res if isinstance(x, dict)]
                busy = [x for x in res if getattr(x, "code", None) == "BACKFILL_IN_PROGRESS"]
                assert len(ok) == 1 and len(busy) == 1, (i, res)
                assert len(room.backfills) == i + 1 and len(fake_sheet.writes) == i + 1

        asyncio.run(run())
    finally:
        _close(conns)


def test_records_are_append_only_and_public_form_hides_cells_and_answers(client, fake_sheet):
    code, token, conns = make_ranked_room(client)
    try:
        room = store.rooms[code]
        post_backfill(client, code, token)
        first = (room.backfills[0].at, dict(room.backfills[0].written), room.backfills[0].result)
        post_review(client, code, token, "1", "第 1 組", "invalid", "答案錯誤")
        post_backfill(client, code, token)
        assert len(room.backfills) == 2
        assert (room.backfills[0].at, dict(room.backfills[0].written), room.backfills[0].result) == first  # 既有紀錄不變
        assert room.backfills[0].at <= room.backfills[1].at
        assert all(r.round == 1 and r.by == "Teacher" for r in room.backfills)
        with client.websocket_connect(f"/ws/teacher?token={token}&code={code}") as t:
            snap = t.receive_json()["room"]
        text = json.dumps(snap["backfills"], ensure_ascii=False)
        assert len(snap["backfills"]) == 2 and snap["sheetUrl"] == room.sheet.url
        assert set(snap["backfills"][0]) == {"round", "at", "written", "skipped", "cleared", "kept", "result", "reason", "message"}
        assert "ans-" not in text and "'!" not in text and "學習單" not in text  # 不含答案與儲存格位置
    finally:
        _close(conns)


def test_sync_to_teacher_windows_and_restore_after_recovery_and_new_round(client, fake_sheet):
    code, token, conns = make_ranked_room(client)
    try:
        with client.websocket_connect(f"/ws/teacher?token={token}&code={code}") as t:
            t.receive_json()
            post_backfill(client, code, token)
            while True:
                m = t.receive_json()
                if m["type"] == "backfill_updated":
                    break
        assert len(m["backfills"]) == 1 and m["backfills"][0]["result"] == "Success"
        assert client.post(f"/api/rooms/{code}/phase/start", headers=auth(token)).status_code == 200  # 新一輪
        new = client.post("/api/rooms/recover", json={"recoveryCode": store.rooms[code].recovery_code}).json()["teacherToken"]
        with client.websocket_connect(f"/ws/teacher?token={new}&code={code}") as t2:
            snap = t2.receive_json()["room"]
        assert snap["backfills"] == m["backfills"]  # 換裝置、新一輪後舊輪紀錄仍在
    finally:
        _close(conns)
