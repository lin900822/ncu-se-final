"""順位看板：由送出紀錄與審核紀錄即時推導（不另存任何狀態）。

僅供老師連線；嚴禁送往學生連線（原則 III）。名次本身由 submissions.submit()
於送出的同一同步區段內賦予（原始名次永不改寫），此處只負責整理成看板；
每筆另帶審核狀態與遞補後名次（Step 9），leader／leadTally 取「有效第一名」。
Step 11：leader／leadTally 為公平規則（獲勝上限、冷卻）讓位後的結果（題組 N 題計 N），
每筆另帶 outcome，頂層帶 fairness（規則；無規則為 None）。
"""
from ..models import Room, fairness_public, iso
from . import bundles, effective


def build_board(room: Room) -> dict:
    round_no = room.round
    by_question: dict[str, list] = {}
    for s in room.submissions:
        if s.round == round_no:
            by_question.setdefault(s.question_id, []).append(s)

    invalid = effective.invalid_keys(room, round_no)
    state = effective.review_state(room, round_no)
    succession = effective.succession_ranks(room, round_no)
    allocation = effective.allocate(room, round_no)  # 含公平規則（上限／冷卻）的首選資格分配
    winners = allocation.winners

    questions = []
    tally: dict[str, int] = {}
    for q in room.questions:
        unit = bundles.unit_of(room, q.id)
        subs = sorted(by_question.get(q.id, []), key=lambda s: s.rank)
        w = winners.get(unit)
        leader = w.group_name if w else None
        if leader is not None:
            tally[leader] = tally.get(leader, 0) + 1
        ranking = []
        for s in subs:
            key = (s.normalized_name, unit)
            last = state.get(key)
            ranking.append(
                {
                    "rank": s.rank,  # 原始名次（不變）
                    "group": s.group_name,
                    "submittedAt": iso(s.submitted_at),
                    "answer": s.answer,  # 僅老師看板
                    "status": "Invalid" if key in invalid else "Valid",
                    "successionRank": succession.get((unit, s.normalized_name)),
                    "reason": last.reason if last else None,
                    # Step 11：本筆在公平規則下的結果（Won／Kept／Behind／Invalid／YieldedCap／YieldedCooldown）
                    "outcome": allocation.status.get((unit, s.normalized_name), "Won"),
                }
            )
        questions.append(
            {
                "questionId": q.id,
                "bundleId": room.bundle_of.get(q.id),  # 題組（Step 7）；未綁定為 None
                "leader": leader,  # 有效第一名
                "submittedCount": len(subs),
                "ranking": ranking,
            }
        )
    lead_tally = [
        {"group": g, "leadCount": n}
        for g, n in sorted(tally.items(), key=lambda kv: (-kv[1], kv[0]))
    ]
    return {
        "type": "board",
        "round": round_no,
        "fairness": fairness_public(room.fairness),  # 無規則為 None
        "questions": questions,
        "leadTally": lead_tally,
    }
