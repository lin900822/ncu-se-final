from urllib.parse import quote

from fastapi import APIRouter, Header, Response
from pydantic import BaseModel

from ..models import AppError, bundle_public, err, iso, question_public, utcnow
from ..services import bundles as bundles_service
from ..services import export, phase, review, rooms, sheets

router = APIRouter(prefix="/api/rooms")


class RecoverBody(BaseModel):
    recoveryCode: str


def _bearer(authorization: str | None) -> str | None:
    if authorization and authorization.lower().startswith("bearer "):
        return authorization[7:].strip()
    return None


class ReviewBody(BaseModel):
    round: int
    unitId: str
    group: str
    action: str
    reason: str


class CreateBody(BaseModel):
    sheetUrl: str | None = None
    fingerprint: str | None = None
    bundles: list[list[str]] | None = None  # 題組：每個內層為相鄰題目的 questionId（Step 7）


@router.post("", status_code=201)
async def create_room(body: CreateBody | None = None):
    sheet = None
    bundles = []
    if body and (body.sheetUrl or body.fingerprint):
        if not (body.sheetUrl and body.fingerprint):
            raise err("BAD_REQUEST")
        # 先完整讀取並驗證，全部通過後才建立房間（任何錯誤都不留下房間）
        sheet = await sheets.read_questions(body.sheetUrl)
        if sheet.source.fingerprint != body.fingerprint:
            raise err("SHEET_CHANGED")
        # 指紋比對通過後、建立房間前驗證題組；任何錯誤都不留下房間
        bundles = bundles_service.validate_bundles(sheet.questions, body.bundles)
    elif body and body.bundles:
        raise err("BUNDLES_INVALID", {"reason": "NO_QUESTIONS", "questionIds": []})
    room = rooms.create_room(sheet, bundles)
    return {
        "code": room.code,
        "teacherToken": room.teacher_token,
        "recoveryCode": room.recovery_code,
        "createdAt": iso(room.created_at),
        "sheetTitle": room.sheet.sheet_title if room.sheet else None,
        "questions": [question_public(q) for q in room.questions],
        "bundles": [bundle_public(b) for b in room.bundles],
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


@router.post("/{code}/reviews")
async def review_submission(
    code: str, body: ReviewBody, authorization: str | None = Header(default=None)
):
    """老師駁回／恢復某組在某搶答單位的送出（僅搶答結束後、最新一輪；憑證只讀標頭）。"""
    room = rooms.verify_teacher(code, _bearer(authorization))
    record, changed = review.apply_review(
        room,
        round_no=body.round,
        unit_id=body.unitId,
        group=body.group,
        action=body.action,
        reason=body.reason,
    )
    if changed:
        await review.publish_review(room)
    out = {
        "changed": changed,
        "round": room.round,
        "unitId": body.unitId,
        "group": record.group_name if record else body.group,
        "action": "invalid" if record and record.action == "Invalid" else "valid",
    }
    if record:
        out["reviewedAt"] = iso(record.reviewed_at)
    return out


@router.get("/{code}/records.csv")
async def export_records(code: str, authorization: str | None = Header(default=None)):
    """匯出所有輪次的作答明細 CSV（僅老師；憑證只讀標頭，不讀網址參數）。唯讀，不更新活動時間。"""
    try:
        # verify_teacher 不檢查房間狀態：房間結束後在保留期（24 小時）內仍可匯出
        room = rooms.verify_teacher(code, _bearer(authorization))
    except AppError as e:
        if e.code == "ROOM_NOT_FOUND":
            # 房間已被清除（超過保留期或服務重啟）：只在此端點改為明確的「紀錄已不存在」
            raise err("RECORDS_GONE") from None
        raise
    if not room.submissions:
        raise err("NO_RECORDS")
    body = export.render_csv(room)
    ymd = utcnow().strftime("%Y%m%d")
    return Response(
        content=body.encode("utf-8"),
        media_type="text/csv; charset=utf-8",
        headers={
            "Content-Disposition": (
                f'attachment; filename="records_{room.code}_{ymd}.csv"; '
                f"filename*=UTF-8''{quote(f'搶答紀錄_{room.code}_{ymd}.csv')}"
            ),
            "Cache-Control": "no-store",
        },
    )


@router.get("/{code}/status")
async def status(code: str):
    room = rooms.get_room(code)
    return {"open": room.status == "Open"}
