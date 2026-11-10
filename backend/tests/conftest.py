import pytest
from starlette.testclient import TestClient

from app.main import app
from app.realtime import realtime
from app.store import store


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
