"""結果公布：結算後（Ended）由各題名次 1 的送出推導，不另存任何狀態。

保密（原則 III）：僅在結算後可對學生公布，內容僅限各題第 1 名的組名與答案；
其他組別的組名／答案、名次（rank／seq）、時間、看板一律不得出現。
階段為 Ended 後 submit() 拒絕新送出，該輪紀錄凍結，因此結果確定且不可改寫。
只可匯入 ..models，避免循環匯入。
"""
from ..models import Room


def build_result(room: Room) -> dict | None:
    if room.phase != "Ended":
        return None
    winners = {
        s.question_id: s
        for s in room.submissions
        if s.round == room.round and s.rank == 1
    }
    results = []
    for q in room.questions:
        w = winners.get(q.id)
        results.append(
            {
                "questionId": q.id,
                "winnerGroup": w.group_name if w else None,
                "answer": w.answer if w else None,
            }
        )
    return {"round": room.round, "results": results}
