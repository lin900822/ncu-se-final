# WebSocket Contract（Step 11 新增與修改）

## 學生 `/ws/student`

### `joined`（新增 `fairness`，唯讀、公開）
```json
{ "type": "joined", "...": "...", "fairness": { "winCap": 2, "cooldownSeconds": 30 } }
```
- `fairness` 為 `null`（不限制）或 `{winCap, cooldownSeconds}`；**只含這兩個數字**，不含任何作答、名次、獲勝題數或分配資訊。
- 學生端在「等待搶答」階段顯示規則說明；其他階段不顯示。重新整理／重連取得相同規則。

### 結算前後的學生資訊（保密不變，原則 III）
- 搶答進行中：學生**不會**收到任何分配結果、名次、獲勝題數或「自己是否達上限」。
- 結算後：`round_result`／`joined.result` 格式**完全不變**——每題只有獲勝組名＋答案（讓位後的結果）；**不含** `outcome`、`Yielded*`、`Kept`、`changedUnits`、`fairness` 以外的任何公平規則細節。
- 學生訊息中**不得**出現：`outcome`、`YieldedCap`、`YieldedCooldown`、`Kept`、`Behind`、`changedUnits`、`winCounts`。

## 老師 `/ws/teacher`

### `snapshot.room`（新增 `fairness`）
同學生格式（`null` 或 `{winCap, cooldownSeconds}`）。老師以恢復碼換裝置後取得相同規則。

### `board`（Step 5／9 修改，僅老師）
```json
{
  "type": "board", "round": 1,
  "fairness": { "winCap": 2, "cooldownSeconds": 30 },
  "questions": [
    {
      "questionId": "3", "bundleId": null, "leader": "第 2 組", "submittedCount": 2,
      "ranking": [
        { "rank": 1, "group": "第 1 組", "submittedAt": "…", "answer": "…",
          "status": "Valid", "successionRank": 1, "reason": null, "outcome": "YieldedCap" },
        { "rank": 2, "group": "第 2 組", "submittedAt": "…", "answer": "…",
          "status": "Valid", "successionRank": 2, "reason": null, "outcome": "Won" }
      ]
    }
  ],
  "leadTally": [ { "group": "第 1 組", "leadCount": 2 }, { "group": "第 2 組", "leadCount": 1 } ]
}
```
- `board.fairness`：本房間的規則（`null` 表示不限制）。
- 每筆 `ranking[]` 新增 `outcome`：`Won`／`Kept`／`Behind`／`Invalid`／`YieldedCap`／`YieldedCooldown`（意義見 [data-model.md](../data-model.md)）；原有欄位（`rank`、`status`、`successionRank`、`reason` 等）**不變**。
- `leader` 與 `leadTally`（以題目計，題組 N 題計 N）為**讓位後**的獲勝者；前端以 `leadCount / winCap` 顯示「x/上限」。
- 搶答進行中也會隨每次送出即時更新（只送老師）。

### `review_updated`（Step 9 修改）
```json
{
  "type": "review_updated", "round": 1,
  "changedUnits": ["3", "5"],
  "board": { "...": "..." }, "reviews": [ "..." ], "result": { "...": "..." }
}
```
- 新增 `changedUnits`：此次審核導致**獲勝組別改變**的其他搶答單位的 id（排除被審核的那個單位本身；沒有連動為空陣列）。老師端據此提示「此次審核連動影響：Q3、Q5」。
- 學生收到的 `round_result`（`reviewed: true`）格式不變，只是內容為重新分配後的結果。

## 保密檢查（原則 III）
- 學生連線收到的所有訊息中，除 `joined.fairness`（規則本身）外，不得含任何公平機制的分配資訊。
- `outcome`、`changedUnits`、`board` 只經 `broadcast_to_teachers`；`round_result` 只經既有的 `broadcast_result`。
