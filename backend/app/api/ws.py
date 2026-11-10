import asyncio

from fastapi import APIRouter, WebSocket, WebSocketDisconnect

from ..models import AppError, err
from ..realtime import close_safe, realtime, send_json_safe
from ..services import groups, rooms

router = APIRouter()

JOIN_TIMEOUT_SECONDS = 5


async def _reject(ws: WebSocket, e: AppError) -> None:
    await send_json_safe(ws, {"type": "error", "code": e.code, "message": e.message})
    await close_safe(ws, 1008)


@router.websocket("/ws/student")
async def student_ws(ws: WebSocket):
    await ws.accept()
    try:
        msg = await asyncio.wait_for(ws.receive_json(), JOIN_TIMEOUT_SECONDS)
    except asyncio.TimeoutError:
        await _reject(ws, err("JOIN_TIMEOUT"))
        return
    except WebSocketDisconnect:
        return
    except Exception:
        await _reject(ws, err("BAD_REQUEST"))
        return
    if not isinstance(msg, dict) or msg.get("type") != "join":
        await _reject(ws, err("BAD_REQUEST"))
        return
    try:
        room, group, rejoined, is_new = groups.join(
            str(msg.get("code", "")), str(msg.get("name", "")), ws
        )
    except AppError as e:
        await _reject(ws, e)
        return

    try:
        await send_json_safe(
            ws,
            {
                "type": "joined",
                "room": {"code": room.code},
                "group": {"name": group.name},
                "rejoined": rejoined,
            },
        )
        await groups.announce_join(room, group, is_new)
        while True:
            await ws.receive_text()
            rooms.touch(room)
    except WebSocketDisconnect:
        pass
    finally:
        await groups.disconnect(room, group, ws)


@router.websocket("/ws/teacher")
async def teacher_ws(ws: WebSocket, token: str = "", code: str = ""):
    await ws.accept()
    try:
        room = rooms.verify_teacher(code, token)
    except AppError:
        await close_safe(ws, 4401)
        return
    if room.status == "Closed":
        await send_json_safe(ws, {"type": "room_closed", "reason": room.closed_reason})
        await close_safe(ws, 1000)
        return
    realtime.add_teacher(room.code, ws)
    rooms.touch(room)
    try:
        await send_json_safe(ws, rooms.snapshot(room))
        while True:
            await ws.receive_text()  # 可選 {"type":"ping"}，僅更新活動時間
            rooms.touch(room)
    except WebSocketDisconnect:
        pass
    finally:
        realtime.remove_teacher(room.code, ws)
        rooms.touch(room)
