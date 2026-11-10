"""階段服務：開始／結束搶答。階段為「能否作答」的唯一事實來源（FR-007）。

狀態更新與紀錄追加都在無 await 的同步區段內完成（單一 worker 下即為原子），
之後才廣播。廣播內容僅含階段資訊（FR-011）。
"""
from ..models import PhaseChange, Room, err, iso, utcnow
from ..realtime import realtime
from . import rooms


async def _broadcast(room: Room, change: PhaseChange) -> None:
    message = {
        "type": "phase_changed",
        "phase": change.phase,
        "round": change.round,
        "changedAt": iso(change.changed_at),
    }
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
    return room.phase, room.round, True


def ensure_answering(room: Room) -> None:
    if room.status != "Open" or room.phase != "Answering":
        raise err("PHASE_LOCKED")
