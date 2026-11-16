import asyncio
import hmac
import json

from fastapi import APIRouter, WebSocket, WebSocketDisconnect

from ..models import AppError, bundle_public, err, fairness_public, question_public, question_texts
from ..realtime import close_safe, realtime, send_json_safe
from ..services import groups, projector, ranking, results, rooms, submissions

router = APIRouter()

JOIN_TIMEOUT_SECONDS = 5


async def _reject(ws: WebSocket, e: AppError) -> None:
    await send_json_safe(ws, {"type": "error", "code": e.code, "message": e.message})
    await close_safe(ws, 1008)


async def _handle_bundle_submit(ws: WebSocket, room, group, data: dict) -> None:
    """題組整組送出（Step 7）。寫入在 submit_bundle 內同步完成，之後才開始 await 廣播。"""
    bundle_id = str(data.get("bundleId", ""))
    try:
        subs, created = submissions.submit_bundle(room, group, bundle_id, data.get("answers"))
    except AppError as e:
        # 驗證失敗只回發送者且不關閉連線；整筆不記錄
        payload = {"type": "error", "code": e.code, "message": e.message, "bundleId": bundle_id}
        if e.details is not None:
            payload["details"] = e.details
        await send_json_safe(ws, payload)
        return
    if not created:
        # 重複送出：只回送既有結果，不新增紀錄、不通知任何人
        await send_json_safe(ws, submissions.to_bundle_group_event(subs))
        return
    # 三種受眾、三種內容（原則 III）：
    # 老師＝逐題組別＋答案＋時間＋名次與看板；同組視窗＝各題答案；他組＝匿名提示（只含題組識別碼與輪次）
    for sub in subs:
        await realtime.broadcast_to_teachers(room.code, submissions.to_teacher_event(sub))
    await realtime.broadcast_to_teachers(room.code, ranking.build_board(room))
    await realtime.broadcast_to_group(
        room.code, group.normalized_name, submissions.to_bundle_group_event(subs)
    )
    await realtime.broadcast_to_other_groups(
        room.code, group.normalized_name, submissions.to_bundle_hint_event(subs)
    )
    await projector.publish(room)  # 投影視圖：匿名進度（Step 12）


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
        room, group, rejoined, is_new, was_online = groups.join(
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
                # 題組設定（不含作答內容；Step 7）
                "bundles": [bundle_public(b) for b in room.bundles],
                # 公平規則本身（公開，Step 11）；只含上限與冷卻兩個數字，不含任何分配資訊
                "fairness": fairness_public(room.fairness),
                # 題目文字只在搶答中才給學生（FR-014）；其餘階段（含重連）一律為空
                "texts": question_texts(room)
                if room.status == "Open" and room.phase == "Answering"
                else {},
                # 還原本組本輪已送出的內容；他組只給匿名的題目識別碼（Step 4）
                "mySubmissions": submissions.my_submissions(room, group),
                "submittedByOthers": submissions.submitted_by_others(room, group),
                # 結算後（Ended）才有結果；其餘階段為 None（Step 6）
                "result": results.build_result(room) if room.status == "Open" else None,
            },
        )
        await groups.announce_join(room, group, is_new, was_online)
        while True:
            raw = await ws.receive_text()
            rooms.touch(room)
            try:
                data = json.loads(raw)
            except ValueError:
                continue
            if isinstance(data, dict) and data.get("type") == "submit_bundle":
                await _handle_bundle_submit(ws, room, group, data)
                continue
            if isinstance(data, dict) and data.get("type") == "submit":
                qid = str(data.get("questionId", ""))
                try:
                    sub, created = submissions.submit(room, group, qid, data.get("answer"))
                except AppError as e:
                    # 驗證失敗只回發送者且不關閉連線（FR-004、FR-003）
                    await send_json_safe(
                        ws,
                        {"type": "error", "code": e.code, "message": e.message, "questionId": qid},
                    )
                    continue
                if not created:
                    # 重複送出：只回送既有結果，不新增紀錄、不通知任何人（FR-005）
                    await send_json_safe(ws, submissions.to_group_event(sub))
                    continue
                # 三種受眾、三種內容（原則 III）：
                # 同組視窗＝答案；老師＝組別＋答案＋時間；他組＝匿名提示（只含題目識別碼與輪次）
                await realtime.broadcast_to_group(
                    room.code, group.normalized_name, submissions.to_group_event(sub)
                )
                await realtime.broadcast_to_teachers(room.code, submissions.to_teacher_event(sub))
                await realtime.broadcast_to_teachers(room.code, ranking.build_board(room))
                await realtime.broadcast_to_other_groups(
                    room.code, group.normalized_name, submissions.to_other_groups_event(sub)
                )
                await projector.publish(room)  # 投影視圖：匿名進度（Step 12）
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


@router.websocket("/ws/projector")
async def projector_ws(ws: WebSocket, code: str = "", key: str = ""):
    """投影視圖（Step 12）：唯讀、只推送。憑證錯誤、房間不存在一律同一則訊息（不洩漏房間是否存在）。"""
    await ws.accept()
    try:
        room = rooms.get_room(code)
        ok = bool(key) and hmac.compare_digest(key.encode(), room.projector_key.encode())
    except AppError:
        ok = False
    if not ok:
        await send_json_safe(ws, {"type": "projector_unavailable"})
        await close_safe(ws, 1008)
        return
    # 不呼叫 rooms.touch：投影連線不算活動；不登記為組別
    if room.status == "Closed":
        await send_json_safe(ws, projector.build_state(room))
        await close_safe(ws, 1000)
        return
    realtime.add_projector(room.code, ws)
    try:
        await send_json_safe(ws, projector.build_state(room))
        while True:
            await ws.receive_text()  # 一律丟棄：投影連線唯讀
    except WebSocketDisconnect:
        pass
    finally:
        realtime.remove_projector(room.code, ws)
