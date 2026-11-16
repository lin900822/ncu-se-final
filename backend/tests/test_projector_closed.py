"""Step 12 US4：房間結束與保留期內外的投影行為。"""
from datetime import timedelta

import pytest
from starlette.websockets import WebSocketDisconnect

from app.models import utcnow
from app.store import store

from .conftest import (
    auth,
    claim,
    close_all,
    get_projector_key,
    make_fair_room,
    projector_ws,
    projector_until,
)

G1, G2 = "第 1 組", "第 2 組"


def _prepare(client):
    code, token, conns = make_fair_room(client, groups=(G1, G2))
    claim(conns, G1, "1", "a")
    assert client.post(f"/api/rooms/{code}/phase/end", headers=auth(token)).status_code == 200
    return code, token, conns


def test_close_sends_final_state_then_disconnects(client, use_sheet):
    code, token, conns = _prepare(client)
    key = get_projector_key(client, code, token)
    cm, ws, _ = projector_ws(client, code, key)
    try:
        assert client.post(f"/api/rooms/{code}/close", headers=auth(token)).status_code == 200
        state = ws.receive_json()
        assert state["status"] == "Closed" and state["phase"] == "Ended"
        assert state["result"]["results"][0]["winnerGroup"] == G1  # 保留最後的得主
        assert {r["group"]: r["score"] for r in state["scoreboard"]} == {G1: 1, G2: 0}
        with pytest.raises(WebSocketDisconnect):
            ws.receive_json()
    finally:
        cm.__exit__(None, None, None)
        close_all(conns)


def test_idle_timeout_also_sends_final_state(client, use_sheet):
    from app.services import rooms

    code, token, conns = _prepare(client)
    key = get_projector_key(client, code, token)
    cm, ws, _ = projector_ws(client, code, key)
    try:
        import asyncio

        asyncio.get_event_loop_policy()  # 確保可建立事件迴圈
        room = store.rooms[code]
        asyncio.run(rooms.close_room(room, "IdleTimeout"))
        assert ws.receive_json()["status"] == "Closed"
    finally:
        cm.__exit__(None, None, None)
        close_all(conns)


def test_new_connection_to_closed_room_gets_same_content_then_closes(client, use_sheet):
    code, token, conns = _prepare(client)
    key = get_projector_key(client, code, token)
    cm, ws, before = projector_ws(client, code, key)
    client.post(f"/api/rooms/{code}/close", headers=auth(token))
    closed = ws.receive_json()
    cm.__exit__(None, None, None)
    cm2, ws2, again = projector_ws(client, code, key)
    try:
        assert again == closed and again["status"] == "Closed"
        assert {k: v for k, v in again.items() if k != "status"} == {k: v for k, v in before.items() if k != "status"}
        with pytest.raises(WebSocketDisconnect):
            ws2.receive_json()
    finally:
        cm2.__exit__(None, None, None)
        close_all(conns)


def test_purged_room_is_unavailable(client, use_sheet):
    code, token, conns = _prepare(client)
    key = get_projector_key(client, code, token)
    client.post(f"/api/rooms/{code}/close", headers=auth(token))
    store.remove_room(code)  # 超過保留期被清除
    cm, ws, first = projector_ws(client, code, key)
    try:
        assert first == {"type": "projector_unavailable"}
    finally:
        cm.__exit__(None, None, None)
        close_all(conns)
