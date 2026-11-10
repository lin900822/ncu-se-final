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
class Question:
    """房間內的一個作答格（扁平清單）。`cell` 僅伺服器保存，絕不外送（原則 III）。"""

    id: str  # 單題 "3"；題組小題 "1-2"
    number: int
    sub: int | None
    label: str  # Q3 / Q1（2）
    cell: str  # A1 表示法含分頁名，如 '學習單'!H6
    text: str = ""  # 「題目」欄文字：僅伺服器保存，搶答開始後才送給學生


def question_public(q: Question) -> dict:
    return {"id": q.id, "number": q.number, "sub": q.sub, "label": q.label}


def question_texts(room: "Room") -> dict[str, str]:
    return {q.id: q.text for q in room.questions}


@dataclass
class SheetSource:
    url: str
    spreadsheet_id: str
    sheet_id: int
    sheet_title: str
    read_at: datetime
    fingerprint: str


@dataclass
class PhaseChange:
    """階段變更紀錄（僅追加）；時間為後端 UTC。"""

    phase: Literal["Answering", "Ended"]
    round: int
    changed_at: datetime
    by: str = "Teacher"


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
    phase: Literal["Waiting", "Answering", "Ended"] = "Waiting"
    round: int = 0
    phase_log: list[PhaseChange] = field(default_factory=list)
    sheet: SheetSource | None = None
    questions: list[Question] = field(default_factory=list)


class AppError(Exception):
    def __init__(
        self,
        code: str,
        message: str,
        http_status: int = 400,
        details: dict | None = None,
    ):
        super().__init__(message)
        self.code = code
        self.message = message
        self.http_status = http_status
        self.details = details


_ERRORS = {
    "ROOM_NOT_FOUND": ("找不到該房間", 404),
    "ROOM_CLOSED": ("該房間已結束", 409),
    "RECOVERY_INVALID": ("恢復碼不正確", 404),
    "UNAUTHORIZED": ("無權限操作此房間", 401),
    "NAME_REQUIRED": ("請填寫組名", 400),
    "NAME_TOO_LONG": ("組名最多 20 字元", 400),
    "GROUP_ONLINE": ("該組目前在線", 409),
    "JOIN_TIMEOUT": ("加入逾時，請重試", 400),
    "PHASE_LOCKED": ("目前不開放作答", 400),
    "SHEET_URL_INVALID": ("請貼上有效的 Google Sheet 連結", 400),
    "SHEETS_NOT_CONFIGURED": ("伺服器尚未設定 Google 機器人", 503),
    "SHEET_FORBIDDEN": ("無法讀取該試算表，請將它共用給機器人帳號", 403),
    "SHEET_NOT_FOUND": ("找不到該試算表", 404),
    "SHEET_TIMEOUT": ("讀取逾時，請稍後再試", 504),
    "SHEET_FORMAT_UNRECOGNIZED": ("無法辨識學習單格式", 422),
    "SHEET_NO_QUESTIONS": ("找不到填空格", 422),
    "SHEET_QUESTIONS_INVALID": ("題號有問題，請修正試算表", 422),
    "SHEET_TOO_MANY_QUESTIONS": ("題數超過上限（50）", 422),
    "SHEET_CHANGED": ("試算表內容已變動，請重新讀取並確認", 409),
    "BAD_REQUEST": ("請求格式錯誤", 400),
}


def err(code: str, details: dict | None = None) -> AppError:
    message, status = _ERRORS[code]
    return AppError(code, message, status, details)
