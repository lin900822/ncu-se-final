"""學習單解析（純函式）：格線＋合併範圍 → 題目清單。

規則見 specs/003-sheet-question-form/research.md D5：
以表頭「題號／題目／作答」定位；題號欄為數字者開啟一個題號（含垂直合併）；
題號範圍內「題目」欄有文字的每一列是一個作答格；作答欄最左格為「（n）」標籤時，
作答格位於其右一格，否則為作答欄最左格。每個作答格視為獨立的一題（扁平清單）。
"""
import re
import unicodedata
from dataclasses import dataclass, field

from ..models import Question, err

MAX_QUESTIONS = 50
MAX_TEXT_LENGTH = 2000

_NUMBER = re.compile(r"^[Qq]?\s*(\d+)(?:\.0+)?$")
_SUBLABEL = re.compile(r"^[（(]\s*(\d+)\s*[）)]$")


@dataclass
class Grid:
    """rows: 顯示字串（空格為 ""）；merges: 0 起算、結束不含的 (r0, r1, c0, c1)。"""

    rows: list[list[str]] = field(default_factory=list)
    merges: list[tuple[int, int, int, int]] = field(default_factory=list)

    def merge_at(self, r: int, c: int) -> tuple[int, int, int, int] | None:
        for m in self.merges:
            if m[0] <= r < m[1] and m[2] <= c < m[3]:
                return m
        return None

    def raw(self, r: int, c: int) -> str:
        if 0 <= r < len(self.rows) and 0 <= c < len(self.rows[r]):
            return self.rows[r][c] or ""
        return ""

    def value(self, r: int, c: int) -> str:
        """合併範圍取左上角的值。"""
        m = self.merge_at(r, c)
        if m:
            return self.raw(m[0], m[2])
        return self.raw(r, c)


def _norm(text: str) -> str:
    return unicodedata.normalize("NFKC", text or "").strip()


def _col_letter(c: int) -> str:
    s = ""
    c += 1
    while c:
        c, rem = divmod(c - 1, 26)
        s = chr(65 + rem) + s
    return s


def _address(title: str, r: int, c: int) -> str:
    return f"'{title.replace(chr(39), chr(39) * 2)}'!{_col_letter(c)}{r + 1}"


def _find_header(grid: Grid) -> tuple[int, int, int, int, int] | None:
    """回傳 (header_row, 題號欄, 題目欄, 作答區起欄, 作答區止欄(不含))。"""
    for r, row in enumerate(grid.rows):
        cols: dict[str, int] = {}
        for c, v in enumerate(row):
            n = _norm(v)
            if n in ("題號", "題目", "作答") and n not in cols:
                cols[n] = c
        if len(cols) == 3:
            m = grid.merge_at(r, cols["作答"])
            a0, a1 = (m[2], m[3]) if m else (cols["作答"], cols["作答"] + 1)
            return r, cols["題號"], cols["題目"], a0, a1
    return None


def _parse_number(text: str) -> int | None:
    m = _NUMBER.match(_norm(text))
    if not m:
        return None
    n = int(m.group(1))
    return n if n >= 1 else None


def parse_questions(grid: Grid, sheet_title: str) -> list[Question]:
    header = _find_header(grid)
    if header is None:
        raise err("SHEET_FORMAT_UNRECOGNIZED")
    hr, no_col, q_col, a0, _a1 = header

    # (題號, [(列, 小題編號或 None)])
    groups: list[tuple[int, list[tuple[int, int | None]]]] = []
    numbers: list[int] = []
    r = hr + 1
    last = len(grid.rows)
    while r < last:
        m = grid.merge_at(r, no_col)
        if m and m[0] != r:  # 合併範圍的後續列，已由左上角處理
            r += 1
            continue
        n = _parse_number(grid.value(r, no_col))
        if n is None:
            r += 1
            continue
        if m:
            rows = list(range(m[0], min(m[1], last)))
        else:
            rows = [r]
            nxt = r + 1
            # 未合併時，後續「題號為空且題目有文字」的列也屬於同一題號
            while (
                nxt < last
                and not _norm(grid.value(nxt, no_col))
                and _norm(grid.value(nxt, q_col))
            ):
                rows.append(nxt)
                nxt += 1
        blanks: list[tuple[int, int | None]] = []
        for row in rows:
            if not _norm(grid.value(row, q_col)):
                continue
            lab = _SUBLABEL.match(_norm(grid.raw(row, a0)))
            blanks.append((row, int(lab.group(1)) if lab else None))
        numbers.append(n)
        groups.append((n, blanks))
        r = rows[-1] + 1

    if not groups:
        raise err("SHEET_NO_QUESTIONS")

    duplicates = sorted({n for n in numbers if numbers.count(n) > 1})
    missing = [n for n in range(1, max(numbers) + 1) if n not in set(numbers)]
    invalid_subs: list[int] = []
    empty: list[int] = []
    for n, blanks in groups:
        if not blanks:
            empty.append(n)
            continue
        subs = [s for _, s in blanks]
        if len(blanks) == 1 and subs[0] is None:
            continue
        if None in subs or subs != list(range(1, len(blanks) + 1)):
            invalid_subs.append(n)
    if duplicates or missing or invalid_subs or empty:
        details: dict = {
            "duplicates": duplicates,
            "missing": missing,
            "invalidSubs": sorted(set(invalid_subs)),
        }
        if empty:
            details["empty"] = sorted(set(empty))
        raise err("SHEET_QUESTIONS_INVALID", details)

    questions: list[Question] = []
    for n, blanks in sorted(groups, key=lambda g: g[0]):
        for row, sub in blanks:
            if sub is None:
                col, qid, label = a0, str(n), f"Q{n}"
            else:
                col, qid, label = a0 + 1, f"{n}-{sub}", f"Q{n}（{sub}）"
            questions.append(
                Question(
                    id=qid,
                    number=n,
                    sub=sub,
                    label=label,
                    cell=_address(sheet_title, row, col),
                    text=grid.value(row, q_col).strip()[:MAX_TEXT_LENGTH],
                )
            )
    if len(questions) > MAX_QUESTIONS:
        raise err("SHEET_TOO_MANY_QUESTIONS")
    return questions
