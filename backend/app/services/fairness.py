"""公平規則（Step 11）：建立房間時驗證每組獲勝上限與冷卻秒數。

規則在建立房間時確定、之後不可修改（憲章原則 IV：進行中不得更動）；只依賴 ..models。
"""
from ..models import FairnessRule, Question, err

MAX_COOLDOWN_SECONDS = 600


def _invalid(reason: str):
    return err("FAIRNESS_INVALID", {"reason": reason})


def _is_int(v) -> bool:
    return isinstance(v, int) and not isinstance(v, bool)


def validate_fairness(questions: list[Question], raw) -> FairnessRule:
    """驗證規則並回傳 FairnessRule；預設（不限制）回傳 FairnessRule()。

    - 省略、None、空物件、或 winCap 為 None 且 cooldownSeconds 為 0／省略 → 預設；
    - 欄位型別須為整數（布林不算）；沒有題目時不得設定；
    - winCap 須為 1..題目數；cooldownSeconds 須為 0..600。
    """
    if not raw:
        return FairnessRule()
    if not isinstance(raw, dict):
        raise _invalid("TYPE")
    win_cap = raw.get("winCap")
    cooldown = raw.get("cooldownSeconds", 0)
    if cooldown is None:
        cooldown = 0
    if win_cap is not None and not _is_int(win_cap):
        raise _invalid("TYPE")
    if not _is_int(cooldown):
        raise _invalid("TYPE")
    if win_cap is None and cooldown == 0:
        return FairnessRule()
    if not questions:
        raise _invalid("NO_QUESTIONS")
    if win_cap is not None and not (1 <= win_cap <= len(questions)):
        raise _invalid("WIN_CAP_RANGE")
    if not (0 <= cooldown <= MAX_COOLDOWN_SECONDS):
        raise _invalid("COOLDOWN_RANGE")
    return FairnessRule(win_cap=win_cap, cooldown_seconds=cooldown)
