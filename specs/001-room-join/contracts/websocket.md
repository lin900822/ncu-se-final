# WebSocket Contract

訊息皆為 JSON，含 `type` 欄位。伺服器啟用協定層 ping（10 秒間隔/10 秒逾時）以偵測異常斷線。

## 老師：`/ws/teacher?code=<房間代碼>&token=<teacherToken>`

驗證失敗：以關閉碼 `4401` 關閉。房間已結束：先送 `room_closed` 再關閉。

連線成功後伺服器立即送出完整快照（斷線重連後亦同）：

```json
{ "type": "snapshot",
  "room": { "code": "K7M2QX", "status": "Open" },
  "groups": [ { "name": "第 1 組", "online": true, "joinedAt": "2026-11-10T09:01:00Z" } ],
  "count": 1 }
```

後續增量事件（伺服器 → 老師）：
- `group_joined`：`{ "type": "group_joined", "group": { ... }, "count": N }`
- `group_status`：`{ "type": "group_status", "name": "第 1 組", "online": false }`
- `room_closed`：`{ "type": "room_closed", "reason": "Manual" | "IdleTimeout" }`
- 若老師以恢復碼換發新 token，舊連線收到 `{ "type": "token_revoked" }` 並被關閉（`4401`）。

客戶端 → 伺服器：無必要訊息（可選 `{ "type": "ping" }`，僅更新活動時間）。

## 學生：`/ws/student`

連線後 5 秒內須送出：

```json
{ "type": "join", "code": "k7m2qx ", "name": "第１組" }
```

成功回應：
```json
{ "type": "joined", "room": { "code": "K7M2QX" }, "group": { "name": "第 1 組" }, "rejoined": false }
```

失敗回應（回應後伺服器關閉連線，關閉碼 `1008`）：
```json
{ "type": "error", "code": "GROUP_ONLINE", "message": "該組目前在線" }
```

| code | 觸發情況 | 訊息 |
|------|---------|------|
| ROOM_NOT_FOUND | 代碼不存在 | 找不到該房間 |
| ROOM_CLOSED | 房間已結束 | 該房間已結束 |
| NAME_REQUIRED | 組名空白 | 請填寫組名 |
| NAME_TOO_LONG | 超過 20 字元 | 組名最多 20 字元 |
| ~~GROUP_ONLINE~~ | 同組名目前在線 | （**Step 4 起移除**：改為允許同組多視窗，見 `specs/004-group-answer-submit/contracts/websocket.md`） |
| JOIN_TIMEOUT | 5 秒內未送 join | 加入逾時，請重試 |

加入後學生連線可能收到：
- `room_closed`：`{ "type": "room_closed", "reason": "..." }` 後關閉。

**保密（FR-009）**：學生連線永遠收不到其他組別的名稱或狀態，也不會收到 `snapshot`／`group_*` 事件。
