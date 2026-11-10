# Data Model: 搶答結果公布看板

僅存後端記憶體；**本步驟不新增任何儲存欄位**。對應 `diagrams/class.puml`。

## 推導資料（不另外儲存）

### 結果 RoundResult（僅 `room.phase == "Ended"` 時存在）
| 欄位 | 型別 | 說明 |
|------|------|------|
| `round` | int | 結算的輪次（＝`room.round`） |
| `results` | list<ResultItem> | 依 `room.questions` 順序，每題一筆 |

### ResultItem
| 欄位 | 型別 | 說明 |
|------|------|------|
| `questionId` | string | 題目識別碼（Step 3，含題組小題如 `1-2`） |
| `winnerGroup` | string \| null | 該題本輪 `rank == 1` 的組別顯示名稱；無人送出為 `null` |
| `answer` | string \| null | 該組送出的答案原文；無人送出為 `null` |

**規則**
- 資料來源僅為 `room.submissions` 中 `round == room.round` 且 `rank == 1` 的紀錄。
- 階段非 Ended 時不產生結果（`None`），因此公布前不可能外送。
- Ended 階段 `submit()` 拒絕新送出，該輪紀錄凍結，故結果確定且不可改寫。
- 不含其他組別的組名、名次、答案、時間、`rank`／`seq`、`board`、`leadTally`。

## 既有實體（沿用，不修改）

`Submission`（含 `rank`、`seq`）、`Room`（`phase`、`round`）、`Group`、`Question`：沿用 Step 1～5。

## 對外形狀（依受眾）

| 受眾 | 內容 | 不得包含 |
|------|------|----------|
| 全體學生（結算後） | `round_result`、`joined.result`：每題 `{questionId, winnerGroup, answer}` | 非第 1 名的組名／答案／名次、`rank`、`seq`、`board`、`leadTally`、送出時間 |
| 老師 | 同上（`round_result`、`snapshot.room.result`）；另沿用 Step 5 的 `board`、`submission` | — |
| 學生（結算前） | 無任何結果欄位（協定同 Step 4、5） | 一切結果與領先資訊 |
