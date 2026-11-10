"""提交服務：驗證、防重複、追加（僅追加）。

保密約束（原則 III）：答案內容只能送給「同組視窗」與「老師」；
其他組別只能收到匿名提示 {type, questionId, round}（不含答案、組名、組數、時間）。
"""
from ..models import Group, Room, Submission, err, iso, utcnow
from . import rooms

MAX_ANSWER_LENGTH = 500


def submit(room: Room, group: Group, question_id: str, answer: str) -> tuple[Submission, bool]:
    """同步（無 await）完成所有檢查與追加，確保階段檢查與去重在同一原子區段。

    回傳 (紀錄, 是否新建)；同組同題同輪已有紀錄時回傳既有紀錄與 False（不新增、不修改）。
    """
    if room.status != "Open" or room.phase != "Answering":
        raise err("PHASE_LOCKED")
    if not any(q.id == question_id for q in room.questions):
        raise err("QUESTION_NOT_FOUND")
    if not isinstance(answer, str) or not answer.strip():
        raise err("ANSWER_EMPTY")
    if len(answer) > MAX_ANSWER_LENGTH:
        raise err("ANSWER_TOO_LONG")
    key = (room.round, group.normalized_name, question_id)
    existing = room.submission_index.get(key)
    if existing is not None:
        return existing, False
    # 順位仲裁（原則 II）：與去重、追加位於同一無 await 區段；seq 為唯一仲裁鍵，
    # 名次＝同題同輪已有有效送出數＋1；寫入後不再修改。驗證失敗／重複路徑不會走到這裡。
    seq = room.next_seq
    room.next_seq += 1
    rank_key = (room.round, question_id)
    rank = room.rank_counts.get(rank_key, 0) + 1
    room.rank_counts[rank_key] = rank
    sub = Submission(
        group_name=group.name,
        normalized_name=group.normalized_name,
        question_id=question_id,
        round=room.round,
        answer=answer,
        submitted_at=utcnow(),  # 時間一律由後端產生
        seq=seq,
        rank=rank,
    )
    room.submissions.append(sub)
    room.submission_index[key] = sub
    rooms.touch(room)
    return sub, True


def my_submissions(room: Room, group: Group) -> dict[str, str]:
    """該組本輪已送出的 {questionId: answer}（只含自己組）。"""
    return {
        s.question_id: s.answer
        for s in room.submissions
        if s.round == room.round and s.normalized_name == group.normalized_name
    }


def submitted_by_others(room: Room, group: Group) -> list[str]:
    """本輪有其他組送出的題目識別碼（匿名；依題目順序，去重，只含識別碼）。"""
    ids = {
        s.question_id
        for s in room.submissions
        if s.round == room.round and s.normalized_name != group.normalized_name
    }
    return [q.id for q in room.questions if q.id in ids]


def to_group_event(sub: Submission) -> dict:
    return {
        "type": "submitted",
        "questionId": sub.question_id,
        "answer": sub.answer,
        "round": sub.round,
    }


def to_teacher_event(sub: Submission) -> dict:
    return {
        "type": "submission",
        "group": sub.group_name,
        "questionId": sub.question_id,
        "answer": sub.answer,
        "round": sub.round,
        "submittedAt": iso(sub.submitted_at),
        "rank": sub.rank,  # 僅老師可見（原則 III）
    }


def to_other_groups_event(sub: Submission) -> dict:
    """匿名提示：只含題目識別碼與輪次。"""
    return {"type": "question_submitted", "questionId": sub.question_id, "round": sub.round}
