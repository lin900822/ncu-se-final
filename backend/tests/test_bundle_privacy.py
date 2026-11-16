"""Step 7 US3：題組送出的同組同步、他組保密（原則 III）、老師事件與重連還原。"""
import json

from .conftest import auth, join_student, make_bundle_room
from .test_submission_privacy import flush

ANSWERS = {"3": "中央處理器", "4": "主記憶體"}


def dumps(o):
    return json.dumps(o, ensure_ascii=False)


def test_bundle_sync_privacy_and_teacher_events(client, use_sheet):
    code, token, _ = make_bundle_room(client)
    with client.websocket_connect(f"/ws/teacher?token={token}&code={code}") as t:
        t.receive_json()  # snapshot
        a1, wa1, _ = join_student(client, code, "甲組")
        a2, wa2, _ = join_student(client, code, "甲組")
        b, wb, _ = join_student(client, code, "乙組")
        try:
            wa1.send_json({"type": "submit_bundle", "bundleId": "B1", "answers": ANSWERS})
            got_a1, got_a2, got_b = flush(wa1), flush(wa2), flush(wb)
            expected = {"type": "bundle_submitted", "bundleId": "B1", "answers": ANSWERS, "round": 1}
            # (a) 同組兩個視窗都收到同一則整組已送出
            assert expected in got_a1 and expected in got_a2
            # (b) 他組只收到匿名提示，且完全不含組名、答案、名次與老師事件
            hints = [m for m in got_b if m["type"] == "bundle_hint"]
            assert hints == [{"type": "bundle_hint", "bundleId": "B1", "round": 1}]
            assert set(hints[0]) == {"type", "bundleId", "round"}
            text = dumps(got_b)
            for word in ["甲組", *ANSWERS.values(), "bundle_submitted", "submission", "board", "rank"]:
                assert word not in text, word
            # (c) 老師：兩則 submission（同時間、同名次）＋一則看板
            teacher = []
            while len(teacher) < 3:
                m = t.receive_json()
                if m["type"] in ("submission", "board"):
                    teacher.append(m)
            subs = [m for m in teacher if m["type"] == "submission"]
            assert [m["questionId"] for m in subs] == ["3", "4"]
            assert all(m["bundleId"] == "B1" and m["group"] == "甲組" for m in subs)
            assert subs[0]["submittedAt"] == subs[1]["submittedAt"]
            assert subs[0]["rank"] == subs[1]["rank"] == 1
            assert teacher[-1]["type"] == "board"
        finally:
            for x in (a1, a2, b):
                x.__exit__(None, None, None)

    # (d) 重連還原：本組含全部成員；他組只知道有人送出
    c, _, ja = join_student(client, code, "甲組")
    d, _, jb = join_student(client, code, "乙組")
    try:
        assert ja["mySubmissions"] == ANSWERS
        assert set(jb["submittedByOthers"]) >= {"3", "4"}
        assert jb["mySubmissions"] == {}
        assert "甲組" not in dumps(jb) and "中央處理器" not in dumps(jb)
    finally:
        for x in (c, d):
            x.__exit__(None, None, None)

    # (e) 新一輪：已送出清空、題組設定不變
    assert client.post(f"/api/rooms/{code}/phase/end", headers=auth(token)).status_code == 200
    assert client.post(f"/api/rooms/{code}/phase/start", headers=auth(token)).status_code == 200
    e, _, je = join_student(client, code, "甲組")
    try:
        assert je["mySubmissions"] == {}
        assert je["bundles"] == [{"id": "B1", "questionIds": ["3", "4"]}]
    finally:
        e.__exit__(None, None, None)
