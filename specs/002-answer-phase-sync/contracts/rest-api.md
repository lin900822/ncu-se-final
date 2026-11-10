# REST Contract（新增）

沿用 Step 1 的錯誤格式 `{ "error": { "code", "message" } }`。

## `POST /api/rooms/{code}/phase/start`
Header：`Authorization: Bearer <teacherToken>`

| 狀況 | 回應 |
|------|------|
| 成功（`Waiting`/`Ended` → `Answering`） | `200` `{ "phase": "Answering", "round": N, "changed": true }`，並廣播 `phase_changed` |
| 已在 `Answering`（冪等） | `200` `{ "phase": "Answering", "round": N, "changed": false }`，不廣播 |
| 憑證缺失/錯誤 | `401 UNAUTHORIZED` |
| 房間不存在 | `404 ROOM_NOT_FOUND` |
| 房間已結束 | `409 ROOM_CLOSED` |

## `POST /api/rooms/{code}/phase/end`
Header 同上。

| 狀況 | 回應 |
|------|------|
| 成功（`Answering` → `Ended`） | `200` `{ "phase": "Ended", "round": N, "changed": true }`，並廣播 `phase_changed` |
| 非 `Answering`（冪等） | `200` `{ "phase": <目前階段>, "round": N, "changed": false }` |
| 其餘錯誤 | 同上 |

## 既有端點的變動
- `GET /api/rooms/{code}/status`、`POST /api/rooms`、`/recover`、`/close`：行為不變。
