"""組別服務：加入、在線/離線、唯一性。"""
from fastapi import WebSocket

from ..models import Group, Room, err, utcnow
from ..normalize import normalize_group_name, validate_group_name
from ..realtime import realtime
from . import projector, rooms


MAX_WINDOWS_PER_GROUP = 10


def join(code: str, raw_name: str, ws: WebSocket) -> tuple[Room, Group, bool, bool, bool]:
    """同步（無 await）完成驗證與標記。

    同組可有多個視窗（Step 4 起不再拒絕「該組目前在線」），每組視窗上限 10。
    回傳 (room, group, rejoined, is_new, was_online)。
    """
    room = rooms.get_room(code)
    if room.status == "Closed":
        raise err("ROOM_CLOSED")
    name = validate_group_name(raw_name)
    key = normalize_group_name(name)
    group = room.groups.get(key)
    if realtime.window_count(room.code, key) >= MAX_WINDOWS_PER_GROUP:
        raise err("GROUP_WINDOWS_FULL")
    is_new = group is None
    was_online = bool(group and group.online)
    if group is None:
        group = Group(name=name, normalized_name=key, online=True, joined_at=utcnow())
        room.groups[key] = group
    else:
        group.online = True
    realtime.add_student(room.code, key, ws)
    rooms.touch(room)
    return room, group, not is_new, is_new, was_online


async def announce_join(room: Room, group: Group, is_new: bool, was_online: bool = False) -> None:
    """只在「新組別」或「由離線轉在線」時通知老師；同組多出的視窗不重複通知。"""
    if was_online and not is_new:
        return
    if is_new:
        await realtime.broadcast_to_teachers(
            room.code,
            {"type": "group_joined", "group": group.to_dict(), "count": len(room.groups)},
        )
        await projector.publish(room)  # 投影視圖的組別名單（Step 12）
    else:
        await realtime.broadcast_to_teachers(
            room.code, {"type": "group_status", "name": group.name, "online": True}
        )


async def disconnect(room: Room, group: Group, ws: WebSocket) -> None:
    """移除此視窗；僅當該組所有視窗都離開才標記離線並通知老師。"""
    remaining = realtime.remove_student(room.code, group.normalized_name, ws)
    rooms.touch(room)
    if remaining > 0:
        return
    group.online = False
    if room.status == "Open":
        await realtime.broadcast_to_teachers(
            room.code, {"type": "group_status", "name": group.name, "online": False}
        )
