import csv
import io
from pathlib import Path

import pytest
from starlette.testclient import TestClient

from app.main import app
from app.services import sheets as sheets_service
from app.realtime import realtime
from app.store import store

from .grid_helper import xlsx_to_grid

FIX = Path(__file__).parent / "fixtures"
SHEET_URL = "https://docs.google.com/spreadsheets/d/abc123/edit#gid=0"


@pytest.fixture
def client():
    store.rooms.clear()
    store.recovery_index.clear()
    realtime.teachers.clear()
    realtime.students.clear()
    with TestClient(app) as c:
        yield c


def create_room(client: TestClient) -> tuple[str, str]:
    r = client.post("/api/rooms")
    assert r.status_code == 201
    body = r.json()
    return body["code"], body["teacherToken"]


def auth(token: str) -> dict:
    return {"Authorization": f"Bearer {token}"}


def join_student(client: TestClient, code: str, name: str):
    """回傳 (context manager 已進入的 websocket, joined 訊息)。呼叫端須自行 close。"""
    cm = client.websocket_connect("/ws/student")
    ws = cm.__enter__()
    ws.send_json({"type": "join", "code": code, "name": name})
    msg = ws.receive_json()
    return cm, ws, msg


@pytest.fixture
def use_sheet(monkeypatch):
    """讓讀取試算表改為回傳範例檔的格線（不連 Google）。回傳可切換檔案的函式。"""
    state = {"name": "single.xlsx"}

    async def fake_fetch(spreadsheet_id, gid):
        grid, title = xlsx_to_grid(FIX / state["name"])
        return grid, title, 0

    monkeypatch.setattr(sheets_service, "_fetch", fake_fetch)

    def switch(name):
        state["name"] = name

    return switch


def make_started_room(client, start=True):
    """建立含題目（單題範例 Q1～Q6）的房間，預設開始搶答。回傳 (code, teacher_token)。"""
    p = client.post("/api/sheets/preview", json={"url": SHEET_URL}).json()
    body = client.post(
        "/api/rooms", json={"sheetUrl": SHEET_URL, "fingerprint": p["fingerprint"]}
    ).json()
    code, token = body["code"], body["teacherToken"]
    if start:
        assert client.post(f"/api/rooms/{code}/phase/start", headers=auth(token)).status_code == 200
    return code, token


def make_bundle_room(client, bundles=(("3", "4"),), start=True):
    """建立含題目（單題範例 Q1～Q6）且帶題組的房間。回傳 (code, teacher_token, 建立回應)。"""
    p = client.post("/api/sheets/preview", json={"url": SHEET_URL}).json()
    r = client.post(
        "/api/rooms",
        json={
            "sheetUrl": SHEET_URL,
            "fingerprint": p["fingerprint"],
            "bundles": [list(b) for b in bundles],
        },
    )
    assert r.status_code == 201, r.json()
    body = r.json()
    code, token = body["code"], body["teacherToken"]
    if start:
        assert client.post(f"/api/rooms/{code}/phase/start", headers=auth(token)).status_code == 200
    return code, token, body


def get_export(client, code, token=None, params=None):
    """匯出紀錄：GET /api/rooms/{code}/records.csv；憑證只放標頭。"""
    headers = auth(token) if token else {}
    return client.get(f"/api/rooms/{code}/records.csv", headers=headers, params=params)


def parse_csv(response) -> list[list[str]]:
    """以 utf-8-sig 解碼並用 csv 解析（含標題列）。"""
    text = response.content.decode("utf-8-sig")
    return list(csv.reader(io.StringIO(text, newline="")))


def post_review(client, code, token, unit_id, group, action, reason, round_no=None):
    """老師審核（駁回／恢復）：POST /api/rooms/{code}/reviews；憑證只放標頭。"""
    if round_no is None:
        from app.store import store

        round_no = store.rooms[code].round if code in store.rooms else 1
    headers = auth(token) if token else {}
    return client.post(
        f"/api/rooms/{code}/reviews",
        headers=headers,
        json={"round": round_no, "unitId": unit_id, "group": group, "action": action, "reason": reason},
    )


def make_ranked_room(client, bundles=(), groups=("第 1 組", "第 2 組", "第 3 組"), end=True):
    """建立含題目的房間並開始搶答；各組加入後由第 1 組開始依序對 Q1 送出（答案 ans-<組序>）。
    end=True 時再結束搶答。回傳 (code, token, connections)；connections 為 [(context manager, ws)]，呼叫端負責關閉。"""
    from .test_submission_privacy import flush

    if bundles:
        code, token, _ = make_bundle_room(client, bundles=bundles)
    else:
        code, token = make_started_room(client)
    conns = []
    for i, name in enumerate(groups, start=1):
        cm, ws, _ = join_student(client, code, name)
        conns.append((cm, ws))
    for i, (_cm, ws) in enumerate(conns, start=1):
        ws.send_json({"type": "submit", "questionId": "1", "answer": f"ans-{i}"})
        flush(ws)
    if end:
        assert client.post(f"/api/rooms/{code}/phase/end", headers=auth(token)).status_code == 200
    return code, token, conns


def drain(ws, n):
    """依序讀取 n 則訊息。"""
    return [ws.receive_json() for _ in range(n)]
