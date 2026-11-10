# WebSocket Contract（相對 Step 1 的新增與修改）

## 新事件：`phase_changed`（伺服器 → 老師與該房間所有學生）

```json
{ "type": "phase_changed", "phase": "Answering", "round": 2, "changedAt": "2026-11-10T09:30:00Z" }
```
`phase` ∈ `Answering` | `Ended`。**不得**包含任何組別名稱、草稿、答案或送出狀態（原則 III）。

## 老師 `/ws/teacher`
`snapshot` 的 `room` 增加階段欄位：

```json
{ "type": "snapshot",
  "room": { "code": "K7M2QX", "status": "Open", "phase": "Waiting", "round": 0 },
  "groups": [ ... ], "count": 1 }
```

## 學生 `/ws/student`
`joined` 回應增加階段欄位（新加入、重新加入、重連皆然）：

```json
{ "type": "joined", "room": { "code": "K7M2QX" }, "group": { "name": "第 1 組" },
  "rejoined": false, "phase": "Waiting", "round": 0 }
```

### 新訊息：`submit`（學生 → 伺服器）
```json
{ "type": "submit" }
```
- 非 `Answering`（含房間已結束）：回 `{ "type": "error", "code": "PHASE_LOCKED", "message": "目前不開放作答" }`，**不關閉連線**。
- `Answering`：本步驟為保留介面，不儲存、不回應；內容與仲裁由 Step 3 定義。

### 錯誤碼新增
| code | 觸發 | 訊息 |
|------|------|------|
| PHASE_LOCKED | 非搶答中送出 | 目前不開放作答 |

## 客戶端行為（非契約，供實作參考）
- 學生端以最近一次 `joined`/`phase_changed` 的 `phase` 決定輸入框是否可用；`round` 增加時清空輸入框。
- 連線中斷時視為鎖定，直到重新收到 `joined`。
