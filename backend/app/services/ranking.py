"""順位看板：由送出紀錄即時推導（不另存任何狀態）。

僅供老師連線；嚴禁送往學生連線（原則 III）。名次本身由 submissions.submit()
於送出的同一同步區段內賦予，此處只負責整理成看板。
"""
from ..models import Room, iso


def build_board(room: Room) -> dict:
    current = [s for s in room.submissions if s.round == room.round]
    by_question: dict[str, list] = {}
    for s in current:
        by_question.setdefault(s.question_id, []).append(s)

    questions = []
    tally: dict[str, int] = {}
    for q in room.questions:
        subs = sorted(by_question.get(q.id, []), key=lambda s: s.rank)
        leader = subs[0].group_name if subs else None
        if leader is not None:
            tally[leader] = tally.get(leader, 0) + 1
        questions.append(
            {
                "questionId": q.id,
                "leader": leader,
                "submittedCount": len(subs),
                "ranking": [
                    {"rank": s.rank, "group": s.group_name, "submittedAt": iso(s.submitted_at)}
                    for s in subs
                ],
            }
        )
    lead_tally = [
        {"group": g, "leadCount": n}
        for g, n in sorted(tally.items(), key=lambda kv: (-kv[1], kv[0]))
    ]
    return {"type": "board", "round": room.round, "questions": questions, "leadTally": lead_tally}
