# WebSocket Contract（相對 Step 1～5 的新增與修改）

## 新事件 `round_result`（伺服器 → 全體學生連線 ＋ 老師）
老師結束搶答（階段實際由 Answering 變為 Ended）後，緊接在 `phase_changed(Ended)` 之後送出，**每輪僅一次**；
重複結束搶答不再送。

```json
{ "type": "round_result", "round": 1,
  "results": [
    { "questionId": "1", "winnerGroup": "第 1 組", "answer": "CPU" },
    { "questionId": "2", "winnerGroup": "第 3 組", "answer": "RAM" },
    { "questionId": "3", "winnerGroup": null, "answer": null } ] }
```
- `results` 依題目順序，**包含所有題目**；無人送出者 `winnerGroup`、`answer` 為 `null`（畫面顯示「本題無人搶答」）。
- 每題只含第 1 名的組別與答案，不含其他組別的任何資訊。

## 學生 `joined` 新增欄位
```json
{ "type": "joined", "...": "...", "result": { "round": 1, "results": [ ... ] } }
```
- 房間開放且階段為 `Ended`（結果已公布）時為上述結構；其餘階段（Waiting、Answering）為 `null`。
- 適用新加入、重新加入、斷線重連、結束後才加入的所有視窗（含同組多視窗）。

## 老師 `snapshot.room` 新增欄位
- `result`：同上結構；階段非 Ended 時為 `null`。重整、重連、換裝置回復後立即還原。

## 客戶端行為（供測試對照）
- 學生端：階段為 Ended 且有 `result` → 顯示結果頁；收到 `phase_changed(Answering)`（新一輪）→ 清除結果並回到作答畫面。
- 「本組搶下」由客戶端以 `winnerGroup === 自己的組名` 判斷。

## 保密（原則 III、FR-004、FR-007）
- 公布前（Waiting、Answering）任何學生連線不得收到 `round_result` 或非 `null` 的 `joined.result`。
- 公布後學生收到的結果只含各題第 1 名的組名與答案；仍不得收到 `rank`、`seq`、`board`、`leadTally`、他組答案或送出時間。
- Step 4、5 的其他學生事件（`submitted`、`question_submitted`）格式不變。
