"""提交服務：驗證、防重複、追加（僅追加）。

保密約束（原則 III）：答案內容只能送給「同組視窗」與「老師」；
其他組別只能收到匿名提示 {type, questionId, round}（不含答案、組名、組數、時間）。

題組（Step 7）：整組一次送出、全有或全無；每個成員各追加一筆，共用 seq／時間／名次。
三種受眾：同組＝bundle_submitted（各題答案）；老師＝逐題 submission＋看板；
他組＝bundle_hint {type, bundleId, round}（不含答案、組名、組數、時間）。
"""
from ..models import Group, Room, Submission, err, iso, utcnow
from . import bundles, rooms

MAX_ANSWER_LENGTH = 500


def submit(room: Room, group: Group, question_id: str, answer: str) -> tuple[Submission, bool]:
    """同步（無 await）完成所有檢查與追加，確保階段檢查與去重在同一原子區段。

    回傳 (紀錄, 是否新建)；同組同題同輪已有紀錄時回傳既有紀錄與 False（不新增、不修改）。
    """
    if room.status != "Open" or room.phase != "Answering":
        raise err("PHASE_LOCKED")
    if not any(q.id == question_id for q in room.questions):
        raise err("QUESTION_NOT_FOUND")
    if question_id in room.bundle_of:
        # 題組成員只能整組送出（FR-006）；擋下繞過畫面的單題請求
        raise err("QUESTION_IN_BUNDLE")
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
    rank_key = (room.round, bundles.unit_of(room, question_id))
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


def submit_bundle(
    room: Room, group: Group, bundle_id: str, answers
) -> tuple[list[Submission], bool]:
    """題組整組送出：同步（無 await）完成所有檢查、去重與追加，全有或全無（原則 II）。

    回傳 (各成員紀錄, 是否新建)；同組同題組同輪已送出時回傳既有紀錄與 False。
    任何錯誤都在寫入前丟出，不留下任何一題的紀錄，next_seq／rank_counts 也不變。
    """
    if room.status != "Open" or room.phase != "Answering":
        raise err("PHASE_LOCKED")
    bundle = bundles.get_bundle(room, bundle_id)
    if bundle is None:
        raise err("BUNDLE_NOT_FOUND")
    members = bundle.question_ids
    if not isinstance(answers, dict):
        raise err("BUNDLE_INCOMPLETE", {"questionIds": list(members)})
    order = {q.id: i for i, q in enumerate(room.questions)}
    bad = [
        qid for qid in members
        if not isinstance(answers.get(qid), str) or not answers[qid].strip()
    ]
    extra = [str(k) for k in answers if k not in members]
    if bad or extra:
        problems = sorted(set(bad) | set(extra), key=lambda q: (order.get(q, len(order)), q))
        raise err("BUNDLE_INCOMPLETE", {"questionIds": problems})
    too_long = [qid for qid in members if len(answers[qid]) > MAX_ANSWER_LENGTH]
    if too_long:
        raise err("ANSWER_TOO_LONG", {"questionIds": too_long})
    existing = [room.submission_index.get((room.round, group.normalized_name, qid)) for qid in members]
    if existing[0] is not None:
        # 成員紀錄總是一起寫入：有一筆即代表整組已送出
        return [e for e in existing if e is not None], False
    # 順位仲裁（原則 II）：整個題組只取一次 seq，名次以題組為搶答單位計數
    seq = room.next_seq
    room.next_seq += 1
    rank_key = (room.round, bundle.id)
    rank = room.rank_counts.get(rank_key, 0) + 1
    room.rank_counts[rank_key] = rank
    now = utcnow()  # 時間一律由後端產生，各成員共用
    created = []
    for qid in members:
        sub = Submission(
            group_name=group.name,
            normalized_name=group.normalized_name,
            question_id=qid,
            round=room.round,
            answer=answers[qid],
            submitted_at=now,
            seq=seq,
            rank=rank,
            bundle_id=bundle.id,
        )
        room.submissions.append(sub)
        room.submission_index[(room.round, group.normalized_name, qid)] = sub
        created.append(sub)
    rooms.touch(room)
    return created, True


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
        "bundleId": sub.bundle_id,
    }


def to_other_groups_event(sub: Submission) -> dict:
    """匿名提示：只含題目識別碼與輪次。"""
    return {"type": "question_submitted", "questionId": sub.question_id, "round": sub.round}


def to_bundle_group_event(subs: list[Submission]) -> dict:
    """同組視窗：整張卡片一次切換為已送出（各題答案）。"""
    return {
        "type": "bundle_submitted",
        "bundleId": subs[0].bundle_id,
        "answers": {s.question_id: s.answer for s in subs},
        "round": subs[0].round,
    }


def to_bundle_hint_event(subs: list[Submission]) -> dict:
    """他組匿名提示「本題組已有組別送出」：只含題組識別碼與輪次。"""
    return {"type": "bundle_hint", "bundleId": subs[0].bundle_id, "round": subs[0].round}
