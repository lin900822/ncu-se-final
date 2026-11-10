# REST API Contract

Base path: `/api`。回應皆為 JSON；錯誤格式 `{ "error": { "code": "<CODE>", "message": "<繁中訊息>" } }`。
老師端受保護操作以 `Authorization: Bearer <teacherToken>` 驗證。

## POST /api/rooms — 建立房間
- Request body: 無
- 201: `{ "code": "K7M2QX", "teacherToken": "...", "recoveryCode": "H8T3NW5RPD", "createdAt": "2026-11-10T09:00:00Z" }`

## POST /api/rooms/recover — 以恢復碼回復老師身分
- Request: `{ "recoveryCode": "H8T3NW5RPD" }`（忽略大小寫與空白）
- 200: `{ "code": "K7M2QX", "teacherToken": "<新 token>", "recoveryCode": "H8T3NW5RPD" }`，舊 token 立即失效
- 404 `RECOVERY_INVALID`：恢復碼不存在
- 409 `ROOM_CLOSED`：房間已結束

## POST /api/rooms/{code}/close — 結束房間
- Auth: Bearer teacherToken
- 200: `{ "status": "Closed", "closedReason": "Manual" }`
- 401 `UNAUTHORIZED`：token 無效
- 404 `ROOM_NOT_FOUND`
- 對已結束房間重複呼叫回 200（冪等）

## GET /api/rooms/{code}/status — 房間是否可加入（學生輸入代碼時預檢，選用）
- 200: `{ "open": true }`；不揭露任何組別資料（FR-009）
- 404 `ROOM_NOT_FOUND`

## 錯誤碼彙總
| code | HTTP | 訊息 |
|------|------|------|
| ROOM_NOT_FOUND | 404 | 找不到該房間 |
| ROOM_CLOSED | 409 | 該房間已結束 |
| RECOVERY_INVALID | 404 | 恢復碼不正確 |
| UNAUTHORIZED | 401 | 無權限操作此房間 |
