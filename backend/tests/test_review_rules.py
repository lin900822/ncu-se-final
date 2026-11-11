"""Step 9 US3：審核的時機、權限、目標驗證、冪等與靜態審核（原則 III、SC-007、SC-009）。"""
import asyncio
import random
import re
from pathlib import Path

import pytest

from app.services import review
from app.store import store

from .conftest import auth, join_student, make_ranked_room, make_started_room, post_review
from .test_review_property import _room, _submit_all
from .test_submission_privacy import flush

APP = Path(__file__).resolve().parents[1] / "app"
UNIT = "1"


def _close(conns):
    for cm, _ws in conns:
        cm.__exit__(None, None, None)


def _code_of(resp):
    return resp.json()["error"]["code"]


# ---- 時機 ----

def test_not_allowed_while_answering_or_waiting(client, use_sheet):
    code, token, conns = make_ranked_room(client, end=False)  # 搶答中
    try:
        r = post_review(client, code, token, UNIT, "第 1 組", "invalid", "x")
        assert r.status_code == 400 and _code_of(r) == "REVIEW_NOT_ALLOWED"
        assert store.rooms[code].reviews == []
    finally:
        _close(conns)
    code2, token2 = make_started_room(client, start=False)  # 尚未開始
    r2 = post_review(client, code2, token2, UNIT, "第 1 組", "invalid", "x", round_no=0)
    assert r2.status_code == 400 and _code_of(r2) == "REVIEW_NOT_ALLOWED"


def test_only_latest_round_can_be_reviewed(client, use_sheet):
    code, token, conns = make_ranked_room(client)
    try:
        assert post_review(client, code, token, UNIT, "第 1 組", "invalid", "第一輪").json()["changed"] is True
        room = store.rooms[code]
        # 開始第二輪並讓兩組送出後結束
        assert client.post(f"/api/rooms/{code}/phase/start", headers=auth(token)).status_code == 200
        for i, (_cm, ws) in enumerate(conns[:2], start=1):
            flush(ws)
            ws.send_json({"type": "submit", "questionId": "1", "answer": f"r2-{i}"})
            flush(ws)
        assert client.post(f"/api/rooms/{code}/phase/end", headers=auth(token)).status_code == 200
        assert room.round == 2
        stale = post_review(client, code, token, UNIT, "第 2 組", "invalid", "舊輪", round_no=1)
        assert stale.status_code == 400 and _code_of(stale) == "REVIEW_NOT_ALLOWED"
        assert len(room.reviews) == 1  # 舊輪紀錄仍在、沒有新增
        ok = post_review(client, code, token, UNIT, "第 1 組", "invalid", "第二輪", round_no=2)
        assert ok.json()["changed"] is True
        assert [(r.round, r.group_name) for r in room.reviews] == [(1, "第 1 組"), (2, "第 1 組")]
        from app.services import results

        q1 = {x["questionId"]: x for x in results.build_result(room)["results"]}["1"]
        assert q1["winnerGroup"] == "第 2 組" and q1["answer"] == "r2-2"  # 只影響第二輪
    finally:
        _close(conns)


def test_not_allowed_after_room_closed(client, use_sheet):
    code, token, conns = make_ranked_room(client)
    try:
        assert client.post(f"/api/rooms/{code}/close", headers=auth(token)).status_code == 200
        r = post_review(client, code, token, UNIT, "第 1 組", "invalid", "x")
        assert r.status_code == 409 and _code_of(r) == "ROOM_CLOSED"
        assert store.rooms[code].reviews == []
    finally:
        _close(conns)


# ---- 權限 ----

