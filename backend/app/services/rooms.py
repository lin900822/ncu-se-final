"""房間服務：建立、恢復、結束、活動時間。"""
from ..models import Room, bundle_public, err, iso, question_public, question_texts, utcnow
from ..normalize import normalize_room_code
from ..realtime import realtime
from ..store import store
from . import bundles as bundles_service
from . import ranking, results


def create_room(sheet=None, bundles=None) -> Room:
    now = utcnow()
    code = store.generate_room_code()
    room = Room(
        code=code,
        created_at=now,
        last_activity_at=now,
        teacher_token=store.generate_token(),
        recovery_code=store.generate_recovery_code(),
    )
    if sheet is not None:
        room.sheet = sheet.source
        room.questions = list(sheet.questions)
        # 題組隨房間建立確定，之後不可修改（Step 7）
        room.bundles = list(bundles or [])
        room.bundle_of = bundles_service.index_bundles(room.bundles)
    store.rooms[code] = room
    store.recovery_index[room.recovery_code] = code
    return room


def get_room(code: str) -> Room:
    room = store.get_room(normalize_room_code(code))
    if room is None:
        raise err("ROOM_NOT_FOUND")
    return room


def verify_teacher(code: str, token: str | None) -> Room:
    room = get_room(code)
    if not token or token != room.teacher_token:
        raise err("UNAUTHORIZED")
    return room


async def recover(recovery_code: str) -> Room:
    key = "".join(str(recovery_code).split()).upper()
    code = store.recovery_index.get(key)
    room = store.get_room(code) if code else None
    if room is None:
        raise err("RECOVERY_INVALID")
    if room.status == "Closed":
        raise err("ROOM_CLOSED")
    room.teacher_token = store.generate_token()
    touch(room)
    await realtime.revoke_teachers(room.code)
    return room


async def close_room(room: Room, reason: str) -> None:
    """Open → Closed，不可逆且冪等。"""
    if room.status == "Closed":
        return
    room.status = "Closed"
    room.closed_reason = reason  # type: ignore[assignment]
    room.closed_at = utcnow()
    await realtime.close_room_connections(room.code, reason)


def touch(room: Room) -> None:
    room.last_activity_at = utcnow()


def snapshot(room: Room) -> dict:
    groups = sorted(room.groups.values(), key=lambda g: g.joined_at)
    return {
        "type": "snapshot",
        "room": {
            "code": room.code,
            "status": room.status,
            "phase": room.phase,
            "round": room.round,
            "sheetTitle": room.sheet.sheet_title if room.sheet else None,
            "questions": [question_public(q) for q in room.questions],
            "bundles": [bundle_public(b) for b in room.bundles],
            "texts": question_texts(room),  # 老師已驗證，可見完整題目文字
            # 老師已驗證：可見所有輪次的送出紀錄（組別、題目、內容、伺服器時間）
            "submissions": [
                {
                    "group": s.group_name,
                    "questionId": s.question_id,
                    "answer": s.answer,
                    "round": s.round,
                    "submittedAt": iso(s.submitted_at),
                    "rank": s.rank,
                    "bundleId": s.bundle_id,
                }
                for s in room.submissions
            ],
            "board": ranking.build_board(room),
            "result": results.build_result(room),
        },
        "groups": [g.to_dict() for g in groups],
        "count": len(groups),
    }
