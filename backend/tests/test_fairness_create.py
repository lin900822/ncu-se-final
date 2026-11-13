"""Step 11 US1：建立房間時設定公平規則（驗證、下發、固定不可改）。"""
import pytest

from app.main import app
from app.store import store

from .conftest import SHEET_URL, auth, join_student


def _create(client, fairness="OMIT", sheet=True, **extra):
    body = dict(extra)
    if sheet:
        p = client.post("/api/sheets/preview", json={"url": SHEET_URL}).json()
        body.update({"sheetUrl": SHEET_URL, "fingerprint": p["fingerprint"]})
    if fairness != "OMIT":
        body["fairness"] = fairness
    return client.post("/api/rooms", json=body)


def _joined(client, code):
    cm, _ws, joined = join_student(client, code, "第 1 組")
    cm.__exit__(None, None, None)
    return joined


def _snapshot(client, code, token):
    with client.websocket_connect(f"/ws/teacher?token={token}&code={code}") as t:
        return t.receive_json()["room"]


def test_rule_is_created_and_published_to_everyone(client, use_sheet):
    r = _create(client, {"winCap": 2, "cooldownSeconds": 30})
    assert r.status_code == 201
    body = r.json()
    rule = {"winCap": 2, "cooldownSeconds": 30}
    assert body["fairness"] == rule
    code, token = body["code"], body["teacherToken"]
    assert _joined(client, code)["fairness"] == rule  # 學生
    assert _snapshot(client, code, token)["fairness"] == rule  # 老師
    rec = client.post("/api/rooms/recover", json={"recoveryCode": body["recoveryCode"]}).json()
    assert _snapshot(client, code, rec["teacherToken"])["fairness"] == rule  # 換裝置後仍相同


@pytest.mark.parametrize(
    "fairness",
    ["OMIT", None, {}, {"winCap": None, "cooldownSeconds": 0}, {"winCap": None}, {"cooldownSeconds": None}],
)
def test_default_means_no_limit(client, use_sheet, fairness):
    r = _create(client, fairness)
    assert r.status_code == 201 and r.json()["fairness"] is None
    code, token = r.json()["code"], r.json()["teacherToken"]
    assert _joined(client, code)["fairness"] is None
    assert _snapshot(client, code, token)["fairness"] is None
    assert store.rooms[code].fairness.win_cap is None and store.rooms[code].fairness.cooldown_seconds == 0


def test_cap_equal_to_question_count_is_allowed(client, use_sheet):
    r = _create(client, {"winCap": 6, "cooldownSeconds": 600})
    assert r.status_code == 201 and r.json()["fairness"] == {"winCap": 6, "cooldownSeconds": 600}


@pytest.mark.parametrize(
    "fairness, reason",
    [
        ({"winCap": 0}, "WIN_CAP_RANGE"),
        ({"winCap": -1}, "WIN_CAP_RANGE"),
        ({"winCap": 7}, "WIN_CAP_RANGE"),  # 大於題目數
        ({"cooldownSeconds": -1}, "COOLDOWN_RANGE"),
        ({"cooldownSeconds": 601}, "COOLDOWN_RANGE"),
        ({"winCap": "2"}, "TYPE"),
        ({"winCap": 2.5}, "TYPE"),
        ({"winCap": True}, "TYPE"),
        ({"cooldownSeconds": "30"}, "TYPE"),
        ({"cooldownSeconds": 1.5}, "TYPE"),
        ({"cooldownSeconds": False}, "TYPE"),
        ("abc", "TYPE"),
    ],
)
def test_invalid_rules_rejected_and_no_room_created(client, use_sheet, fairness, reason):
    before = len(store.rooms)
    r = _create(client, fairness)
    assert r.status_code == 400
    e = r.json()["error"]
    assert e["code"] == "FAIRNESS_INVALID" and e["details"]["reason"] == reason
    assert len(store.rooms) == before


@pytest.mark.parametrize("fairness", [{"winCap": 1}, {"cooldownSeconds": 5}])
def test_rule_without_questions_is_rejected(client, fairness):
    r = _create(client, fairness, sheet=False)
    assert r.status_code == 400 and r.json()["error"]["details"]["reason"] == "NO_QUESTIONS"
    assert len(store.rooms) == 0
    assert _create(client, "OMIT", sheet=False).status_code == 201  # 沒有規則的無試算表房間仍可建立


def test_validation_order_sheet_and_bundles_come_first(client, use_sheet):
    bad = {"winCap": 99}
    p = client.post("/api/sheets/preview", json={"url": SHEET_URL}).json()
    r = client.post("/api/rooms", json={"sheetUrl": SHEET_URL, "fingerprint": "wrong", "fairness": bad})
    assert r.status_code == 409 and r.json()["error"]["code"] == "SHEET_CHANGED"
    r2 = client.post(
        "/api/rooms",
        json={"sheetUrl": SHEET_URL, "fingerprint": p["fingerprint"], "bundles": [["3"]], "fairness": bad},
    )
    assert r2.status_code == 400 and r2.json()["error"]["code"] == "BUNDLES_INVALID"
    assert len(store.rooms) == 0


def test_rule_is_fixed_for_the_life_of_the_room(client, use_sheet):
    r = _create(client, {"winCap": 2, "cooldownSeconds": 10})
    code, token = r.json()["code"], r.json()["teacherToken"]
    rule = {"winCap": 2, "cooldownSeconds": 10}
    for path in ("start", "end", "start", "end"):
        assert client.post(f"/api/rooms/{code}/phase/{path}", headers=auth(token)).status_code == 200
        assert _joined(client, code)["fairness"] == rule
        assert _snapshot(client, code, token)["fairness"] == rule
    assert not any("fairness" in getattr(route, "path", "") for route in app.routes)  # 沒有任何修改規則的端點
