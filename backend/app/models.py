"""資料模型（僅存記憶體）；所有時間皆為後端產生的 UTC。"""
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Literal


def utcnow() -> datetime:
    return datetime.now(timezone.utc)


def iso(dt: datetime) -> str:
    return dt.strftime("%Y-%m-%dT%H:%M:%SZ")


@dataclass
class Group:
    name: str
    normalized_name: str
    online: bool
    joined_at: datetime

    def to_dict(self) -> dict:
        return {"name": self.name, "online": self.online, "joinedAt": iso(self.joined_at)}


@dataclass
class Room:
    code: str
    created_at: datetime
    last_activity_at: datetime
    teacher_token: str
    recovery_code: str
    status: Literal["Open", "Closed"] = "Open"
    closed_reason: Literal["Manual", "IdleTimeout"] | None = None
    closed_at: datetime | None = None
    groups: dict[str, Group] = field(default_factory=dict)


class AppError(Exception):
    def __init__(self, code: str, message: str, http_status: int = 400):
        super().__init__(message)
        self.code = code
        self.message = message
        self.http_status = http_status


_ERRORS = {
    "ROOM_NOT_FOUND": ("找不到該房間", 404),
    "ROOM_CLOSED": ("該房間已結束", 409),
    "RECOVERY_INVALID": ("恢復碼不正確", 404),
    "UNAUTHORIZED": ("無權限操作此房間", 401),
    "NAME_REQUIRED": ("請填寫組名", 400),
    "NAME_TOO_LONG": ("組名最多 20 字元", 400),
    "GROUP_ONLINE": ("該組目前在線", 409),
    "JOIN_TIMEOUT": ("加入逾時，請重試", 400),
    "BAD_REQUEST": ("請求格式錯誤", 400),
}


def err(code: str) -> AppError:
    message, status = _ERRORS[code]
    return AppError(code, message, status)
