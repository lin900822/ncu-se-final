from pathlib import Path

import pytest

from app.models import AppError
from app.sheets.parser import Grid, parse_questions

from .grid_helper import xlsx_to_grid

FIX = Path(__file__).parent / "fixtures"


def _ids(qs):
    return [q.id for q in qs]


def test_single_sample():
    grid, title = xlsx_to_grid(FIX / "single.xlsx")
    qs = parse_questions(grid, title)
    assert _ids(qs) == ["1", "2", "3", "4", "5", "6"]
    assert all(q.sub is None for q in qs)
    assert [q.label for q in qs] == [f"Q{i}" for i in range(1, 7)]
    assert [q.cell for q in qs] == [f"'學習單'!G{r}" for r in (5, 7, 9, 11, 13, 15)]


def test_group_sample():
    grid, title = xlsx_to_grid(FIX / "group.xlsx")
    qs = parse_questions(grid, title)
    assert _ids(qs) == ["1-1", "1-2", "2-1", "2-2", "3", "4"]
    assert [q.label for q in qs] == ["Q1（1）", "Q1（2）", "Q2（1）", "Q2（2）", "Q3", "Q4"]
    assert [q.cell for q in qs] == [
        "'學習單'!H5",
        "'學習單'!H6",
        "'學習單'!H8",
        "'學習單'!H9",
        "'學習單'!G11",
        "'學習單'!G13",
    ]
    assert [q.sub for q in qs] == [1, 2, 1, 2, None, None]


def make_grid(numbers, header=True, text="題目文字"):
    rows = [["", "", "", "", "", "", "", ""]]
    if header:
        rows.append(["", "題號", "題目", "", "", "", "作答", ""])
    for n in numbers:
        rows.append(["", str(n), text, "", "", "", "", ""])
    return Grid(rows=rows, merges=[])


def test_duplicates_and_missing():
    with pytest.raises(AppError) as e:
        parse_questions(make_grid([1, 2, 2, 4]), "S")
    assert e.value.code == "SHEET_QUESTIONS_INVALID"
    assert e.value.details["duplicates"] == [2]
    assert e.value.details["missing"] == [3]


def test_invalid_subs():
    grid = Grid(
        rows=[
            ["", "題號", "題目", "", "", "", "作答", ""],
            ["", "1", "a", "", "", "", "（1）", ""],
            ["", "", "b", "", "", "", "（3）", ""],
        ],
        merges=[(1, 3, 1, 2)],
    )
    with pytest.raises(AppError) as e:
        parse_questions(grid, "S")
    assert e.value.code == "SHEET_QUESTIONS_INVALID"
    assert e.value.details["invalidSubs"] == [1]


def test_no_header():
    with pytest.raises(AppError) as e:
        parse_questions(make_grid([1], header=False), "S")
    assert e.value.code == "SHEET_FORMAT_UNRECOGNIZED"


def test_header_but_no_numbers():
    with pytest.raises(AppError) as e:
        parse_questions(make_grid([]), "S")
    assert e.value.code == "SHEET_NO_QUESTIONS"


def test_too_many():
    with pytest.raises(AppError) as e:
        parse_questions(make_grid(range(1, 52)), "S")
    assert e.value.code == "SHEET_TOO_MANY_QUESTIONS"
    assert len(parse_questions(make_grid(range(1, 51)), "S")) == 50


def test_number_tolerance_and_numeric_order():
    grid = make_grid([])
    for n in ["１", " 2 ", "Q3", "4.0"]:
        grid.rows.append(["", n, "題目", "", "", "", "", ""])
    qs = parse_questions(grid, "S")
    assert [q.number for q in qs] == [1, 2, 3, 4]
    # 數字排序：10 排在 9 之後
    qs = parse_questions(make_grid([10, 9, 8, 7, 6, 5, 4, 3, 2, 1]), "S")
    assert [q.number for q in qs] == list(range(1, 11))


def test_non_numeric_cells_ignored_and_quote_in_title():
    grid = make_grid([1])
    grid.rows.append(["", "備註：請小心", "", "", "", "", "", ""])
    qs = parse_questions(grid, "O'Neil")
    assert len(qs) == 1
    assert qs[0].cell == "'O''Neil'!G3"


def test_question_text_extracted():
    grid, title = xlsx_to_grid(FIX / "single.xlsx")
    qs = parse_questions(grid, title)
    assert "英文縮寫" in qs[0].text and "二進位" in qs[1].text
    grid, title = xlsx_to_grid(FIX / "group.xlsx")
    qs = {q.id: q.text for q in parse_questions(grid, title)}
    assert "Windows" in qs["1-2"] and "英文簡稱" in qs["1-1"]


def test_text_truncated():
    qs = parse_questions(make_grid([1], text="字" * 5000), "S")
    assert len(qs[0].text) == 2000
