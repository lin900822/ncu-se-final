"""回填：把各題「有效第一名」的答案寫回原 Google 試算表的作答格（Step 10）。

本檔的純函式部分（計畫推導）不連線、不 await：
- system_written：依成功的回填紀錄推導「先前由本系統寫入的格」；
- build_plan：由有效結果＋作答格位置＋先前寫入＋試算表現況，推導寫入／清空／保留／略過。
回填只讀取結果，不改動任何送出、名次或審核紀錄（原則 II）；回填屬老師專屬（原則 III）。
"""
from dataclasses import dataclass, field
from typing import Literal

from ..config import get_sheets_config
from ..models import AppError, BackfillRecord, Room, backfill_public, err, utcnow
from ..realtime import realtime
from ..sheets.a1 import parse_a1
from ..sheets.client import SheetsClient
from ..sheets.parser import Grid
from . import results, rooms, sheets

Action = Literal["write", "clear", "keep", "skip"]


@dataclass
class PlanItem:
    question_id: str
    label: str
    action: Action
    cell: str
    answer: str | None = None  # 只有 write 有值（答案原文）
    overwrite: bool = False  # write 且目標格原本有內容、且與答案不同


@dataclass
class BackfillPlan:
    items: list[PlanItem] = field(default_factory=list)

    @property
    def counts(self) -> dict:
        n = {"write": 0, "skip": 0, "clear": 0, "keep": 0}
        for it in self.items:
            n[it.action] += 1
        n["overwrite"] = sum(1 for it in self.items if it.action == "write" and it.overwrite)
        return n

    @property
    def can_backfill(self) -> bool:
        c = self.counts
        return c["write"] + c["clear"] > 0


def system_written(room: Room) -> dict[str, str]:
    """先前由本系統寫入的格：依時間先後套用所有成功的回填紀錄（先加入 written，再移除 cleared）。

    失敗的紀錄不影響。鍵為作答格位址，值為最後一次寫入的文字。
    """
    written: dict[str, str] = {}
    for rec in room.backfills:
        if rec.result != "Success":
            continue
        written.update(rec.written)
        for cell in rec.cleared:
            written.pop(cell, None)
    return written


def build_plan(room: Room, result: dict, grid: Grid) -> BackfillPlan:
    """推導回填計畫；每個題目恰屬一類。

    - write：有有效第一名 → 寫入該組在這一題的答案原文；目標格現有內容非空且不同於答案者計為覆寫；
    - clear：沒有有效第一名、該格先前由本系統寫入、且目前內容仍等於當初寫入的文字 → 清空；
    - keep：同上但目前內容已被老師改過 → 不動；
    - skip：其餘沒有有效第一名的題目 → 不動（絕不碰未被本系統寫過的格）。
    """
    by_question = {r["questionId"]: r for r in result["results"]}
    previous = system_written(room)
    plan = BackfillPlan()
    for q in room.questions:
        row, col = parse_a1(q.cell)
        current = grid.raw(row, col)  # 合併儲存格以記錄的左上格為準
        item = by_question.get(q.id) or {}
        if item.get("winnerGroup") is not None and item.get("answer") is not None:
            answer = item["answer"]
            plan.items.append(
                PlanItem(
                    q.id, q.label, "write", q.cell, answer,
                    overwrite=current.strip() != "" and current != answer,
                )
            )
        elif q.cell in previous:
            action: Action = "clear" if current == previous[q.cell] else "keep"
            plan.items.append(PlanItem(q.id, q.label, action, q.cell))
        else:
            plan.items.append(PlanItem(q.id, q.label, "skip", q.cell))
    return plan


def target_updates(plan: BackfillPlan) -> list[tuple[int, int, str | None]]:
    """要送往試算表的更新：write → (row, col, 答案)；clear → (row, col, None)；依題目順序。"""
    updates: list[tuple[int, int, str | None]] = []
    for it in plan.items:
        if it.action == "write":
            row, col = parse_a1(it.cell)
            updates.append((row, col, it.answer))
        elif it.action == "clear":
            row, col = parse_a1(it.cell)
            updates.append((row, col, None))
    return updates


# ---------------------------------------------------------------------------
# 連線與寫入（async）
# ---------------------------------------------------------------------------

async def _write_batch(spreadsheet_id: str, sheet_id: int, updates) -> None:
    """對 Google 的唯一寫入：單一批次、全有或全無。這是測試替換用的縫隙（fake_sheet）。"""
    config = get_sheets_config()
    if config is None:
        raise err("SHEETS_NOT_CONFIGURED")
    await SheetsClient(config).write_cells(spreadsheet_id, sheet_id, updates)


