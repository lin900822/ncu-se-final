"""階段服務：開始／結束搶答。階段為「能否作答」的唯一事實來源（FR-007）。

狀態更新與紀錄追加都在無 await 的同步區段內完成（單一 worker 下即為原子），
之後才廣播。廣播內容僅含階段資訊（FR-011）。
"""
from ..models import PhaseChange, Room, err, iso, question_texts, utcnow
from ..realtime import realtime
from . import projector, ranking, results, rooms


async def _broadcast(room: Room, change: PhaseChange) -> None:
    message = {
        "type": "phase_changed",
        "phase": change.phase,
        "round": change.round,
        "changedAt": iso(change.changed_at),
    }
    await realtime.broadcast_to_teachers(room.code, message)
    await realtime.broadcast_to_students(room.code, message)


async def _reveal_texts(room: Room, change: PhaseChange) -> None:
    """開始搶答後才把題目文字送出（FR-014）；結束搶答不送。"""
    if not room.questions:
        return
    message = {"type": "question_texts", "round": change.round, "texts": question_texts(room)}
    await realtime.broadcast_to_teachers(room.code, message)
    await realtime.broadcast_to_students(room.code, message)


async def start_answering(room: Room) -> tuple[str, int, bool]:
    if room.status == "Closed":
        raise err("ROOM_CLOSED")
    if room.phase == "Answering":
        return room.phase, room.round, False
    room.phase = "Answering"
    room.round += 1
    change = PhaseChange(phase="Answering", round=room.round, changed_at=utcnow())
    room.phase_log.append(change)
    rooms.touch(room)
    await _broadcast(room, change)
    await _reveal_texts(room, change)
    # 新一輪：老師端看板重設為空白（僅老師，原則 III）
    await realtime.broadcast_to_teachers(room.code, ranking.build_board(room))
    # 投影視圖（Step 12）：先推新狀態（匿名進度），再送一次性倒數事件；純視覺，不影響學生端開放
    await projector.publish(room)
    await projector.announce_countdown(room)
    return room.phase, room.round, True


async def end_answering(room: Room) -> tuple[str, int, bool]:
    if room.status == "Closed":
        raise err("ROOM_CLOSED")
    if room.phase != "Answering":
        return room.phase, room.round, False
    room.phase = "Ended"
    change = PhaseChange(phase="Ended", round=room.round, changed_at=utcnow())
    room.phase_log.append(change)
    rooms.touch(room)
    await _broadcast(room, change)
    # 結算：每輪僅一次（重複結束走上方早退路徑，不會到這裡）
    message = {"type": "round_result", **results.build_result(room)}
    await realtime.broadcast_result(room.code, message)
    await realtime.broadcast_to_teachers(room.code, message)
    await projector.publish(room)  # 投影視圖：結算後的得主與排行榜（Step 12）
    return room.phase, room.round, True


def ensure_answering(room: Room) -> None:
    if room.status != "Open" or room.phase != "Answering":
        raise err("PHASE_LOCKED")
