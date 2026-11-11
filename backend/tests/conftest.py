import csv
import io
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest
from starlette.testclient import TestClient

from app.main import app
from app.services import backfill as backfill_service
from app.services import submissions as submissions_service
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


class FakeSheet:
    """測試用可讀可寫的記憶體試算表：取代對 Google 的讀取與回填寫入（不連網）。"""

    def __init__(self, name="single.xlsx"):
        self.sheet_id = 0
        self.writes: list[list[tuple]] = []  # 每次批次寫入的 updates
        self.fail_next = None  # 設為 AppError：下一次寫入丟出且不套用任何更新
        self.use(name)

    def use(self, name):
        self.grid, self.title = xlsx_to_grid(FIX / name)

    def snapshot(self):
        return [list(r) for r in self.grid.rows]

    def set_cell(self, row, col, text):
        """模擬老師手動編輯某格。"""
        while len(self.grid.rows) <= row:
            self.grid.rows.append([])
        line = self.grid.rows[row]
        while len(line) <= col:
            line.append("")
        line[col] = text

    def insert_row(self, at):
        """在第 at 列（0 起算）前插入空列，並同步位移合併範圍（模擬老師改了試算表結構）。"""
        self.grid.rows.insert(at, [])
        merges = []
        for r0, r1, c0, c1 in self.grid.merges:
            if r0 >= at:
                merges.append((r0 + 1, r1 + 1, c0, c1))
            elif r1 > at:
                merges.append((r0, r1 + 1, c0, c1))
            else:
                merges.append((r0, r1, c0, c1))
        self.grid.merges = merges

    async def fetch(self, spreadsheet_id, gid):
        return self.grid, self.title, self.sheet_id

    async def write_batch(self, spreadsheet_id, sheet_id, updates):
        if self.fail_next is not None:
            e, self.fail_next = self.fail_next, None
            raise e
        self.writes.append(list(updates))
        for row, col, text in updates:  # 原子套用：None 清為空字串，其餘設為該字串
            self.set_cell(row, col, "" if text is None else text)


@pytest.fixture
def fake_sheet(monkeypatch):
    """可讀可寫的假試算表（取代 use_sheet）；回傳 FakeSheet，可 .use("group.xlsx") 切換範例檔。"""
    fs = FakeSheet()
    monkeypatch.setattr(sheets_service, "_fetch", fs.fetch)
    monkeypatch.setattr(backfill_service, "_write_batch", fs.write_batch, raising=False)
    return fs


def post_backfill(client, code, token, round_no=None, preview=False):
    """回填：POST /api/rooms/{code}/backfill[/preview]；憑證只放標頭。"""
    if round_no is None:
        from app.store import store

        round_no = store.rooms[code].round if code in store.rooms else 1
    headers = auth(token) if token else {}
    path = f"/api/rooms/{code}/backfill" + ("/preview" if preview else "")
    return client.post(path, headers=headers, json={"round": round_no})


class Clock:
    """測試用可控的後端時鐘：fake_clock.set(秒) 讓之後的送出以「基準時間＋秒」作為 submitted_at。"""

    BASE = datetime(2026, 1, 1, tzinfo=timezone.utc)

    def __init__(self):
        self.now = self.BASE

    def set(self, seconds: float):
        self.now = self.BASE + timedelta(seconds=seconds)


@pytest.fixture
def fake_clock(monkeypatch):
    """取代 submissions.utcnow，讓測試精確控制每筆送出的後端時間（驗證冷卻與時間來源）。"""
    clock = Clock()
    monkeypatch.setattr(submissions_service, "utcnow", lambda: clock.now)
    return clock


def make_fair_room(
    client, win_cap=None, cooldown=0, bundles=(), groups=("第 1 組", "第 2 組", "第 3 組"), start=True
):
    """建立含題目（單題範例 Q1～Q6）並帶公平規則的房間，各組加入；回傳 (code, token, conns)。
    conns 為 {組名: (context manager, ws)}，呼叫端以 close_all(conns) 關閉。"""
    p = client.post("/api/sheets/preview", json={"url": SHEET_URL}).json()
    body = {
        "sheetUrl": SHEET_URL,
        "fingerprint": p["fingerprint"],
        "bundles": [list(b) for b in bundles],
        "fairness": {"winCap": win_cap, "cooldownSeconds": cooldown},
    }
    r = client.post("/api/rooms", json=body)
    assert r.status_code == 201, r.json()
    code, token = r.json()["code"], r.json()["teacherToken"]
    if start:
        assert client.post(f"/api/rooms/{code}/phase/start", headers=auth(token)).status_code == 200
    conns = {}
    for name in groups:
        cm, ws, _ = join_student(client, code, name)
        conns[name] = (cm, ws)
    return code, token, conns


def claim(conns, group, qid, answer):
    """該組對單題送出答案並等伺服器處理完（flush），讓測試精確控制送出先後。"""
    from .test_submission_privacy import flush

    ws = conns[group][1]
    ws.send_json({"type": "submit", "questionId": qid, "answer": answer})
    return flush(ws)


def claim_bundle(conns, group, bundle_id, answers):
    from .test_submission_privacy import flush

    ws = conns[group][1]
    ws.send_json({"type": "submit_bundle", "bundleId": bundle_id, "answers": answers})
    return flush(ws)


def close_all(conns):
    for cm, _ws in conns.values():
        cm.__exit__(None, None, None)


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
