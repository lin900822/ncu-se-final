"""組別服務：加入、在線/離線、唯一性。"""
from fastapi import WebSocket

from ..models import Group, Room, err, utcnow
from ..normalize import normalize_group_name, validate_group_name
from ..realtime import realtime
from . import rooms


def join(code: str, raw_name: str, ws: WebSocket) -> tuple[Room, Group, bool, bool]:
    """同步（無 await）完成驗證與標記，確保同時加入同一組名時只有一方成功。

    回傳 (room, group, rejoined, is_new)。
    """
    room = rooms.get_room(code)
    if room.status == "Closed":
        raise err("ROOM_CLOSED")
    name = validate_group_name(raw_name)
    key = normalize_group_name(name)
    group = room.groups.get(key)
    if group is not None and group.online:
        raise err("GROUP_ONLINE")
    is_new = group is None
    if group is None:
        group = Group(name=name, normalized_name=key, online=True, joined_at=utcnow())
        room.groups[key] = group
    else:
        group.online = True
    realtime.set_student(room.code, key, ws)
    rooms.touch(room)
    return room, group, not is_new, is_new


async def announce_join(room: Room, group: Group, is_new: bool) -> None:
    if is_new:
        await realtime.broadcast_to_teachers(
            room.code,
            {"type": "group_joined", "group": group.to_dict(), "count": len(room.groups)},
        )
    else:
        await realtime.broadcast_to_teachers(
            room.code, {"type": "group_status", "name": group.name, "online": True}
        )


async def disconnect(room: Room, group: Group, ws: WebSocket) -> None:
    """僅當此連線仍是登記中的連線才標記離線，避免舊連線延遲關閉誤傷新連線。"""
    if not realtime.student_is(room.code, group.normalized_name, ws):
        return
    realtime.remove_student(room.code, group.normalized_name)
    group.online = False
    rooms.touch(room)
    if room.status == "Open":
        await realtime.broadcast_to_teachers(
            room.code, {"type": "group_status", "name": group.name, "online": False}
        )
