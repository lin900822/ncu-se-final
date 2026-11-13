"""Step 7 US1：建立房間時設定題組（驗證、編號、下發）。"""
import pytest

from app.store import store

from .conftest import SHEET_URL, auth, join_student, make_bundle_room, make_started_room


def _create(client, bundles, sheet=True):
    body = {"bundles": bundles}
    if sheet:
        p = client.post("/api/sheets/preview", json={"url": SHEET_URL}).json()
        body.update({"sheetUrl": SHEET_URL, "fingerprint": p["fingerprint"]})
    return client.post("/api/rooms", json=body)


def test_bundle_created_in_question_order(client, use_sheet):
    _, _, body = make_bundle_room(client, bundles=[["4", "3"]], start=False)
    assert body["bundles"] == [{"id": "B1", "questionIds": ["3", "4"]}]


def test_bundles_numbered_by_first_member(client, use_sheet):
    _, _, body = make_bundle_room(client, bundles=[["5", "6"], ["1", "2"]], start=False)
    assert body["bundles"] == [
        {"id": "B1", "questionIds": ["1", "2"]},
        {"id": "B2", "questionIds": ["5", "6"]},
    ]


@pytest.mark.parametrize(
    "bundles, reason",
    [
        ([["3"]], "TOO_FEW"),
        ([["3", "3"]], "OVERLAP"),
        ([["2", "5"]], "NOT_ADJACENT"),
        ([["3", "4"], ["4", "5"]], "OVERLAP"),
        ([["3", "99"]], "UNKNOWN_QUESTION"),
    ],
)
def test_invalid_bundles_rejected_without_room(client, use_sheet, bundles, reason):
    before = len(store.rooms)
    r = _create(client, bundles)
    assert r.status_code == 400
    e = r.json()["error"]
    assert e["code"] == "BUNDLES_INVALID"
    assert e["details"]["reason"] == reason
    assert len(store.rooms) == before


def test_bundles_without_sheet_rejected(client):
    r = _create(client, [["1", "2"]], sheet=False)
    assert r.status_code == 400
    e = r.json()["error"]
    assert e["code"] == "BUNDLES_INVALID" and e["details"]["reason"] == "NO_QUESTIONS"
    assert len(store.rooms) == 0


def test_adjacent_subquestions_can_be_bundled(client, use_sheet):
    use_sheet("group.xlsx")
    _, _, body = make_bundle_room(client, bundles=[["1-2", "2-1"]], start=False)
    assert body["bundles"] == [{"id": "B1", "questionIds": ["1-2", "2-1"]}]


def test_bundles_sent_to_students_and_teacher(client, use_sheet):
    code, token, body = make_bundle_room(client, start=False)
    cm, ws, joined = join_student(client, code, "第 1 組")
    try:
        assert joined["bundles"] == body["bundles"] == [{"id": "B1", "questionIds": ["3", "4"]}]
    finally:
        cm.__exit__(None, None, None)
    with client.websocket_connect(f"/ws/teacher?token={token}&code={code}") as t:
        snap = t.receive_json()
        assert snap["room"]["bundles"] == body["bundles"]
    # 以恢復碼回復後設定不變
    rec = client.post("/api/rooms/recover", json={"recoveryCode": body["recoveryCode"]}).json()
    with client.websocket_connect(f"/ws/teacher?token={rec['teacherToken']}&code={code}") as t:
        assert t.receive_json()["room"]["bundles"] == body["bundles"]


def test_no_bundles_is_empty_list(client, use_sheet):
    code, token = make_started_room(client, start=False)
    cm, ws, joined = join_student(client, code, "第 1 組")
    try:
        assert joined["bundles"] == []
    finally:
        cm.__exit__(None, None, None)
    with client.websocket_connect(f"/ws/teacher?token={token}&code={code}") as t:
        assert t.receive_json()["room"]["bundles"] == []
    assert client.post(f"/api/rooms/{code}/phase/start", headers=auth(token)).status_code == 200
