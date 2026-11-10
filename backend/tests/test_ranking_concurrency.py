"""並發送出的名次必須唯一且連續（原則 II、SC-001）。"""
import asyncio
from datetime import datetime, timezone

from app.models import Group, Question
from app.services import rooms, submissions


def _room(n_groups):
    room = rooms.create_room()
    room.questions = [Question(id="1", number=1, sub=None, label="Q1", cell="A1", text="t")]
    room.phase = "Answering"
    room.round = 1
    groups = []
    for i in range(n_groups):
        g = Group(name=f"G{i}", normalized_name=f"g{i}", online=True, joined_at=datetime.now(timezone.utc))
        room.groups[g.normalized_name] = g
        groups.append(g)
    return room, groups


async def _submit(room, g, delay):
    await asyncio.sleep(delay)
    return submissions.submit(room, g, "1", f"ans-{g.name}")


def test_concurrent_ranks_unique_100_rounds():
    async def run():
        for _ in range(100):
            room, groups = _room(5)
            res = await asyncio.gather(*[_submit(room, g, 0) for g in groups])
            assert all(created for _, created in res)
            assert sorted(s.rank for s in room.submissions) == [1, 2, 3, 4, 5]
            assert len({s.seq for s in room.submissions}) == 5

    asyncio.run(run())


def test_same_group_concurrent_one_rank():
    async def run():
        room, groups = _room(1)
        res = await asyncio.gather(*[_submit(room, groups[0], 0) for _ in range(10)])
        assert sum(1 for _, c in res if c) == 1
        assert len(room.submissions) == 1 and room.submissions[0].rank == 1

    asyncio.run(run())


def test_identical_timestamps_still_unique(monkeypatch):
    fixed = datetime(2026, 11, 10, tzinfo=timezone.utc)
    monkeypatch.setattr(submissions, "utcnow", lambda: fixed)
    room, groups = _room(3)
    for g in groups:
        submissions.submit(room, g, "1", "x")
    assert [s.rank for s in room.submissions] == [1, 2, 3]
    assert len({s.submitted_at for s in room.submissions}) == 1
