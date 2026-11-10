from fastapi import APIRouter, Header
from pydantic import BaseModel

from ..models import err, iso, question_public
from ..services import phase, rooms, sheets

router = APIRouter(prefix="/api/rooms")


class RecoverBody(BaseModel):
    recoveryCode: str


def _bearer(authorization: str | None) -> str | None:
    if authorization and authorization.lower().startswith("bearer "):
        return authorization[7:].strip()
    return None


class CreateBody(BaseModel):
    sheetUrl: str | None = None
    fingerprint: str | None = None


@router.post("", status_code=201)
async def create_room(body: CreateBody | None = None):
    sheet = None
    if body and (body.sheetUrl or body.fingerprint):
        if not (body.sheetUrl and body.fingerprint):
            raise err("BAD_REQUEST")
        # 先完整讀取並驗證，全部通過後才建立房間（任何錯誤都不留下房間）
        sheet = await sheets.read_questions(body.sheetUrl)
        if sheet.source.fingerprint != body.fingerprint:
            raise err("SHEET_CHANGED")
    room = rooms.create_room(sheet)
    return {
        "code": room.code,
        "teacherToken": room.teacher_token,
        "recoveryCode": room.recovery_code,
        "createdAt": iso(room.created_at),
        "sheetTitle": room.sheet.sheet_title if room.sheet else None,
        "questions": [question_public(q) for q in room.questions],
    }


@router.post("/recover")
async def recover(body: RecoverBody):
    room = await rooms.recover(body.recoveryCode)
    return {"code": room.code, "teacherToken": room.teacher_token, "recoveryCode": room.recovery_code}


@router.post("/{code}/close")
async def close(code: str, authorization: str | None = Header(default=None)):
    room = rooms.verify_teacher(code, _bearer(authorization))
    await rooms.close_room(room, "Manual")
    return {"status": "Closed", "closedReason": room.closed_reason}


@router.post("/{code}/phase/start")
async def start_phase(code: str, authorization: str | None = Header(default=None)):
    room = rooms.verify_teacher(code, _bearer(authorization))
    p, rnd, changed = await phase.start_answering(room)
    return {"phase": p, "round": rnd, "changed": changed}


@router.post("/{code}/phase/end")
async def end_phase(code: str, authorization: str | None = Header(default=None)):
    room = rooms.verify_teacher(code, _bearer(authorization))
    p, rnd, changed = await phase.end_answering(room)
    return {"phase": p, "round": rnd, "changed": changed}


@router.get("/{code}/status")
async def status(code: str):
    room = rooms.get_room(code)
    return {"open": room.status == "Open"}
