"""Step 8 US3：只有持有效老師憑證者能匯出（原則 III）。"""
import json
import re
from pathlib import Path

import pytest

from .conftest import get_export, join_student, make_started_room, parse_csv
from .test_submission_privacy import flush

APP = Path(__file__).resolve().parents[1] / "app"
SECRET_ANSWER = "機密答案XYZ"
SECRET_GROUP = "機密組"


def _setup(client):
    code, token = make_started_room(client)
    cm, ws, _ = join_student(client, code, SECRET_GROUP)
    ws.send_json({"type": "submit", "questionId": "1", "answer": SECRET_ANSWER})
    msgs = flush(ws)
    return code, token, cm, ws, msgs


def _assert_denied(r):
    assert r.status_code == 401
    assert r.json()["error"]["code"] == "UNAUTHORIZED"
    assert SECRET_ANSWER not in r.text and SECRET_GROUP not in r.text


def test_missing_or_wrong_credentials_rejected(client, use_sheet):
    code, token, cm, _, _ = _setup(client)
    try:
        _assert_denied(get_export(client, code))  # 只知道房間代碼
        _assert_denied(get_export(client, code, "wrong"))
        _assert_denied(client.get(f"/api/rooms/{code}/records.csv", headers={"Authorization": "Basic abc"}))
        _assert_denied(client.get(f"/api/rooms/{code}/records.csv", headers={"Authorization": token}))  # 缺 Bearer
        assert get_export(client, code, token).status_code == 200
    finally:
        cm.__exit__(None, None, None)


@pytest.mark.parametrize("param", ["token", "authorization", "teacherToken", "access_token"])
def test_credential_in_url_is_ignored(client, use_sheet, param):
    code, token, cm, _, _ = _setup(client)
    try:
        r = client.get(f"/api/rooms/{code}/records.csv", params={param: token})
        _assert_denied(r)
    finally:
        cm.__exit__(None, None, None)


def test_old_credential_invalid_after_recovery_new_works(client, use_sheet):
    code, token, cm, _, _ = _setup(client)
    try:
        recovery = client.post(
            "/api/rooms/recover", json={"recoveryCode": _recovery_of(code)}
        ).json()
        new_token = recovery["teacherToken"]
        assert new_token != token
        _assert_denied(get_export(client, code, token))  # 舊憑證失效
        r = get_export(client, code, new_token)
        assert r.status_code == 200
        rows = parse_csv(r)
        assert rows[1][3] == SECRET_GROUP and rows[1][4] == SECRET_ANSWER  # 新裝置可匯出完整紀錄
    finally:
        cm.__exit__(None, None, None)


def _recovery_of(code):
    from app.store import store

    return store.rooms[code].recovery_code


def test_students_never_receive_export_content(client, use_sheet):
    code, token, cm, ws, msgs = _setup(client)
    try:
        # 學生嘗試用 WebSocket 要求匯出：被忽略，不回傳紀錄
        ws.send_json({"type": "export"})
        ws.send_json({"type": "records"})
        more = flush(ws)
        get_export(client, code, token)  # 老師匯出期間
        more += flush(ws)
        text = json.dumps(msgs + more, ensure_ascii=False)
        for word in ("records.csv", "輪次,題號", "接收時間", "export"):
            assert word not in text, word
    finally:
        cm.__exit__(None, None, None)


def test_static_scan_export_only_used_by_teacher_http_route():
    """審查：匯出服務只被老師 HTTP 路由引用，學生 WebSocket 與廣播路徑不得引用。"""
    users = []
    pattern = re.compile(r"^\s*from\s+\S*services\s+import\s+.*\bexport\b|^\s*from\s+\S*services\.export\s+import", re.M)
    for path in APP.rglob("*.py"):
        if path.name == "export.py":
            continue
        if pattern.search(path.read_text(encoding="utf-8")):
            users.append(path.relative_to(APP).as_posix())
    assert users == ["api/rooms.py"]
    for f in ("api/ws.py", "realtime.py", "services/groups.py", "services/phase.py", "services/submissions.py"):
        assert "export" not in (APP / f).read_text(encoding="utf-8"), f
