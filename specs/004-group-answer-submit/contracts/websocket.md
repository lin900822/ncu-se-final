# WebSocket Contract（相對 Step 1～3 的新增與修改）

## 學生 `/ws/student`

### 加入規則變更（取代 Step 1 的 `GROUP_ONLINE`）
同組已有視窗在線時，以相同代碼與組名加入的新視窗**不再被拒絕**，視為該組的另一個視窗。
每組最多 10 個視窗，超過回：

```json
{ "type": "error", "code": "GROUP_WINDOWS_FULL", "message": "該組視窗數已達上限（10）" }
```
（回應後關閉連線 `1008`，同 Step 1 的加入錯誤。）`GROUP_ONLINE` 錯誤碼移除。

### `joined` 新增欄位（新加入、重新加入、重連皆然）
```json
{ "type": "joined", "...": "...",
  "mySubmissions": { "1": "CPU", "3-1": "…" },
  "submittedByOthers": ["2", "5"] }
```
- `mySubmissions`：該組**本輪**已送出的 `{questionId: answer}`（只含自己組）。
- `submittedByOthers`：本輪有**其他組**送出的題目識別碼清單（匿名，不含組名、內容、組數、時間）。

### 客戶端 → 伺服器：`submit`
```json
{ "type": "submit", "questionId": "1", "answer": "CPU" }
```
不得帶時間；時間由伺服器產生。

### 伺服器 → 學生的事件

| 事件 | 受眾 | 內容 | 說明 |
|------|------|------|------|
| `submitted` | 同組所有視窗（含發送者） | `{ "type":"submitted", "questionId":"1", "answer":"CPU", "round":2 }` | 該組此題已送出；內容唯讀 |
| `submitted`（重複送出） | 僅發送者 | 同上（內容為**既有**答案） | 連點、同組另一視窗先到時，不新增紀錄也不通知他人 |
| `question_submitted` | **其他組別**所有視窗 | `{ "type":"question_submitted", "questionId":"1", "round":2 }` | 匿名提示：不含組名、內容、組數、時間 |

### 錯誤（只回發送者，不關閉連線；附 `questionId`）
| code | 觸發 | 訊息 |
|------|------|------|
| PHASE_LOCKED | 非搶答中、或房間已結束 | 目前不開放作答（沿用 Step 2） |
| QUESTION_NOT_FOUND | 題目識別碼不存在 | 找不到該題 |
| ANSWER_EMPTY | 答案為空或僅空白 | 請填寫答案 |
| ANSWER_TOO_LONG | 超過 500 字元 | 答案最多 500 字元 |

## 老師 `/ws/teacher`

`snapshot.room` 新增 `submissions`（所有輪次，依接受順序）：
```json
{ "submissions": [
  { "group": "第 1 組", "questionId": "1", "answer": "CPU", "round": 1, "submittedAt": "2026-11-10T09:30:05Z" } ] }
```

新事件 `submission`（伺服器 → 老師，每筆新紀錄一則）：
```json
{ "type": "submission", "group": "第 1 組", "questionId": "1", "answer": "CPU", "round": 1, "submittedAt": "2026-11-10T09:30:05Z" }
```

## 組別在線通知（語意調整）
`group_status`／`group_joined` 只在組別「由離線變在線」「新組別加入」「最後一個視窗離開」時送給老師；
同組多出的視窗加入或離開不重複通知。

## 保密（原則 III、FR-008）
- 任何學生連線收到的事件，**不得**包含其他組別的答案、草稿、組名、組數或送出時間。
- 答案內容只會出現在：同組視窗的 `submitted`／`joined.mySubmissions`、老師的 `submission`／`snapshot`。
- 草稿不經由任何訊息傳送。
