"""即時廣播通道：連線登記與推送。

刻意不提供任何「向學生連線廣播他組資料」的方法（FR-009）：
組別清單與狀態只會送給老師連線。
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
        self.students: dict[tuple[str, str], WebSocket] = {}

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

    # --- 學生連線 ---
    def set_student(self, code: str, normalized_name: str, ws: WebSocket) -> None:
        self.students[(code, normalized_name)] = ws

    def student_is(self, code: str, normalized_name: str, ws: WebSocket) -> bool:
        return self.students.get((code, normalized_name)) is ws

    def remove_student(self, code: str, normalized_name: str) -> None:
        self.students.pop((code, normalized_name), None)

    # --- 房間層級 ---
    def has_connections(self, code: str) -> bool:
        if self.teachers.get(code):
            return True
        return any(k[0] == code for k in self.students)

    async def close_room_connections(self, code: str, reason: str) -> None:
        message = {"type": "room_closed", "reason": reason}
        targets = list(self.teachers.pop(code, ()))
        for key in [k for k in self.students if k[0] == code]:
            targets.append(self.students.pop(key))
        for ws in targets:
            await send_json_safe(ws, message)
            await close_safe(ws, 1000)


realtime = Realtime()
