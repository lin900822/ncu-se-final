"""有效結果推導：由「原始名次＋審核紀錄」推導有效狀態、遞補後名次與有效第一名（純函式、唯讀）。

原始答案、送出時間、處理序、原始名次永不改寫（原則 II、資料完整性）；審核只追加 ReviewRecord，
某筆送出是否有效＝同一 (輪次, 組別, 搶答單位) 的最後一筆審核動作是否為駁回。
只可匯入 ..models 與 bundles，避免 results／ranking／export／review 之間循環匯入。
"""
from dataclasses import dataclass, field

from ..models import FairnessRule, ReviewRecord, Room, Submission, iso
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


@dataclass
class Allocation:
    """某輪的首選資格分配結果（推導資料，不另存）。

    winners：每個「有申請」的單位的獲勝送出（全部被駁回為 None；沒有送出的單位不在字典中）；
    status：(unit_id, normalized_name) → Won／Kept／Behind／Invalid／YieldedCap／YieldedCooldown；
    wins：各組取得題數（含 Kept；題組計成員數）。
    """

    winners: dict[str, Submission | None] = field(default_factory=dict)
    status: dict[tuple[str, str], str] = field(default_factory=dict)
    wins: dict[str, int] = field(default_factory=dict)


def unit_size(room: Room, unit_id: str) -> int:
    """搶答單位的題數：題組＝成員數，單題＝1（獲勝題數以題計，N 題計 N）。"""
    for b in room.bundles:
        if b.id == unit_id:
            return len(b.question_ids)
    return 1


def _ineligible(
    rule: FairnessRule, wins: dict[str, int], last_win: dict, s: Submission
) -> str | None:
    """這筆申請是否因公平規則讓位：回傳 YieldedCap／YieldedCooldown，符合資格回傳 None。"""
    if rule.win_cap is not None and wins.get(s.normalized_name, 0) >= rule.win_cap:
        return "YieldedCap"  # 上限優先於冷卻
    last = last_win.get(s.normalized_name)
    if (
        rule.cooldown_seconds > 0
        and last is not None
        and (s.submitted_at - last).total_seconds() < rule.cooldown_seconds
    ):
        return "YieldedCooldown"  # 冷卻只看後端記錄的 submitted_at，且只從最近一次「取得」起算
    return None


def allocate(room: Room, round_no: int) -> Allocation:
    """逐筆資格判定的分配（確定性、純函式、不改動任何送出）：

    1. 申請＝本輪未被駁回的 unit_entries（每組每單位一筆）；被駁回者 status=Invalid。
    2. 申請依後端處理序 seq 由小到大逐筆判定：單位已有獲勝者 → Behind；不符資格 → 讓位
       （單位保持開放，由原始名次下一順位的後續申請遞補）；符合 → Won，並累計題數與取得時間。
    3. 主判定後仍沒有獲勝者、但有未被駁回申請的單位：由原始名次最前者 Kept（題目不懸空）。
    沒有公平規則時，結果與 Step 9 的「名次最前且未被駁回者」完全相同。
    """
    invalid = invalid_keys(room, round_no)
    entries = unit_entries(room, round_no)
    alloc = Allocation()
    claims: list[tuple[int, str, Submission]] = []
    for unit, lst in entries.items():
        for s in lst:
            if (s.normalized_name, unit) in invalid:
                alloc.status[(unit, s.normalized_name)] = "Invalid"
            else:
                claims.append((s.seq, unit, s))
    claims.sort(key=lambda c: c[0])

    last_win: dict[str, object] = {}
    for _seq, unit, s in claims:
        key = (unit, s.normalized_name)
        if alloc.winners.get(unit) is not None:
            alloc.status[key] = "Behind"
            continue
        reason = _ineligible(room.fairness, alloc.wins, last_win, s)
        if reason is not None:
            alloc.status[key] = reason
            continue
        alloc.winners[unit] = s
        alloc.status[key] = "Won"
        alloc.wins[s.normalized_name] = alloc.wins.get(s.normalized_name, 0) + unit_size(room, unit)
        last_win[s.normalized_name] = s.submitted_at

    for unit, lst in entries.items():
        if alloc.winners.get(unit) is not None:
            continue
        valid = [s for s in lst if (s.normalized_name, unit) not in invalid]
        if valid:
            best = valid[0]  # 原始名次最前者保留
            alloc.winners[unit] = best
            alloc.status[(unit, best.normalized_name)] = "Kept"
            alloc.wins[best.normalized_name] = alloc.wins.get(best.normalized_name, 0) + unit_size(room, unit)
        else:
            alloc.winners[unit] = None
    return alloc


def effective_winners(room: Room, round_no: int) -> dict[str, Submission | None]:
    """每個「有送出」的單位的獲勝送出（含公平規則的讓位與保留）；全部被駁回為 None；沒有送出的單位不在字典中。"""
    return allocate(room, round_no).winners


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
