# WebSocket Contract（Step 9 新增與修改）

## 學生 `/ws/student`

**不新增學生訊息型別**，學生也**不能**送出任何審核相關訊息（`review`、`reviews` 等一律被忽略）。

### `round_result`（Step 6 修改：新增 `reviewed` 旗標）
老師審核成功（`changed: true`）後，送給房間**所有學生視窗**（含被駁回組、遞補組、他組、同組多視窗）：

```json
{
  "type": "round_result",
  "round": 1,
  "reviewed": true,
  "results": [
    { "questionId": "1", "winnerGroup": "第 2 組", "answer": "CPU" },
    { "questionId": "2", "winnerGroup": null, "answer": null }
  ]
}
```
- 內容與 Step 6 相同：每題**只有有效第一名**的組名＋答案；沒有有效答案（含全部被駁回）為 `null`。
- 若該題有組別送出但**全部被駁回**，該題項目額外附 `"noValid": true`（學生端據此顯示「本題（題組）無有效答案」，以區別「無人搶答」）；其餘情況**不帶**此欄位。此旗標只表示「曾有送出」，學生本來就會收到匿名的「已有組別送出」提示，不洩漏組名、答案或理由。
- `reviewed: true` 只出現在審核觸發的更新；結束搶答時的首次公布**沒有**此欄位（或為 `false`）。
- 學生端收到 `reviewed: true` 時顯示「老師已更新結果」，並以新結果取代畫面上的舊結果。
- **不含**：被駁回組別的組名／答案、駁回理由、審核紀錄、遞補後名次、原始名次、看板。
- 只經 `realtime.broadcast_result` 發送（靜態審核：呼叫端僅 `phase.py` 與 `review.py`）。

### `joined`（不變）
`joined.result` 在 `Ended` 階段由 `build_result` 推導，因此重連、重新整理、晚加入的學生自動得到**審核後**的最新結果；**沒有** `reviewed` 旗標，也不含任何審核資訊。

## 老師 `/ws/teacher`

### `review_updated`（新增）
審核成功（`changed: true`）後送給老師所有視窗：

```json
{
  "type": "review_updated",
  "round": 1,
  "board": { "type": "board", "round": 1, "questions": [ "..." ], "leadTally": [ "..." ] },
  "reviews": [
    {
      "round": 1,
      "unitId": "1",
      "group": "第 1 組",
      "action": "invalid",
      "reason": "答案錯誤",
      "by": "Teacher",
      "reviewedAt": "2026-11-11T03:30:00Z"
    }
  ],
  "result": { "round": 1, "results": [ "..." ] }
}
```
- `board`：完整看板（格式見 data-model「看板名次項目」：每筆含 `status`、`successionRank`、`reason`、`answer`；`leader`／`leadTally` 為有效第一名）。
- `reviews`：本房間**所有**審核紀錄（含舊輪），依時間先後；老師端以整份覆蓋。
- `result`：與學生收到的 `round_result` 內容相同的有效結果（不含 `type`／`reviewed`）。
- 老師**不**另收 `round_result`。

### `snapshot.room`（修改）
- 新增 `reviews`：同上，所有審核紀錄。
- `board`、`result` 已是審核後的推導結果。
- 老師以恢復碼換裝置回復後，因此看到完整的審核狀態與紀錄（FR-015、FR-020）。

### `board`（Step 5 修改）
每次有新送出時老師收到的 `board` 也是新格式（`ranking[]` 多 `answer`、`status`、`successionRank`、`reason`）；沒有審核時 `status` 皆為 `"Valid"`、`successionRank` 等於 `rank`、`reason` 為 `null`。

## 保密檢查（原則 III）
- 學生連線收到的所有訊息中，**不得**出現：`review_updated`、`reviews`、`status`、`successionRank`、`reason`、`board`、`rank`、被駁回組別的組名與答案。
- `review_updated` 只經 `broadcast_to_teachers`；`round_result` 只經 `broadcast_result`。
