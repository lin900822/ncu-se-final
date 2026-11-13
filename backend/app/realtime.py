"""即時廣播通道：連線登記與推送。

保密約束（原則 III）：
- 答案內容只能經 `broadcast_to_group`（同組視窗）與 `broadcast_to_teachers` 傳送。
- `broadcast_to_students`、`broadcast_to_other_groups` 嚴禁傳入答案、組名、草稿、組數或時間；
  只能傳房間層級訊息（階段、題目文字）或匿名提示 {type, questionId, round}。
- 組別清單與狀態只會送給老師連線。
- 名次、看板、領先組別與領先題數（Step 5）僅能經 `broadcast_to_teachers` 傳送。
- 結算後的結果公布（Step 6）只能經 `broadcast_result`（學生）與 `broadcast_to_teachers`（老師）。
- 投影通道（Step 12）只能傳「全班公開」的 `projector_state` 與 `countdown`：搶答中嚴禁傳入組名（名單除外）、
  答案、名次、時間、讓位／保留；投影連線唯讀、不計為組別。
"""
from fastapi import WebSocket


async def send_json_safe(ws: WebSocket, message: dict) -> None:
    try:
        await ws.send_json(message)
    except Exception:
        pass


async def close_safe(ws: WebSocket, code: int = 1000) -> None:
    try:
        await ws.close(code=code)
    except Exception:
        pass


class Realtime:
    def __init__(self) -> None:
        self.teachers: dict[str, set[WebSocket]] = {}
        # 同組可有多個視窗（Step 4）：(房間代碼, 正規化組名) -> 連線集合
        self.students: dict[tuple[str, str], set[WebSocket]] = {}
        # 投影視圖（Step 12）：唯讀連線，不計為組別、不計入 has_connections
        self.projectors: dict[str, set[WebSocket]] = {}

    # --- 老師連線 ---
    def add_teacher(self, code: str, ws: WebSocket) -> None:
        self.teachers.setdefault(code, set()).add(ws)

    def remove_teacher(self, code: str, ws: WebSocket) -> None:
        conns = self.teachers.get(code)
        if conns:
            conns.discard(ws)
            if not conns:
                self.teachers.pop(code, None)

    async def broadcast_to_teachers(self, code: str, message: dict) -> None:
        for ws in list(self.teachers.get(code, ())):
            await send_json_safe(ws, message)

    async def revoke_teachers(self, code: str) -> None:
        """換發新 token 後，使該房間既有老師連線失效。"""
        for ws in list(self.teachers.pop(code, ())):
            await send_json_safe(ws, {"type": "token_revoked"})
            await close_safe(ws, 4401)

    # --- 投影連線（唯讀） ---
    def add_projector(self, code: str, ws: WebSocket) -> None:
        self.projectors.setdefault(code, set()).add(ws)

    def remove_projector(self, code: str, ws: WebSocket) -> None:
        conns = self.projectors.get(code)
        if conns:
            conns.discard(ws)
            if not conns:
                self.projectors.pop(code, None)

    def has_projectors(self, code: str) -> bool:
        return bool(self.projectors.get(code))

    async def broadcast_to_projectors(self, code: str, message: dict) -> None:
        """投影視圖：僅限全班公開內容（projector_state／countdown），搶答中嚴禁組名（名單除外）與答案。"""
        for ws in list(self.projectors.get(code, ())):
            await send_json_safe(ws, message)

    # --- 學生連線 ---
    def add_student(self, code: str, normalized_name: str, ws: WebSocket) -> None:
        self.students.setdefault((code, normalized_name), set()).add(ws)

    def remove_student(self, code: str, normalized_name: str, ws: WebSocket) -> int:
        """移除一個視窗，回傳該組剩餘視窗數（為 0 時移除該鍵）。"""
        key = (code, normalized_name)
        conns = self.students.get(key)
        if not conns:
            return 0
        conns.discard(ws)
        if not conns:
            self.students.pop(key, None)
            return 0
        return len(conns)

    def window_count(self, code: str, normalized_name: str) -> int:
        return len(self.students.get((code, normalized_name), ()))

    async def broadcast_to_group(self, code: str, normalized_name: str, message: dict) -> None:
        """同組所有視窗（可含答案內容，因為是該組自己的資料）。"""
        for ws in list(self.students.get((code, normalized_name), ())):
            await send_json_safe(ws, message)

    async def broadcast_to_other_groups(self, code: str, exclude_name: str, message: dict) -> None:
        """同房間除指定組之外的所有視窗。僅限匿名提示，嚴禁含答案、組名、組數、時間。"""
        for (c, name), conns in list(self.students.items()):
            if c == code and name != exclude_name:
                for ws in list(conns):
                    await send_json_safe(ws, message)

    async def broadcast_result(self, code: str, message: dict) -> None:
        """結算後公布結果給房間所有學生視窗。

        僅限 `round_result`（結算首次公布與老師審核後的更新，每題僅有效第 1 名的組名＋答案）；
        嚴禁用於其他訊息（原則 III）。
        """
        for (c, _name), conns in list(self.students.items()):
            if c == code:
                for ws in list(conns):
                    await send_json_safe(ws, message)

    async def broadcast_to_students(self, code: str, message: dict) -> None:
        """僅限不含組別資料的房間層級訊息（如階段、題目文字）。

        嚴禁傳入任何組別名稱、草稿、答案或送出狀態（原則 III / FR-011）。
        """
        for (c, _name), conns in list(self.students.items()):
            if c == code:
                for ws in list(conns):
                    await send_json_safe(ws, message)

    # --- 房間層級 ---
    def has_connections(self, code: str) -> bool:
        if self.teachers.get(code):
            return True
        return any(k[0] == code for k in self.students)

    async def close_room_connections(self, code: str, reason: str) -> None:
        message = {"type": "room_closed", "reason": reason}
        targets = list(self.teachers.pop(code, ()))
        projectors = list(self.projectors.pop(code, ()))  # 投影連線：最終狀態已先送出，這裡只關閉
        for key in [k for k in self.students if k[0] == code]:
            targets.extend(self.students.pop(key))
        for ws in targets:
            await send_json_safe(ws, message)
            await close_safe(ws, 1000)
        for ws in projectors:
            await close_safe(ws, 1000)


realtime = Realtime()
