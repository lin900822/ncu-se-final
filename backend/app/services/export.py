"""紀錄匯出：把所有輪次的有效送出整理成 CSV（純函式、唯讀）。

保密（原則 III）：內容含各組答案與名次，只可由持有老師憑證的路徑呼叫（api/rooms.py）；
嚴禁被學生 WebSocket 路徑引用。
唯讀：不修改任何紀錄（僅追加）；整段同步、不得 await，因此是一致快照（題組成員必定一起出現）。
時間為送出當下由後端產生的 UTC（原則 II）；排名直接取自送出紀錄，不重新計算。
只可匯入 ..models，避免循環匯入。
"""
import csv
import io

from ..models import Room, iso

COLUMNS = ["輪次", "題號", "題組", "組別", "答案", "接收時間", "排名"]

# 以這些字元開頭的文字可能被試算表當成公式（CSV injection）
_FORMULA_PREFIXES = ("=", "+", "-", "@", "\t", "\r", "\n")


def safe_cell(text: str) -> str:
    """公式字元開頭時補一個單引號，使試算表視為文字；去掉第一個字元即為原文。"""
    if text and text[0] in _FORMULA_PREFIXES:
        return "'" + text
    return text


def build_rows(room: Room) -> list[list]:
    """每筆有效送出一列（所有輪次；題組成員各一列），依「輪次 → 題目順序 → 名次」排序。"""
    order = {q.id: i for i, q in enumerate(room.questions)}
    label = {q.id: q.label for q in room.questions}
    bundle_label = {
        b.id: "、".join(label.get(qid, qid) for qid in b.question_ids) for b in room.bundles
    }
    subs = sorted(
        room.submissions,
        key=lambda s: (s.round, order.get(s.question_id, len(order)), s.rank),
    )
    return [
        [
            s.round,
            label.get(s.question_id, s.question_id),
            bundle_label.get(s.bundle_id, "") if s.bundle_id else "",
            safe_cell(s.group_name),
            safe_cell(s.answer),
            iso(s.submitted_at),
            s.rank,
        ]
        for s in subs
    ]


def render_csv(room: Room) -> str:
    """標題列＋所有資料列；UTF-8 BOM 開頭（Excel 直接開啟中文不亂碼）、CRLF 換行。"""
    buf = io.StringIO()
    writer = csv.writer(buf, lineterminator="\r\n")
    writer.writerow(COLUMNS)
    writer.writerows(build_rows(room))
    return "﻿" + buf.getvalue()
