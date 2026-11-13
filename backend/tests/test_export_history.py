"""Step 8 US2：多輪、題組、排序、與老師端逐筆一致、唯讀、規模。"""
import time
from datetime import datetime, timezone

from app.models import Group, Question, iso
from app.services import export, ranking, rooms, submissions
from app.store import store

from .conftest import auth, get_export, join_student, make_bundle_room, make_started_room, parse_csv
from .test_submission_privacy import flush


def _single(ws, qid, answer):
    ws.send_json({"type": "submit", "questionId": qid, "answer": answer})
    return flush(ws)


def _bundle(ws, answers, bundle_id="B1"):
    ws.send_json({"type": "submit_bundle", "bundleId": bundle_id, "answers": answers})
    return flush(ws)


def test_multiple_rounds_all_exported_and_sorted(client, use_sheet):
    code, token = make_started_room(client)
    a, wa, _ = join_student(client, code, "第 1 組")
    b, wb, _ = join_student(client, code, "第 2 組")
    try:
        _single(wb, "2", "r1-乙-Q2")
        _single(wa, "1", "r1-甲-Q1")
        _single(wb, "1", "r1-乙-Q1")
        assert client.post(f"/api/rooms/{code}/phase/end", headers=auth(token)).status_code == 200
        assert client.post(f"/api/rooms/{code}/phase/start", headers=auth(token)).status_code == 200
        _single(wb, "1", "r2-乙-Q1")
        _single(wa, "1", "r2-甲-Q1")
        rows = parse_csv(get_export(client, code, token))[1:]
        assert [(r[0], r[1], r[3], r[6]) for r in rows] == [
            ("1", "Q1", "第 1 組", "1"),
            ("1", "Q1", "第 2 組", "2"),
            ("1", "Q2", "第 2 組", "1"),
            ("2", "Q1", "第 2 組", "1"),
            ("2", "Q1", "第 1 組", "2"),
        ]
    finally:
        for cm in (a, b):
            cm.__exit__(None, None, None)


def test_bundle_rows_share_group_time_rank_and_label(client, use_sheet):
    code, token, _ = make_bundle_room(client)
    a, wa, _ = join_student(client, code, "第 1 組")
    b, wb, _ = join_student(client, code, "第 2 組")
    try:
        _single(wa, "1", "單題")
        _bundle(wa, {"3": "甲3", "4": "甲4"})
        _bundle(wb, {"3": "乙3", "4": "乙4"})
        rows = parse_csv(get_export(client, code, token))[1:]
        # 排序：題目順序 → 名次；題組各題成員列相鄰
        assert [(r[1], r[3], r[6]) for r in rows] == [
            ("Q1", "第 1 組", "1"),
            ("Q3", "第 1 組", "1"),
            ("Q3", "第 2 組", "2"),
            ("Q4", "第 1 組", "1"),
            ("Q4", "第 2 組", "2"),
        ]
        assert rows[0][2] == ""  # 未綁定題目題組欄為空
        assert {r[2] for r in rows[1:]} == {"Q3、Q4"}
        # 同一次題組送出：時間相同
        by = {(r[1], r[3]): r for r in rows}
        assert by[("Q3", "第 1 組")][5] == by[("Q4", "第 1 組")][5]
        assert by[("Q3", "第 2 組")][5] == by[("Q4", "第 2 組")][5]
        # 題組各題一定同時出現
        assert sum(1 for r in rows if r[1] == "Q3") == sum(1 for r in rows if r[1] == "Q4")
        assert "B1" not in "".join(",".join(r) for r in rows)
    finally:
        for cm in (a, b):
            cm.__exit__(None, None, None)


def test_matches_teacher_snapshot_and_board(client, use_sheet):
    code, token, _ = make_bundle_room(client)
    a, wa, _ = join_student(client, code, "第 1 組")
    b, wb, _ = join_student(client, code, "第 2 組")
    try:
        _single(wb, "1", "乙1")
        _single(wa, "1", "甲1")
        _bundle(wa, {"3": "甲3", "4": "甲4"})
        _single(wb, "5", "乙5")
        rows = parse_csv(get_export(client, code, token))[1:]
        room = store.rooms[code]
        assert len(rows) == len(room.submissions)  # 不缺漏、不多出
        assert len({(r[0], r[1], r[3]) for r in rows}) == len(rows)  # 不重複
        with client.websocket_connect(f"/ws/teacher?token={token}&code={code}") as t:
            snap = t.receive_json()["room"]
        label = {q["id"]: q["label"] for q in snap["questions"]}
        from_snap = sorted(
            (str(s["round"]), label[s["questionId"]], s["group"], s["answer"], s["submittedAt"], str(s["rank"]))
            for s in snap["submissions"]
        )
        from_csv = sorted((r[0], r[1], r[3], r[4], r[5], r[6]) for r in rows)
        assert from_csv == from_snap
        # 與進度板名次一致
        board = ranking.build_board(room)
        for q in board["questions"]:
            expect = [(x["rank"], x["group"]) for x in q["ranking"]]
            got = [(int(r[6]), r[3]) for r in rows if r[1] == label[q["questionId"]]]
            assert got == expect
    finally:
        for cm in (a, b):
            cm.__exit__(None, None, None)


def test_rejected_submissions_not_exported(client, use_sheet):
    code, token = make_started_room(client)
    a, wa, _ = join_student(client, code, "第 1 組")
    try:
        _single(wa, "1", "   ")  # 空白
        _single(wa, "1", "x" * 501)  # 超長
        _single(wa, "1", "有效")
        _single(wa, "1", "重複")  # 重複送出
        rows = parse_csv(get_export(client, code, token))[1:]
        assert [r[4] for r in rows] == ["有效"]
        client.post(f"/api/rooms/{code}/phase/end", headers=auth(token))
        _single(wa, "2", "結束後")  # 非搶答中
        assert [r[4] for r in parse_csv(get_export(client, code, token))[1:]] == ["有效"]
    finally:
        a.__exit__(None, None, None)


def test_export_is_read_only_and_repeatable(client, use_sheet):
    code, token = make_started_room(client)
    a, wa, _ = join_student(client, code, "第 1 組")
    try:
        _single(wa, "1", "答")
        room = store.rooms[code]
        before = (len(room.submissions), room.next_seq, dict(room.rank_counts), room.last_activity_at)
        first = get_export(client, code, token).content
        for _ in range(9):
            assert get_export(client, code, token).content == first
        after = (len(room.submissions), room.next_seq, dict(room.rank_counts), room.last_activity_at)
        assert before == after
    finally:
        a.__exit__(None, None, None)


def test_max_scale_6000_rows_fast():
    room = rooms.create_room()
    room.questions = [Question(id=str(i), number=i, sub=None, label=f"Q{i}", cell=f"A{i}") for i in range(1, 51)]
    groups = []
    for i in range(40):
        g = Group(name=f"第 {i + 1} 組", normalized_name=f"g{i}", online=True, joined_at=datetime.now(timezone.utc))
        room.groups[g.normalized_name] = g
        groups.append(g)
    for rnd in (1, 2, 3):
        room.round, room.phase = rnd, "Answering"
        for g in groups:
            for q in room.questions:
                submissions.submit(room, g, q.id, f"答案-{rnd}-{g.name}-{q.id}")
    assert len(room.submissions) == 6000
    t0 = time.perf_counter()
    text = export.render_csv(room)
    elapsed = time.perf_counter() - t0
    assert elapsed < 1.0, elapsed
    assert text.count("\r\n") == 6001  # 標題列 + 6000 列
    assert iso(room.submissions[0].submitted_at) in text
