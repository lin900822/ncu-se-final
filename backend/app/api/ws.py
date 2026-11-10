import asyncio
import json

from fastapi import APIRouter, WebSocket, WebSocketDisconnect

from ..models import AppError, err, question_public, question_texts
from ..realtime import close_safe, realtime, send_json_safe
from ..services import groups, phase, rooms

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
                "phase": room.phase,
                "round": room.round,
                "questions": [question_public(q) for q in room.questions],
                # 題目文字只在搶答中才給學生（FR-014）；其餘階段（含重連）一律為空
                "texts": question_texts(room)
                if room.status == "Open" and room.phase == "Answering"
                else {},
            },
        )
        await groups.announce_join(room, group, is_new)
        while True:
            raw = await ws.receive_text()
            rooms.touch(room)
            try:
                data = json.loads(raw)
            except ValueError:
                continue
            if isinstance(data, dict) and data.get("type") == "submit":
                try:
                    phase.ensure_answering(room)
                except AppError as e:
                    # 鎖定中的送出一律拒絕，但不關閉連線（FR-007）
                    await send_json_safe(
                        ws, {"type": "error", "code": e.code, "message": e.message}
                    )
                # Answering：本步驟僅為閘門，內容與仲裁由 Step 3 實作
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
