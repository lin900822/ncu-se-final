"""Step 9 US1：隨機駁回／恢復序列的性質測試（SC-003、SC-006）。直接以服務層驗證，不經 HTTP。"""
import random
from datetime import datetime, timezone

from app.models import Group, Question
from app.services import bundles, effective, review, rooms, submissions


def _room(n_groups, bundled):
    qs = [Question(id=str(i), number=i, sub=None, label=f"Q{i}", cell=f"A{i}") for i in range(1, 5)]
    room = rooms.create_room()
    room.questions = qs
    if bundled:
        room.bundles = bundles.validate_bundles(qs, [["3", "4"]])
        room.bundle_of = bundles.index_bundles(room.bundles)
    room.phase, room.round = "Answering", 1
    groups = []
    for i in range(n_groups):
        g = Group(name=f"G{i}", normalized_name=f"g{i}", online=True, joined_at=datetime.now(timezone.utc))
        room.groups[g.normalized_name] = g
        groups.append(g)
    return room, groups


def _submit_all(room, groups, bundled, rng):
    order = groups[:]
    rng.shuffle(order)
    for g in order:
        if bundled:
            submissions.submit_bundle(room, g, "B1", {"3": f"{g.name}-3", "4": f"{g.name}-4"})
        else:
            submissions.submit(room, g, "1", f"{g.name}-1")
    room.phase = "Ended"


def _run(seed, bundled):
    rng = random.Random(seed)
    room, groups = _room(rng.randint(3, 6), bundled)
    _submit_all(room, groups, bundled, rng)
    unit = "B1" if bundled else "1"
    original = [(s.group_name, s.question_id, s.answer, s.submitted_at, s.seq, s.rank) for s in room.submissions]
    entries = effective.unit_entries(room, 1)[unit]  # 依原始名次排序
    invalid: set[str] = set()  # 獨立追蹤（不使用 effective 的實作）
    for step in range(rng.randint(5, 15)):
        target = rng.choice(entries)
        action = rng.choice(["invalid", "valid"])
        before = len(room.reviews)
        rec, changed = review.apply_review(
            room, round_no=1, unit_id=unit, group=target.group_name, action=action, reason=f"r{step}"
        )
        want_invalid = action == "invalid"
        is_dup = (target.normalized_name in invalid) == want_invalid
        assert changed is (not is_dup)
        assert len(room.reviews) == before + (0 if is_dup else 1)
        if want_invalid:
            invalid.add(target.normalized_name)
        else:
            invalid.discard(target.normalized_name)

        # (a) 第一名＝原始名次最前且目前有效者
        expected_winner = next((s for s in entries if s.normalized_name not in invalid), None)
        got = effective.effective_winners(room, 1)[unit]
        assert (got.normalized_name if got else None) == (
            expected_winner.normalized_name if expected_winner else None
        )
        # (b) 遞補後名次：排除無效者後 1..n 連續，無效者無名次
        valid_order = [s.normalized_name for s in entries if s.normalized_name not in invalid]
        ranks = effective.succession_ranks(room, 1)
        assert {k: v for k, v in ranks.items() if k[0] == unit} == {
            (unit, n): i for i, n in enumerate(valid_order, start=1)
        }
        # (d) 原始資料全程不變
        assert [(s.group_name, s.question_id, s.answer, s.submitted_at, s.seq, s.rank) for s in room.submissions] == original


def test_random_review_sequences_single_unit_100():
    for seed in range(100):
        _run(seed, bundled=False)


def test_random_review_sequences_bundle_unit_30():
    for seed in range(1000, 1030):
        _run(seed, bundled=True)
