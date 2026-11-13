# WebSocket Contract（相對 Step 1～6 的新增與修改）

## 學生 `/ws/student`

### `joined` 新增欄位
```json
{ "type": "joined", "...": "...",
  "bundles": [{ "id": "B1", "questionIds": ["3", "4"] }] }
```
- `bundles`：房間的題組設定（不含作答內容）；無題組時為 `[]`。
- `mySubmissions`、`submittedByOthers` 格式不變；題組成員會一起出現，前端以 `bundles` 對回卡片。

### 客戶端 → 伺服器：`submit_bundle`（新增）
```json
{ "type": "submit_bundle", "bundleId": "B1", "answers": { "3": "CPU", "4": "記憶體" } }
```
- `answers` 的 key 必須**恰好**是該題組的成員（不多不少）；不得帶時間。
- 單題 `submit` 不變，但 `questionId` 屬於題組時回 `QUESTION_IN_BUNDLE`。

### 伺服器 → 學生的事件（新增）

| 事件 | 受眾 | 內容 | 說明 |
|------|------|------|------|
| `bundle_submitted` | 同組所有視窗（含發送者） | `{ "type":"bundle_submitted", "bundleId":"B1", "answers":{"3":"CPU","4":"記憶體"}, "round":2 }` | 整張卡片一次切換為已送出；內容唯讀 |
| `bundle_submitted`（重複送出） | 僅發送者 | 同上（內容為**既有**答案） | 連點、同組另一視窗先到時，不新增紀錄也不通知他人 |
| `bundle_hint` | **其他組別**所有視窗 | `{ "type":"bundle_hint", "bundleId":"B1", "round":2 }` | 匿名提示「本題組已有組別送出」：不含組名、內容、組數、時間 |

### 錯誤（只回發送者，不關閉連線；附 `bundleId`）
```json
{ "type": "error", "code": "BUNDLE_INCOMPLETE", "message": "請填完題組內所有題目",
  "bundleId": "B1", "details": { "questionIds": ["4"] } }
```

| code | 觸發 | 訊息 |
|------|------|------|
| PHASE_LOCKED | 非搶答中或房間已結束 | 目前不開放作答（沿用） |
| BUNDLE_NOT_FOUND | `bundleId` 不存在 | 找不到該題組 |
| BUNDLE_INCOMPLETE | 有成員缺少、空白或只有空白字元，或帶了非成員題目 | 請填完題組內所有題目（`details.questionIds` 列出問題題目） |
| ANSWER_TOO_LONG | 任一成員答案 > 500 字元 | 答案最多 500 字元（`details.questionIds`） |
| QUESTION_IN_BUNDLE | 以單題 `submit` 送題組成員（附 `questionId`） | 此題屬於題組，請整組一起送出 |

任何錯誤都不寫入任何一題的紀錄。

## 老師 `/ws/teacher`

### `snapshot.room` 新增欄位
- `bundles`：同學生 `joined.bundles`。
- `submissions[]` 每筆多 `bundleId`（單題為 `null`）。
- `board.questions[]` 每題多 `bundleId`（單題為 `null`）；同題組各題的 `leader`、`ranking` 相同。

### 題組送出時老師收到
1. 每個成員一則 `submission`（沿用 Step 4/5 欄位，多 `bundleId`；同題組各則 `submittedAt`、`rank` 相同）；
2. 一則 `board`（沿用 Step 5）。

### `round_result`（Step 6）
格式不變；同題組各題 `winnerGroup` 相同，前端依 `bundles` 把各題框在一起、只顯示一次搶下組別。

## 保密檢查（原則 III）
- 他組只會收到 `bundle_hint`（`bundleId`、`round`）；不得收到 `bundle_submitted`、`submission`、`board`。
- `bundles` 設定可給所有學生（不含作答內容）。
