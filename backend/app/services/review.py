"""人工審核：老師駁回／恢復某組在某搶答單位的送出，由次順位遞補（Step 9）。

apply_review 整段同步、不得 await：驗證、重複判斷與追加在同一無 await 區段內完成（單一 worker 下即為原子），
因此連點或兩個視窗同時審核同一筆只會寫入一筆（原則 II、SC-009）。任何驗證失敗都在寫入前丟出，不留下任何紀錄。
審核只追加 ReviewRecord，**不修改任何 Submission**（答案／時間／處理序／原始名次永不改寫）。
保密（原則 III）：審核資訊與看板只送老師；學生只收到更新後的有效第一名（組名＋答案），
不含被駁回者、理由、名次，且只經 realtime.broadcast_result 發送。
"""
from ..models import ReviewRecord, Room, err, utcnow
from ..normalize import normalize_group_name
from ..realtime import realtime
from . import effective, ranking, results, rooms

MAX_REASON_LENGTH = 100
_ACTIONS = {"invalid": "Invalid", "valid": "Valid"}


def apply_review(
    room: Room, *, round_no: int, unit_id: str, group: str, action: str, reason: str
) -> tuple[ReviewRecord | None, bool]:
    """回傳 (該筆目標最近一筆審核紀錄或 None, 是否新建)；重複動作回傳 (既有紀錄, False)，不新增。"""
    if room.status != "Open":
        raise err("ROOM_CLOSED")
    if room.phase != "Ended" or round_no != room.round:
        raise err("REVIEW_NOT_ALLOWED")
    if action not in _ACTIONS:
        raise err("BAD_REQUEST")
    # 搶答單位：題組 id，或「未綁定題組」的題目 id（題組成員題只能整組審核）
    valid_units = {b.id for b in room.bundles} | {q.id for q in room.questions if q.id not in room.bundle_of}
    if unit_id not in valid_units:
        raise err("UNIT_NOT_FOUND")
    normalized = normalize_group_name(group)
    entries = effective.unit_entries(room, room.round).get(unit_id, [])
    target = next((s for s in entries if s.normalized_name == normalized), None)
    if target is None:
        raise err("REVIEW_TARGET_NOT_FOUND")
    if not isinstance(reason, str) or not reason.strip():
        raise err("REASON_REQUIRED")
    text = reason.strip()
    if len(text) > MAX_REASON_LENGTH:
        raise err("REASON_TOO_LONG")

    last = effective.review_state(room, room.round).get((normalized, unit_id))
    currently_invalid = last is not None and last.action == "Invalid"
    if currently_invalid == (action == "invalid"):
        return last, False  # 重複：不新增、不廣播、不重複遞補

    record = ReviewRecord(
        round=room.round,
        unit_id=unit_id,
        group_name=target.group_name,
        normalized_name=normalized,
        action=_ACTIONS[action],  # type: ignore[arg-type]
        reason=text,
        reviewed_at=utcnow(),  # 時間一律由後端產生
    )
    room.reviews.append(record)
    rooms.touch(room)
    return record, True


async def publish_review(room: Room, changed_units: list[str] | None = None) -> None:
    """審核成功後廣播：老師收到完整看板／審核紀錄／有效結果；全體學生只收到更新後的有效第一名。

    changed_units（Step 11）：因公平規則連動而改變獲勝者的其他單位（只送老師，不送學生）。"""
    result = results.build_result(room)
    await realtime.broadcast_to_teachers(
        room.code,
        {
            "type": "review_updated",
            "round": room.round,
            "board": ranking.build_board(room),
            "reviews": [effective.review_public(r) for r in room.reviews],
            "result": result,
            "changedUnits": list(changed_units or []),
        },
    )
    # 學生：沿用結果公布的專用通道，內容只有各題有效第一名的組名＋答案（不含被駁回者、理由、名次）
    await realtime.broadcast_result(room.code, {"type": "round_result", "reviewed": True, **result})
