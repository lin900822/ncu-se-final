"""Step 9 US4：匯出 CSV 追加四個審核欄位（審核狀態、遞補後名次、審核理由、審核時間）。"""
import re

from .conftest import auth, get_export, make_ranked_room, parse_csv, post_review
from .test_submission_privacy import flush

HEADER = ["輪次", "題號", "題組", "組別", "答案", "接收時間", "排名", "審核狀態", "遞補後名次", "審核理由", "審核時間", "獲勝狀態", "未獲勝原因"]
TIME_RE = re.compile(r"^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}Z$")
UNIT = "1"


def _close(conns):
    for cm, _ws in conns:
        cm.__exit__(None, None, None)


def _export(client, code, token):
    rows = parse_csv(get_export(client, code, token))
    return rows, {r[3]: r for r in rows[1:]}


def test_header_has_eleven_columns_and_unreviewed_rows_are_valid(client, use_sheet):
    code, token, conns = make_ranked_room(client)
    try:
        rows, by = _export(client, code, token)
        assert rows[0] == HEADER and all(len(r) == 13 for r in rows)
        for g, expected_rank in (("第 1 組", "1"), ("第 2 組", "2"), ("第 3 組", "3")):
            r = by[g]
            assert (r[6], r[7], r[8], r[9], r[10]) == (expected_rank, "有效", expected_rank, "", "")
    finally:
        _close(conns)


def test_rejected_row_and_succession_ranks(client, use_sheet):
    code, token, conns = make_ranked_room(client)
    try:
        _, before = _export(client, code, token)
        post_review(client, code, token, UNIT, "第 1 組", "invalid", "答案錯誤")
        rows, by = _export(client, code, token)
        g1, g2, g3 = by["第 1 組"], by["第 2 組"], by["第 3 組"]
        assert (g1[6], g1[7], g1[8], g1[9]) == ("1", "無效", "", "答案錯誤")  # 原始排名不變、遞補後名次空白
        assert TIME_RE.match(g1[10])
        assert (g2[6], g2[7], g2[8], g2[9], g2[10]) == ("2", "有效", "1", "", "")
        assert (g3[6], g3[7], g3[8]) == ("3", "有效", "2")
        # 前七欄內容、排序、列數與審核前完全相同
        assert [r[:7] for r in rows[1:]] == [r[:7] for r in _rows_of(before)]
    finally:
        _close(conns)


def _rows_of(by):
    return sorted(by.values(), key=lambda r: (r[0], r[1], int(r[6])))


def test_restored_row_is_valid_with_restore_reason_and_time(client, use_sheet):
    code, token, conns = make_ranked_room(client)
    try:
        post_review(client, code, token, UNIT, "第 1 組", "invalid", "答案錯誤")
        post_review(client, code, token, UNIT, "第 1 組", "valid", "誤判")
        _, by = _export(client, code, token)
        g1 = by["第 1 組"]
        assert (g1[7], g1[8], g1[9]) == ("有效", "1", "誤判") and TIME_RE.match(g1[10])
        assert [by[g][8] for g in ("第 2 組", "第 3 組")] == ["2", "3"]  # 回到原始名次
    finally:
        _close(conns)


def test_bundle_rows_share_review_columns(client, use_sheet):
    code, token, conns = make_ranked_room(client, bundles=(("3", "4"),), groups=("第 1 組", "第 2 組"), end=False)
    try:
        for i, (_cm, ws) in enumerate(conns, start=1):
            ws.send_json({"type": "submit_bundle", "bundleId": "B1", "answers": {"3": f"g{i}-3", "4": f"g{i}-4"}})
            flush(ws)
        assert client.post(f"/api/rooms/{code}/phase/end", headers=auth(token)).status_code == 200
        post_review(client, code, token, "B1", "第 1 組", "invalid", "整組錯誤")
        rows, _ = _export(client, code, token)
        mine = [r for r in rows[1:] if r[2] == "Q3、Q4" and r[3] == "第 1 組"]
        assert len(mine) == 2 and {tuple(r[7:]) for r in mine} == {tuple(mine[0][7:])}
        assert mine[0][7:10] == ["無效", "", "整組錯誤"]
        other = [r for r in rows[1:] if r[2] == "Q3、Q4" and r[3] == "第 2 組"]
        assert {r[7] for r in other} == {"有效"} and {r[8] for r in other} == {"1"}
    finally:
        _close(conns)


def test_reason_is_protected_against_formula_injection(client, use_sheet):
    code, token, conns = make_ranked_room(client)
    try:
        post_review(client, code, token, UNIT, "第 1 組", "invalid", "=1+1")
        _, by = _export(client, code, token)
        assert by["第 1 組"][9] == "'=1+1"
    finally:
        _close(conns)
