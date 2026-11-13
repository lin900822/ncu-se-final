"""Step 7 US4：進度板與結果以題組為單位一致；領先題數以題數計。"""
from app.services import ranking
from app.store import store

from .conftest import auth, join_student, make_bundle_room
from .test_submission_privacy import flush


def _send(ws, answers, bundle_id="B1"):
    ws.send_json({"type": "submit_bundle", "bundleId": bundle_id, "answers": answers})
    flush(ws)


def test_board_and_result_consistent_for_bundle(client, use_sheet):
    code, token, _ = make_bundle_room(client, bundles=[["3", "4"], ["5", "6"]])
    a, wa, _ = join_student(client, code, "第 1 組")
    b, wb, _ = join_student(client, code, "第 2 組")
    try:
        _send(wa, {"3": "A3", "4": "A4"})
        _send(wb, {"3": "B3", "4": "B4"})
        room = store.rooms[code]
        board = ranking.build_board(room)
        q = {x["questionId"]: x for x in board["questions"]}
        # (a) 題組各題 leader 與名次清單相同，且帶 bundleId
        assert q["3"]["leader"] == q["4"]["leader"] == "第 1 組"
        # 同題組各題的名次清單相同（每筆另帶各題自己的答案，所以比較時排除 answer）
        strip = lambda rows: [{k: v for k, v in r.items() if k != "answer"} for r in rows]  # noqa: E731
        assert strip(q["3"]["ranking"]) == strip(q["4"]["ranking"])
        assert [r["rank"] for r in q["3"]["ranking"]] == [1, 2]
        assert q["3"]["bundleId"] == q["4"]["bundleId"] == "B1"
        assert q["5"]["bundleId"] == "B2" and q["1"]["bundleId"] is None
        # (b) 領先題數以題數計：2 題題組計 2；再搶下一題單題變 3
        assert {t["group"]: t["leadCount"] for t in board["leadTally"]} == {"第 1 組": 2}
        wa.send_json({"type": "submit", "questionId": "1", "answer": "A1"})
        flush(wa)
        tally = {t["group"]: t["leadCount"] for t in ranking.build_board(room)["leadTally"]}
        assert tally == {"第 1 組": 3}
        # (d) 老師快照
        with client.websocket_connect(f"/ws/teacher?token={token}&code={code}") as t:
            snap = t.receive_json()["room"]
            assert {s["questionId"]: s["bundleId"] for s in snap["submissions"]} == {
                "3": "B1", "4": "B1", "1": None
            }
            assert snap["board"]["questions"][2]["bundleId"] == "B1"
        # (c) 結算：題組各題同一搶下組別、答案各自；無人送出的題組為 None
        assert client.post(f"/api/rooms/{code}/phase/end", headers=auth(token)).status_code == 200
        while True:
            m = wb.receive_json()
            if m["type"] == "round_result":
                break
        res = {r["questionId"]: r for r in m["results"]}
        assert res["3"]["winnerGroup"] == res["4"]["winnerGroup"] == "第 1 組"
        assert (res["3"]["answer"], res["4"]["answer"]) == ("A3", "A4")
        assert res["5"]["winnerGroup"] is None and res["6"]["winnerGroup"] is None
    finally:
        for x in (a, b):
            x.__exit__(None, None, None)