def _precheck(room: Room, round_no: int) -> None:
    if room.sheet is None:
        raise err("BACKFILL_NO_SHEET")
    if room.phase != "Ended" or round_no != room.round:
        raise err("BACKFILL_NOT_ALLOWED")


async def _read_verified(room: Room) -> Grid:
    """重新讀取試算表並驗證結構指紋與建立房間時一致；不一致即拒絕（在任何寫入之前，FR-009）。"""
    grid, _questions, fingerprint = await sheets.read_for_backfill(room)
    if fingerprint != room.sheet.fingerprint:
        raise err("SHEET_STRUCTURE_CHANGED")
    return grid


async def preview(room: Room, round_no: int) -> dict:
    """預覽（唯讀）：讀取試算表、推導計畫、回傳確認摘要；不寫入、不追加紀錄、不廣播。"""
    _precheck(room, round_no)
    grid = await _read_verified(room)
    plan = build_plan(room, results.build_result(room), grid)
    return {
        "round": room.round,
        "sheetTitle": room.sheet.sheet_title,
        "sheetUrl": room.sheet.url,
        "canBackfill": plan.can_backfill,
        "counts": plan.counts,
        "items": [
            {
                "questionId": it.question_id,
                "label": it.label,
                "action": it.action,
                "overwrite": it.overwrite,
                "answer": it.answer if it.action == "write" else None,
            }
            for it in plan.items
        ],
    }


async def _record_failure(room: Room, reason: str) -> None:
    """開始讀取之後的失敗也是一次回填嘗試：追加 Failed 紀錄並廣播（試算表保證未被改動）。"""
    room.backfills.append(BackfillRecord(round=room.round, at=utcnow(), result="Failed", reason=reason))
    rooms.touch(room)
    await publish(room)


# 進行中的回填（每房間一次只允許一個）；重啟後自然清空
_running: set[str] = set()


async def execute(room: Room, round_no: int) -> dict:
    """確認回填（同房間互斥）：連點或多視窗同時確認只會有一次有效的寫入與一筆紀錄。"""
    _precheck(room, round_no)
    if room.code in _running:  # 檢查與加入在同一同步區段內（無 await）
        raise err("BACKFILL_IN_PROGRESS")
    _running.add(room.code)
    try:
        return await _execute_locked(room, round_no)
    finally:
        _running.discard(room.code)


async def _execute_locked(room: Room, round_no: int) -> dict:
    """確認回填：以確認當下的有效結果與試算表現況重新推導計畫，單一批次寫入，成功後追加紀錄並廣播。

    驗證順序固定：前置檢查（未綁定→階段／輪次）→ 讀取並驗證結構 → 可做事項 → 寫入。
    前置檢查失敗與「沒有可回填的答案」不算回填嘗試（不記錄）；之後的任何失敗都記為 Failed 紀錄。
    """
    _precheck(room, round_no)
    try:
        grid = await _read_verified(room)
        plan = build_plan(room, results.build_result(room), grid)
        updates = target_updates(plan)
        if not updates:
            raise err("BACKFILL_NOTHING")
        await _write_batch(room.sheet.spreadsheet_id, room.sheet.sheet_id, updates)
    except AppError as e:
        if e.code != "BACKFILL_NOTHING":
            await _record_failure(room, e.code)
        raise
    except Exception:
        # 意外例外：不洩漏內部資訊，一律視為連線失敗
        await _record_failure(room, "SHEET_TIMEOUT")
        raise err("SHEET_TIMEOUT") from None
    counts = plan.counts
    record = BackfillRecord(
        round=room.round,
        at=utcnow(),
        result="Success",
        written={it.cell: it.answer for it in plan.items if it.action == "write"},
        cleared=[it.cell for it in plan.items if it.action == "clear"],
        skipped_count=counts["skip"],
        kept_count=counts["keep"],
    )
    room.backfills.append(record)
    rooms.touch(room)
    await publish(room)
    return {
        "round": room.round,
        "sheetUrl": room.sheet.url,
        "counts": {k: counts[k] for k in ("write", "skip", "clear", "keep")},
        "record": backfill_public(record),
    }


async def publish(room: Room) -> None:
    """回填屬老師專屬：只經 broadcast_to_teachers 送出（整份紀錄覆蓋）；學生端完全不涉及。"""
    await realtime.broadcast_to_teachers(
        room.code,
        {"type": "backfill_updated", "backfills": [backfill_public(r) for r in room.backfills]},
    )
