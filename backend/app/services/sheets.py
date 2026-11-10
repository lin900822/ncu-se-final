"""學習單服務：讀取試算表 → 題目清單與指紋。"""
import hashlib
from dataclasses import dataclass

from ..config import get_sheets_config
from ..models import Question, SheetSource, err, question_public, utcnow
from ..sheets.client import SheetsClient
from ..sheets.parser import Grid, parse_questions
from ..sheets.url import parse_sheet_url


@dataclass
class ReadResult:
    questions: list[Question]
    source: SheetSource


async def _fetch(spreadsheet_id: str, gid: int | None) -> tuple[Grid, str, int]:
    config = get_sheets_config()
    if config is None:
        raise err("SHEETS_NOT_CONFIGURED")
    return await SheetsClient(config).fetch(spreadsheet_id, gid)


def fingerprint_of(questions: list[Question]) -> str:
    raw = "|".join(f"{q.id}@{q.cell}" for q in questions)
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()


async def read_questions(url: str) -> ReadResult:
    spreadsheet_id, gid = parse_sheet_url(url)
    grid, title, sheet_id = await _fetch(spreadsheet_id, gid)
    questions = parse_questions(grid, title)
    source = SheetSource(
        url=url.strip(),
        spreadsheet_id=spreadsheet_id,
        sheet_id=sheet_id,
        sheet_title=title,
        read_at=utcnow(),
        fingerprint=fingerprint_of(questions),
    )
    return ReadResult(questions=questions, source=source)


async def preview(url: str) -> dict:
    """預覽：不建立房間，且不含儲存格位置。"""
    result = await read_questions(url)
    return {
        "sheetTitle": result.source.sheet_title,
        "questions": [question_public(q) for q in result.questions],
        "fingerprint": result.source.fingerprint,
    }
