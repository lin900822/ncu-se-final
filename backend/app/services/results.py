"""結果公布：結算後（Ended）由各單位的「有效第一名」推導，不另存任何狀態。

有效第一名＝原始名次最前且未被老師駁回者（Step 9）；沒有任何審核時等於各題名次 1。
保密（原則 III）：僅在結算後可對學生公布，內容僅限各題有效第 1 名的組名與答案；
其他組別的組名／答案、被駁回者與理由、名次（rank／seq）、時間、看板一律不得出現。
只可匯入 ..models、bundles、effective，避免循環匯入。
"""
from ..models import Room
from . import bundles, effective


def build_result(room: Room) -> dict | None:
    if room.phase != "Ended":
        return None
    winners = effective.effective_winners(room, room.round)
    entries = effective.unit_entries(room, room.round)
    results = []
    for q in room.questions:
        unit = bundles.unit_of(room, q.id)
        w = winners.get(unit)
        mine = room.submission_index.get((room.round, w.normalized_name, q.id)) if w else None
        item = {
            "questionId": q.id,
            "winnerGroup": w.group_name if w else None,
            "answer": mine.answer if mine else None,
        }
        if w is None and entries.get(unit):
            # 有送出但全部被駁回：學生端據此顯示「無有效答案」（只表示曾有送出，不含組名／答案／理由）
            item["noValid"] = True
        results.append(item)
    return {"round": room.round, "results": results}
