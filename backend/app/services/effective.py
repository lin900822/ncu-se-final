"""有效結果推導：由「原始名次＋審核紀錄」推導有效狀態、遞補後名次與有效第一名（純函式、唯讀）。

原始答案、送出時間、處理序、原始名次永不改寫（原則 II、資料完整性）；審核只追加 ReviewRecord，
某筆送出是否有效＝同一 (輪次, 組別, 搶答單位) 的最後一筆審核動作是否為駁回。
只可匯入 ..models 與 bundles，避免 results／ranking／export／review 之間循環匯入。
"""
from ..models import ReviewRecord, Room, Submission, iso
from . import bundles


def review_state(room: Room, round_no: int) -> dict[tuple[str, str], ReviewRecord]:
    """該輪每個 (normalized_name, unit_id) 的最後一筆審核紀錄。"""
    state: dict[tuple[str, str], ReviewRecord] = {}
    for r in room.reviews:
        if r.round == round_no:
            state[(r.normalized_name, r.unit_id)] = r
    return state


def invalid_keys(room: Room, round_no: int) -> set[tuple[str, str]]:
    """目前被駁回的 (normalized_name, unit_id)。"""
    return {k for k, r in review_state(room, round_no).items() if r.action == "Invalid"}


def unit_entries(room: Room, round_no: int) -> dict[str, list[Submission]]:
    """本輪送出依搶答單位分組；每個組別在每個單位只留一筆（題組取題目順序最前的成員），
    各單位內依原始名次由小到大排序。"""
    order = {q.id: i for i, q in enumerate(room.questions)}
    first: dict[tuple[str, str], Submission] = {}
    for s in room.submissions:
        if s.round != round_no:
            continue
        key = (bundles.unit_of(room, s.question_id), s.normalized_name)
        cur = first.get(key)
        if cur is None or order.get(s.question_id, len(order)) < order.get(cur.question_id, len(order)):
            first[key] = s
    out: dict[str, list[Submission]] = {}
    for (unit, _name), s in first.items():
        out.setdefault(unit, []).append(s)
    for lst in out.values():
        lst.sort(key=lambda s: s.rank)
    return out


def effective_winners(room: Room, round_no: int) -> dict[str, Submission | None]:
    """每個「有送出」的單位取原始名次最前且未被駁回者；全部被駁回為 None；沒有送出的單位不在字典中。"""
    invalid = invalid_keys(room, round_no)
    winners: dict[str, Submission | None] = {}
    for unit, entries in unit_entries(room, round_no).items():
        winners[unit] = next((s for s in entries if (s.normalized_name, unit) not in invalid), None)
    return winners


def succession_ranks(room: Room, round_no: int) -> dict[tuple[str, str], int]:
    """(unit_id, normalized_name) → 排除無效者後的名次（由 1 起連續）；無效者不在字典中。"""
    invalid = invalid_keys(room, round_no)
    ranks: dict[tuple[str, str], int] = {}
    for unit, entries in unit_entries(room, round_no).items():
        n = 0
        for s in entries:
            if (s.normalized_name, unit) in invalid:
                continue
            n += 1
            ranks[(unit, s.normalized_name)] = n
    return ranks


def review_public(r: ReviewRecord) -> dict:
    """老師端顯示用（僅老師可見，原則 III）。"""
    return {
        "round": r.round,
        "unitId": r.unit_id,
        "group": r.group_name,
        "action": "invalid" if r.action == "Invalid" else "valid",
        "reason": r.reason,
        "by": r.by,
        "reviewedAt": iso(r.reviewed_at),
    }
