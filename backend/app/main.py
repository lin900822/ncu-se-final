import asyncio
import os
from contextlib import asynccontextmanager
from datetime import timedelta

from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse

from .api import rooms as rooms_api
from .api import sheets as sheets_api
from .api import ws as ws_api
from .models import AppError, utcnow
from .realtime import realtime
from .services import rooms
from .store import store

IDLE_SECONDS = int(os.environ.get("ROOM_IDLE_SECONDS", "7200"))
SCAN_SECONDS = int(os.environ.get("ROOM_SCAN_SECONDS", "30"))
CLOSED_RETENTION = timedelta(hours=24)


async def _sweep_once() -> None:
    now = utcnow()
    for room in list(store.rooms.values()):
        if room.status == "Open":
            if realtime.has_connections(room.code):
                rooms.touch(room)  # 有開啟中的連線即視為活動中
            elif (now - room.last_activity_at).total_seconds() >= IDLE_SECONDS:
                await rooms.close_room(room, "IdleTimeout")
        elif room.closed_at and now - room.closed_at >= CLOSED_RETENTION:
            store.remove_room(room.code)


async def _idle_loop() -> None:
    while True:
        await asyncio.sleep(SCAN_SECONDS)
        try:
            await _sweep_once()
        except Exception:
            pass


@asynccontextmanager
async def lifespan(_: FastAPI):
    task = asyncio.create_task(_idle_loop())
    yield
    task.cancel()


app = FastAPI(title="課堂搶答 - 房間與組別", lifespan=lifespan)


@app.exception_handler(AppError)
async def app_error_handler(_: Request, e: AppError):
    error: dict = {"code": e.code, "message": e.message}
    if e.details:
        error["details"] = e.details
    return JSONResponse(status_code=e.http_status, content={"error": error})


app.include_router(rooms_api.router)
app.include_router(sheets_api.router)
app.include_router(ws_api.router)
