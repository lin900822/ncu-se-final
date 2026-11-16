# Data Model: 搶答歷史紀錄 CSV 匯出

本功能**不新增任何儲存資料**：匯出列由既有 `Submission`（Step 4/5/7）與 `Question`、`QuestionBundle` 推導，產生後即丟棄。
所有資料仍僅存記憶體；時間一律為後端產生的 UTC。

## ExportRow（推導，不另存、不建立資料類別）

CSV 的一列，對應一筆有效送出（題組成員各一列）。

| 欄位（CSV 標題） | 來源 | 格式與規則 |
|------------------|------|-----------|
| 輪次 | `Submission.round` | 整數，1 起算 |
| 題號 | `Question.label`（以 `question_id` 對應） | 如 `Q1`、`Q3`、`Q1（2）`，與老師端相同 |
| 題組 | `Room.bundles`（以 `Submission.bundle_id` 對應） | 題組成員題號以「、」相連，如 `Q3、Q4`；未綁定為空字串 |
| 組別 | `Submission.group_name` | 組名原文；套用 `safe_cell()` |
| 答案 | `Submission.answer` | 答案原文（≤ 500 字元，不截斷）；套用 `safe_cell()` |
| 接收時間 | `Submission.submitted_at` | `models.iso()`：`YYYY-MM-DDTHH:MM:SSZ`（UTC，精確到秒） |
| 排名 | `Submission.rank` | 整數，1 起算；題組成員共用同一排名 |

**不輸出**：`seq`、`normalized_name`、`bundle_id`（內部識別）、`Question.cell`、`teacher_token`、恢復碼等任何內部或機密資訊（FR-014）。

## 排序（FR-012）

`(round, 題目在 room.questions 中的順序, rank)` 由小到大；排序為穩定排序，題組成員因共用排名而相鄰排列。

## 一致性不變式

- 列數＝`len(room.submissions)`（所有輪次的有效送出，題組成員各算一筆）；不多、不少、不重複。
- 每列的 `(輪次, 題號, 組別)` 唯一（沿用 Step 4 的「同組同題同輪最多一筆」）。
- 同一輪同一題的排名為 1…n 唯一、連續（沿用 Step 5）；題組成員各題的排名與同組別、同時間相同（沿用 Step 7）。
- 匯出前後 `room.submissions`、`next_seq`、`rank_counts`、`last_activity_at` 皆不變（唯讀）。
- 匯出在單一同步區段內完成（無 await），因此是一致快照：題組不會只匯出一部分。

## safe_cell(text) 規則（FR-017）

```text
若 text 非空且 text[0] 屬於 { '=', '+', '-', '@', '\t', '\r', '\n' }  →  回傳 "'" + text
否則 → 回傳 text
```
- 只套用在使用者提供的文字欄位：**組別**與**答案**。
- 補上前綴後的內容去掉第一個字元 `'` 即為原文（可還原）。
- 空字串不處理；以空白開頭但後接 `=` 者不屬於危險開頭，不處理。

## 檔案層級規則

| 項目 | 規則 |
|------|------|
| 編碼 | UTF-8，**含 BOM**（`﻿` 置於檔案最前） |
| 換行 | CRLF（`\r\n`）；欄位內的換行原樣保留於引號內 |
| 引號 | 含逗號、雙引號、換行（CR/LF）的欄位以雙引號包住；內含雙引號加倍 |
| 標題列 | 第一列固定為 `輪次,題號,題組,組別,答案,接收時間,排名` |
| 空資料 | 沒有任何有效送出時**不產生檔案**，回 `NO_RECORDS` |

## 新增錯誤碼

| code | HTTP | 訊息 | 觸發 |
|------|------|------|------|
| `NO_RECORDS` | 404 | 尚無送出紀錄可匯出 | 房間存在、憑證正確，但沒有任何有效送出 |
| `RECORDS_GONE` | 404 | 紀錄已不存在，請於活動結束後盡快匯出 | 房間已超過保留期被清除（此端點內由 `ROOM_NOT_FOUND` 轉換） |

`UNAUTHORIZED`（401）沿用 Step 1。
