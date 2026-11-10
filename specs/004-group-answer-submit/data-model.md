# Data Model: 組別答案提交與防重複送出

僅存後端記憶體；時間皆為後端產生的 UTC。對應 `diagrams/class.puml`。

## Submission（僅追加）

| 欄位 | 型別 | 說明 |
|------|------|------|
| `groupName` | string | 組名（顯示用）；識別以 `normalizedName` |
| `normalizedName` | string | 組別識別鍵（Step 1 的 `Group.normalized_name`） |
| `questionId` | string | 題目識別碼（Step 3 的 `Question.id`，如 `"3"`、`"1-2"`） |
| `round` | int | 送出當時的輪次（`Room.round`） |
| `answer` | string | 答案原文，**非空白且 ≤ 500 字元**（以原字串長度計） |
| `submittedAt` | datetime(UTC) | 後端於接受當下產生；客戶端不得提供 |

**規則**
- 同一 `(round, normalizedName, questionId)` 最多一筆（去重鍵）；之後的送出視為重複，不新增、不修改。
- 紀錄僅追加，新一輪不刪除舊紀錄，也不覆寫。
- 僅在房間 `Open` 且 `phase == "Answering"` 時才可新增。

## Room（擴充）

| 新增欄位 | 型別 | 說明 |
|----------|------|------|
| `submissions` | list<Submission> | 全部送出紀錄（依接受順序） |
| `submission_index` | dict[(round, normalizedName, questionId)] → Submission | 去重與快速查詢；由 `submissions` 推得，不作為額外事實 |

## Group（語意調整）

| 欄位 | 變更 |
|------|------|
| `online` | 語意改為「至少一個視窗在線」；所有視窗離線才為 `false` |
| 視窗集合 | 不存在 `Group` 上，存在執行期連線登記（見下）；每組 ≤ **10** 個視窗 |

## 執行期連線登記（非持久資料）

- `students: dict[(roomCode, normalizedName)] -> set[WebSocket]`（Step 1 為單一 `WebSocket`）。
- 第 11 個視窗加入時拒絕（`GROUP_WINDOWS_FULL`）；最後一個視窗離開才把 `Group.online` 設為 `false`。

## 派生狀態（不另外儲存）

| 狀態 | 來源 |
|------|------|
| 某組某題「已送出」 | `submission_index` 中有 `(room.round, 該組, 題目)` |
| 他組送出提示 | `submission_index` 中有 `(room.round, 其他任一組, 題目)`；只輸出 `questionId` |

## 對外送出的形狀（依受眾）

| 受眾 | 內容 | 不得包含 |
|------|------|----------|
| 同組視窗 | `{questionId, answer, round}` | — |
| 老師 | `{group, questionId, answer, round, submittedAt}` | — |
| 其他組別 | `{questionId, round}` | 答案、組名、組數、時間、草稿 |
