# WebSocket Contract（相對 Step 1～4 的新增與修改）

學生端 `/ws/student` **完全不變**：不新增事件、不新增欄位。`joined`、`submitted`、`question_submitted`
皆不含名次、看板或領先資訊（FR-012、FR-013）。

## 老師 `/ws/teacher`

### `submission` 事件新增欄位
```json
{ "type": "submission", "group": "第 1 組", "questionId": "1", "answer": "CPU",
  "round": 1, "submittedAt": "2026-11-10T09:30:05.123456Z", "rank": 1 }
```
`rank`：該組在 `(round, questionId)` 的名次（1 起算）。

### 新事件 `board`（伺服器 → 老師）
每筆新有效送出後、以及新一輪開始時推送；為本輪**完整**看板，客戶端直接覆蓋：
```json
{ "type": "board", "round": 1,
  "questions": [
    { "questionId": "1", "leader": "第 1 組", "submittedCount": 2,
      "ranking": [
        { "rank": 1, "group": "第 1 組", "submittedAt": "2026-11-10T09:30:05.123456Z" },
        { "rank": 2, "group": "第 2 組", "submittedAt": "2026-11-10T09:30:05.130012Z" } ] },
    { "questionId": "2", "leader": null, "submittedCount": 0, "ranking": [] } ],
  "leadTally": [ { "group": "第 1 組", "leadCount": 1 } ] }
```
- `questions` 依題目順序，包含尚無人送出的題目（`leader: null`，畫面顯示「尚無組別送出」）。
- 新一輪開始時推送 `submittedCount: 0` 的空白看板。

### `snapshot.room` 新增
- `board`：同上結構（本輪），重整、斷線重連、以恢復碼換裝置後立即還原。
- `submissions[]` 每筆新增 `rank`（所有輪次；舊輪紀錄保留其當時名次）。

## 保密（原則 III、FR-012）
- `rank`、`board`、領先組別與各組領先題數只會出現在老師連線的訊息中。
- 任何學生連線（含同組、他組）收到的訊息序列化後不得含 `rank`、`board`、`leadTally`、`leader`。

## 順位判定規則（供測試對照）
- 名次依後端處理序（`seq`）決定，與 `submittedAt` 是否相同、客戶端夾帶的任何時間無關。
- 同題同輪名次為 1..n 且不重複；拒絕或重複的送出不佔名次；已定名次不改寫。
