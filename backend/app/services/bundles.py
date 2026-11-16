"""題組設定：建立房間時驗證並整理老師綁定的相鄰題目；之後只供查詢。

題組是房間層級的「送出單位設定」，不改變題目本身（原則 I）。
只可匯入 ..models，避免循環匯入。
"""
from ..models import Question, QuestionBundle, Room, err


def _invalid(reason: str, question_ids: list[str]):
    return err("BUNDLES_INVALID", {"reason": reason, "questionIds": question_ids})


def validate_bundles(questions: list[Question], raw: list[list[str]] | None) -> list[QuestionBundle]:
    """驗證題組設定；通過則回傳依題目順序整理、編號為 B1、B2… 的題組。

    規則：每組 ≥ 2 題、成員須為本房間題目、一題最多屬於一個題組、成員在題目清單中連續相鄰。
    第一個錯誤即丟出 BUNDLES_INVALID（details.reason 說明原因）。
    """
    if not raw:
        return []
    if not questions:
        raise _invalid("NO_QUESTIONS", [])
    index = {q.id: i for i, q in enumerate(questions)}
    used: set[str] = set()
    groups: list[list[str]] = []
    for members in raw:
        unknown = [qid for qid in members if qid not in index]
        if unknown:
            raise _invalid("UNKNOWN_QUESTION", unknown)
        dup = sorted({qid for qid in members if members.count(qid) > 1 or qid in used}, key=index.get)
        if dup:
            raise _invalid("OVERLAP", dup)
        ordered = sorted(members, key=index.get)
        if len(ordered) < 2:
            raise _invalid("TOO_FEW", ordered)
        positions = [index[qid] for qid in ordered]
        if positions[-1] - positions[0] + 1 != len(positions):
            raise _invalid("NOT_ADJACENT", ordered)
        used.update(ordered)
        groups.append(ordered)
    groups.sort(key=lambda g: index[g[0]])
    return [QuestionBundle(id=f"B{i}", question_ids=g) for i, g in enumerate(groups, start=1)]


def index_bundles(bundles: list[QuestionBundle]) -> dict[str, str]:
    """questionId -> bundleId。"""
    return {qid: b.id for b in bundles for qid in b.question_ids}


def unit_of(room: Room, question_id: str) -> str:
    """搶答單位：題目所屬題組 id；未綁定時為題目 id。"""
    return room.bundle_of.get(question_id, question_id)


def get_bundle(room: Room, bundle_id: str) -> QuestionBundle | None:
    return next((b for b in room.bundles if b.id == bundle_id), None)
