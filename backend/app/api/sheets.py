from fastapi import APIRouter
from pydantic import BaseModel

from ..services import sheets

router = APIRouter(prefix="/api/sheets")


class PreviewBody(BaseModel):
    url: str


@router.post("/preview")
async def preview(body: PreviewBody):
    return await sheets.preview(body.url)
