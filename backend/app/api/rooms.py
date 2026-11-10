from fastapi import APIRouter, Header
from pydantic import BaseModel

from ..models import iso
from ..services import rooms

router = APIRouter(prefix="/api/rooms")


class RecoverBody(BaseModel):
    recoveryCode: str


def _bearer(authorization: str | None) -> str | None:
    if authorization and authorization.lower().startswith("bearer "):
        return authorization[7:].strip()
    return None


@router.post("", status_code=201)
async def create_room():
    room = rooms.create_room()
    return {
        "code": room.code,
        "teacherToken": room.teacher_token,
        "recoveryCode": room.recovery_code,
        "createdAt": iso(room.created_at),
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


@router.get("/{code}/status")
async def status(code: str):
    room = rooms.get_room(code)
    return {"open": room.status == "Open"}
