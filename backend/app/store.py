"""記憶體儲存：單一程序、單一 worker。

所有狀態變更都在沒有 await 的同步區段內完成（asyncio 單執行緒下即為原子），
因此不需要額外的鎖。
"""
import secrets

from .models import Room

# 排除易混淆字元 0 O 1 I L
_ALPHABET = "ABCDEFGHJKMNPQRSTUVWXYZ23456789"


class Store:
    def __init__(self) -> None:
        self.rooms: dict[str, Room] = {}
        self.recovery_index: dict[str, str] = {}  # 恢復碼 -> 房間代碼

    def get_room(self, code: str) -> Room | None:
        return self.rooms.get(code)

    def _random(self, n: int) -> str:
        return "".join(secrets.choice(_ALPHABET) for _ in range(n))

    def generate_room_code(self) -> str:
        while True:
            code = self._random(6)
            if code not in self.rooms:
                return code

    def generate_recovery_code(self) -> str:
        while True:
            code = self._random(10)
            if code not in self.recovery_index:
                return code

    def generate_token(self) -> str:
        return secrets.token_urlsafe(32)

    def remove_room(self, code: str) -> None:
        room = self.rooms.pop(code, None)
        if room:
            self.recovery_index.pop(room.recovery_code, None)


store = Store()
