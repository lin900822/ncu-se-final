"""Step 11 隨機屬性測試：隨機送出序列下，allocate() 須與獨立參考實作一致，並滿足不變量。"""
import random
from datetime import datetime, timedelta, timezone

from app.models import FairnessRule, Question, QuestionBundle, ReviewRecord, Room, Submission
from app.services import effective

T0 = datetime(2026, 1, 1, tzinfo=timezone.utc)
GROUPS = ["g1", "g2", "g3", "g4"]


def _build(rng: random.Random):
    n_q = rng.randint(2, 7)
    qids = [str(i + 1) for i in range(n_q)]
    room = Room(code="X", created_at=T0, last_activity_at=T0, teacher_token="t", recovery_code="r")
    room.questions = [Question(id=q, number=int(q), sub=None, label=f"Q{q}", cell="A1") for q in qids]
    # 隨機把相鄰兩題綁成題組
    i = 0
    while i < n_q - 1:
        if rng.random() < 0.3:
            b = QuestionBundle(id=f"B{len(room.bundles) + 1}", question_ids=[qids[i], qids[i + 1]])
            room.bundles.append(b)
            for q in b.question_ids:
                room.bundle_of[q] = b.id
            i += 2
        else:
            i += 1
    cap = rng.choice([None, *range(1, n_q + 1)])
    room.fairness = FairnessRule(win_cap=cap, cooldown_seconds=0)
    room.round = 1
    units = []
    for q in qids:
        u = room.bundle_of.get(q, q)
        if u not in units:
            units.append(u)
    members = {u: [q for q in qids if room.bundle_of.get(q, q) == u] for u in units}
    seq = 0
    claimed = set()
    ranks: dict[str, int] = {}
    for _ in range(rng.randint(0, 25)):
        g, u = rng.choice(GROUPS), rng.choice(units)
        if (g, u) in claimed:
            continue
        claimed.add((g, u))
        seq += 1
        ranks[u] = ranks.get(u, 0) + 1
        for q in members[u]:
            room.submissions.append(
                Submission(g, g, q, 1, "a", T0 + timedelta(seconds=seq), seq, ranks[u], room.bundle_of.get(q))
            )
    for _ in range(rng.randint(0, 4)):  # 隨機審核（只取最後一筆有效）
        if claimed:
            g, u = rng.choice(sorted(claimed))
            act = rng.choice(["Invalid", "Valid"])
            room.reviews.append(ReviewRecord(1, u, g, g, act, "r", T0))
    return room, units, members


def _reference(room, units, members):
    """獨立參考：逐筆依 seq 判定，單位已有人或該組已達上限就略過；最後補保留。"""
    state: dict[tuple[str, str], str] = {}
    for r in room.reviews:
        state[(r.normalized_name, r.unit_id)] = r.action
    bad = {k for k, v in state.items() if v == "Invalid"}
    first: dict[tuple[str, str], Submission] = {}
    for s in room.submissions:
        u = room.bundle_of.get(s.question_id, s.question_id)
        first.setdefault((s.normalized_name, u), s)
    cap = room.fairness.win_cap
    winner: dict[str, str | None] = {}
    count = {g: 0 for g in GROUPS}
    live = sorted((s.seq, u, g) for (g, u), s in first.items() if (g, u) not in bad)
    for _seq, u, g in live:
        if u in winner:
            continue
        if cap is not None and count[g] >= cap:
            continue
        winner[u] = g
        count[g] += len(members[u])
    for u in units:
        cands = [(first[(g, u)].rank, g) for g in GROUPS if (g, u) in first and (g, u) not in bad]
        if u in winner:
            continue
        if cands:
            g = min(cands)[1]
            winner[u] = g
            count[g] += len(members[u])
        elif any((g, u) in first for g in GROUPS):
            winner[u] = None
    return winner, count


def test_allocate_matches_independent_reference_over_random_sequences():
    rng = random.Random(20260111)
    for _ in range(300):
        room, units, members = _build(rng)
        alloc = effective.allocate(room, 1)
        exp_w, exp_c = _reference(room, units, members)
        got = {u: (w.normalized_name if w else None) for u, w in alloc.winners.items()}
        assert got == exp_w
        assert {g: c for g, c in alloc.wins.items() if c} == {g: c for g, c in exp_c.items() if c}
        # 不變量：每個有有效申請的單位都有獲勝者；上限內取得時最多只超過一個單位大小
        cap = room.fairness.win_cap
        if cap is not None:
            kept = {k for k, v in alloc.status.items() if v == "Kept"}
            for g, c in alloc.wins.items():
                kept_n = sum(len(members[u]) for (u, gg) in kept if gg == g)
                assert c - kept_n < cap + max(len(m) for m in members.values())
        # 決定性
        again = effective.allocate(room, 1)
        assert again.status == alloc.status and again.wins == alloc.wins