def test_unauthorized_variants_rejected_without_leak(client, use_sheet):
    code, token, conns = make_ranked_room(client)
    try:
        room = store.rooms[code]
        body = {"round": 1, "unitId": UNIT, "group": "第 1 組", "action": "invalid", "reason": "x"}
        attempts = [
            client.post(f"/api/rooms/{code}/reviews", json=body),
            client.post(f"/api/rooms/{code}/reviews", json=body, headers={"Authorization": "Bearer wrong"}),
            client.post(f"/api/rooms/{code}/reviews", json=body, headers={"Authorization": "Basic abc"}),
            client.post(f"/api/rooms/{code}/reviews", json=body, headers={"Authorization": token}),  # 缺 Bearer
            client.post(f"/api/rooms/{code}/reviews?token={token}", json=body),  # 憑證放網址
        ]
        for r in attempts:
            assert r.status_code == 401 and _code_of(r) == "UNAUTHORIZED"
            assert "ans-1" not in r.text and "第 1 組" not in r.text
        assert room.reviews == []
    finally:
        _close(conns)


def test_old_credential_rejected_after_recovery(client, use_sheet):
    code, token, conns = make_ranked_room(client)
    try:
        new = client.post("/api/rooms/recover", json={"recoveryCode": store.rooms[code].recovery_code}).json()["teacherToken"]
        old_try = post_review(client, code, token, UNIT, "第 1 組", "invalid", "x")
        assert old_try.status_code == 401 and store.rooms[code].reviews == []
        assert post_review(client, code, new, UNIT, "第 1 組", "invalid", "x").status_code == 200
    finally:
        _close(conns)


# ---- 目標驗證 ----

def test_target_and_action_validation(client, use_sheet):
    code, token, conns = make_ranked_room(client, groups=("第 1 組", "第 2 組"))
    try:
        room = store.rooms[code]
        cases = [
            (("99", "第 1 組", "invalid"), "UNIT_NOT_FOUND"),
            ((UNIT, "不存在的組", "invalid"), "REVIEW_TARGET_NOT_FOUND"),
            (("2", "第 1 組", "invalid"), "REVIEW_TARGET_NOT_FOUND"),  # Q2 沒人送出
            ((UNIT, "第 1 組", "delete"), "BAD_REQUEST"),
        ]
        for (unit, group, action), expected in cases:
            r = post_review(client, code, token, unit, group, action, "理由")
            assert r.status_code == 400 and _code_of(r) == expected, (unit, group, action)
        assert room.reviews == []
    finally:
        _close(conns)


# ---- 冪等與併發 ----

def test_duplicate_review_returns_unchanged(client, use_sheet):
    code, token, conns = make_ranked_room(client)
    try:
        room = store.rooms[code]
        first = post_review(client, code, token, UNIT, "第 1 組", "invalid", "答案錯誤")
        again = post_review(client, code, token, UNIT, "第 1 組", "invalid", "答案錯誤")
        assert first.json()["changed"] is True and again.json()["changed"] is False
        assert len(room.reviews) == 1
        not_invalid = post_review(client, code, token, UNIT, "第 2 組", "valid", "沒被駁回")  # 有效再恢復
        assert not_invalid.json()["changed"] is False and len(room.reviews) == 1
    finally:
        _close(conns)


def test_concurrent_duplicate_reviews_record_exactly_one_100_times():
    async def run():
        for seed in range(100):
            rng = random.Random(seed)
            room, groups = _room(3, bundled=False)
            _submit_all(room, groups, False, rng)
            name = groups[0].name

            async def go():
                await asyncio.sleep(0)
                return review.apply_review(room, round_no=1, unit_id="1", group=name, action="invalid", reason="亂填")

            res = await asyncio.gather(go(), go(), go())
            assert sum(1 for _rec, changed in res if changed) == 1
            assert len(room.reviews) == 1

    asyncio.run(run())


# ---- 靜態審核 ----

def test_static_scan_review_service_only_used_by_teacher_route():
    pattern = re.compile(r"^\s*from\s+\S*services\s+import\s+.*\breview\b|^\s*from\s+\S*services\.review\s+import", re.M)
    users = []
    for path in APP.rglob("*.py"):
        if path.name == "review.py":
            continue
        if pattern.search(path.read_text(encoding="utf-8")):
            users.append(path.relative_to(APP).as_posix())
    assert users == ["api/rooms.py"]
    for f in ("api/ws.py", "realtime.py", "services/groups.py", "services/submissions.py", "services/phase.py"):
        text = (APP / f).read_text(encoding="utf-8")
        assert not re.search(r"\bservices\.review\b|import .*\breview\b", text), f
