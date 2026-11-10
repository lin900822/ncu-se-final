"""Step 7 US3：題組併發送出——全有或全無、名次唯一（原則 II、SC-005）。"""
import asyncio
from datetime import datetime, timezone

from app.models import Group, Question
from app.services import bundles, rooms, submissions


def _room(n_groups):
    qs = [Question(id=str(i), number=i, sub=None, label=f"Q{i}", cell=f"A{i}") for i in range(1, 5)]
    b = bundles.validate_bundles(qs, [["3", "4"]])
    room = rooms.create_room()
    room.questions = qs
    room.bundles = b
    room.bundle_of = bundles.index_bundles(b)
    room.phase = "Answering"
    room.round = 1
    groups = []
    for i in range(n_groups):
        g = Group(name=f"G{i}", normalized_name=f"g{i}", online=True, joined_at=datetime.now(timezone.utc))
        room.groups[g.normalized_name] = g
        groups.append(g)
    return room, groups


async def _send(room, g, tag):
    await asyncio.sleep(0)
    return submissions.submit_bundle(room, g, "B1", {"3": f"{tag}-3", "4": f"{tag}-4"})


def test_same_group_two_windows_never_mixed():
    async def run():
        for _ in range(50):
            room, (g,) = _room(1)
            res = await asyncio.gather(_send(room, g, "A"), _send(room, g, "B"))
            assert sum(1 for _, created in res if created) == 1
            subs = room.submissions
            assert len(subs) == 2
            assert subs[0].seq == subs[1].seq
            # 兩題答案來自同一個視窗
            assert {s.answer.split("-")[0] for s in subs} in ({"A"}, {"B"})

    asyncio.run(run())


def test_two_groups_ranks_unique_per_bundle():
    async def run():
        for _ in range(50):
            room, groups = _room(2)
            await asyncio.gather(*[_send(room, g, g.name) for g in groups])
            by_group = {}
            for s in room.submissions:
                by_group.setdefault(s.group_name, set()).add(s.rank)
            assert all(len(r) == 1 for r in by_group.values())  # 同組各題同名次
            assert sorted(r.pop() for r in by_group.values()) == [1, 2]  # 唯一不並列

    asyncio.run(run())


def test_seq_advances_once_per_bundle_and_single_unaffected():
    room, groups = _room(3)
    before = room.next_seq
    for g in groups:
        submissions.submit_bundle(room, g, "B1", {"3": "x", "4": "y"})
    assert room.next_seq == before + 3
    sub, _ = submissions.submit(room, groups[0], "1", "z")
    assert sub.rank == 1  # 單題名次與題組各自計數
