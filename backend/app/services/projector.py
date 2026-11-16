"""投影視圖（Step 12）：由房間紀錄推導「全班公開」的整份畫面資料，並推送給唯讀的投影連線。

保密（原則 III）：大螢幕等同全班可見。搶答中只輸出各單位「是否已有組別送出」（匿名布林）與總進度，
**不產生**任何送出組別的歸屬、答案、名次、時間、讓位／保留；結算後只公開各題得主組名＋答案
（直接取自 results.build_result，與學生端同一份）與各組累計得分。
純讀取：不得修改 room 的任何欄位。只匯入 ..models、..realtime、bundles、effective、results。
"""
from ..models import Room, bundle_public, question_public
from ..realtime import realtime
from . import bundles, effective, results


def _settled_rounds(room: Room) -> range:
    """已結算輪次：搶答中的那一輪尚未結算；其餘階段 1..round。"""
    last = room.round - 1 if room.phase == "Answering" else room.round
    return range(1, max(last, 0) + 1)


def scoreboard(room: Room) -> list[dict]:
    """各組累計得分（已結算各輪取得題數；題組 N 題計 N；含公平規則讓位與保留），同分名次並列。"""
    totals: dict[str, int] = {}
    for n in _settled_rounds(room):
        for name, wins in effective.allocate(room, n).wins.items():
            totals[name] = totals.get(name, 0) + wins
    rows = [(g.name, totals.get(key, 0)) for key, g in room.groups.items()]
    rows.sort(key=lambda r: (-r[1], r[0]))
    out: list[dict] = []
    for i, (name, score) in enumerate(rows):
        rank = out[-1]["rank"] if out and out[-1]["score"] == score else i + 1
        out.append({"group": name, "score": score, "rank": rank})
    return out


def _units(room: Room) -> list[str]:
    seen: list[str] = []
    for q in room.questions:
        u = bundles.unit_of(room, q.id)
        if u not in seen:
            seen.append(u)
    return seen


def build_state(room: Room) -> dict:
    submitted = None
    progress = None
    if room.phase == "Answering":
        done = {bundles.unit_of(room, s.question_id) for s in room.submissions if s.round == room.round}
        units = _units(room)
        submitted = {u: u in done for u in units}
        progress = {"answered": sum(1 for u in units if u in done), "total": len(units)}
    return {
        "type": "projector_state",
        "code": room.code,
        "status": room.status,
        "phase": room.phase,
        "round": room.round,
        "groups": [g.name for g in sorted(room.groups.values(), key=lambda g: g.joined_at)],
        "questions": [question_public(q) for q in room.questions],
        "bundles": [bundle_public(b) for b in room.bundles],
        "progress": progress,
        "submitted": submitted,
        "result": results.build_result(room) if room.phase == "Ended" else None,
        "scoreboard": scoreboard(room),
    }


async def publish(room: Room) -> None:
    if not realtime.has_projectors(room.code):
        return
    await realtime.broadcast_to_projectors(room.code, build_state(room))


async def announce_countdown(room: Room) -> None:
    """老師實際開始搶答時的一次性視覺事件；不含任何仲裁資訊，晚連線不補播。"""
    await realtime.broadcast_to_projectors(room.code, {"type": "countdown", "round": room.round})
