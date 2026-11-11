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
class QuestionBundle:
    """題組：老師建立房間時綁定、須一起送出的相鄰題目（房間層級的送出單位設定）。

    題目本身仍為扁平清單、不因綁定而改變（原則 I）；建立後不可修改。
    """

    id: str  # B1、B2…（依第一個成員在題目清單中的位置編號）
    question_ids: list[str]  # 依題目順序，≥ 2 題


def bundle_public(b: QuestionBundle) -> dict:
    """題組設定不含任何作答內容，可給所有學生。"""
    return {"id": b.id, "questionIds": list(b.question_ids)}


@dataclass
class SheetSource:
    url: str
    spreadsheet_id: str
    sheet_id: int
    sheet_title: str
    read_at: datetime
    fingerprint: str


@dataclass
class Submission:
    """組別對某題的一次有效送出（僅追加）；時間由後端 UTC 產生，客戶端不得提供。

    題組送出時，每個成員題目各一筆，共用 seq／submitted_at／rank，並帶 bundle_id。
    """

    group_name: str
    normalized_name: str
    question_id: str
    round: int
    answer: str  # 非空白且 ≤ 500 字元，保存原文
    submitted_at: datetime  # 後端 UTC，僅供顯示，不參與排序判定
    seq: int  # 房間內單調遞增處理序（仲裁依據），建立後不可改寫
    rank: int  # 同一 (round, unitId) 的名次（1 起算），建立後不可改寫
    bundle_id: str | None = None  # 題組送出時為題組 id；單題送出為 None


@dataclass
class PhaseChange:
    """階段變更紀錄（僅追加）；時間為後端 UTC。"""

    phase: Literal["Answering", "Ended"]
    round: int
    changed_at: datetime
    by: str = "Teacher"


@dataclass
class ReviewRecord:
    """老師對某組別在某搶答單位本輪送出的一次駁回或恢復（僅追加、不修改、不刪除）。

    不改動 Submission 的答案／時間／原始名次；有效狀態由最後一筆紀錄推導（services/effective.py）。
    """

    round: int
    unit_id: str  # 題組 id（如 B1）或題目 id
    group_name: str
    normalized_name: str
    action: Literal["Invalid", "Valid"]  # 駁回 | 恢復
    reason: str  # 必填；strip 後非空、≤ 100 字元
    reviewed_at: datetime  # 後端 UTC
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
    submissions: list[Submission] = field(default_factory=list)
    # 去重索引：(round, normalized_name, question_id) -> Submission（由 submissions 推得）
    submission_index: dict[tuple[int, str, str], Submission] = field(default_factory=dict)
    questions: list[Question] = field(default_factory=list)
    # 順位仲裁（Step 5）：處理序計數與每個搶答單位每輪已排名數（皆由 submissions 推得）
    # rank_counts 鍵為 (round, unitId)；unitId＝題目所屬題組 id，未綁定為題目 id
    next_seq: int = 1
    rank_counts: dict[tuple[int, str], int] = field(default_factory=dict)
    # 題組（Step 7）：建立房間時確定、之後不可修改；bundle_of 為 questionId -> bundleId（由 bundles 推得）
    bundles: list[QuestionBundle] = field(default_factory=list)
    bundle_of: dict[str, str] = field(default_factory=dict)
    # 人工審核（Step 9）：僅追加的審核紀錄；有效結果由原始名次＋審核紀錄推導，不另存
    reviews: list[ReviewRecord] = field(default_factory=list)


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
    "GROUP_WINDOWS_FULL": ("該組視窗數已達上限（10）", 409),
    "QUESTION_NOT_FOUND": ("找不到該題", 400),
    "ANSWER_EMPTY": ("請填寫答案", 400),
    "ANSWER_TOO_LONG": ("答案最多 500 字元", 400),
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
    "REVIEW_NOT_ALLOWED": ("目前不開放審核，請於搶答結束後審核最新一輪", 400),
    "REASON_REQUIRED": ("請填寫理由", 400),
    "REASON_TOO_LONG": ("理由最多 100 字元", 400),
    "UNIT_NOT_FOUND": ("找不到該題或題組", 400),
    "REVIEW_TARGET_NOT_FOUND": ("找不到該組在此題的送出", 400),
    "NO_RECORDS": ("尚無送出紀錄可匯出", 404),
    "RECORDS_GONE": ("紀錄已不存在，請於活動結束後盡快匯出", 404),
    "BUNDLES_INVALID": ("題組設定有誤", 400),
    "BUNDLE_NOT_FOUND": ("找不到該題組", 400),
    "BUNDLE_INCOMPLETE": ("請填完題組內所有題目", 400),
    "QUESTION_IN_BUNDLE": ("此題屬於題組，請整組一起送出", 400),
    "BAD_REQUEST": ("請求格式錯誤", 400),
}


def err(code: str, details: dict | None = None) -> AppError:
    message, status = _ERRORS[code]
    return AppError(code, message, status, details)
