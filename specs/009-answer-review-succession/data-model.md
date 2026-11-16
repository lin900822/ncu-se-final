# Data Model: 老師端人工審核與順位遞補

僅列相對 Step 1～8 的新增與修改。所有資料仍僅存記憶體；時間一律為後端產生的 UTC。
**`Submission` 不修改**：答案、送出時間、處理序、原始名次永不改寫。

## ReviewRecord（新增，僅追加）

老師對某組別在某搶答單位本輪送出所做的一次駁回或恢復。

| 欄位 | 型別 | 規則 |
|------|------|------|
| `round` | int | 必為審核當下的最新一輪（`room.round`） |
| `unit_id` | str | 搶答單位：題組 id（如 `B1`）或題目 id（如 `1`、`1-2`） |
| `group_name` | str | 組別顯示名稱 |
| `normalized_name` | str | 組名正規化（比對用，沿用 Step 1） |
| `action` | `"Invalid"` \| `"Valid"` | 駁回／恢復 |
| `reason` | str | 必填；`strip()` 後非空、**≤ 100 字元**；保存原文 |
| `by` | str | 操作者，固定 `"Teacher"`（沿用 `PhaseChange.by`） |
| `reviewed_at` | datetime | 後端 UTC，建立時產生 |

**不變式**：只追加、不修改、不刪除；題組以 `unit_id` 整組一次記錄（不為各成員題各記一筆）。

## Room（修改）

| 新增欄位 | 型別 | 說明 |
|----------|------|------|
| `reviews` | list[ReviewRecord] | 依時間先後追加；預設空 |

## 推導資料（不另存）

| 推導 | 規則 |
|------|------|
| **無效鍵** `(round, normalized_name, unit_id)` | 該鍵**最後一筆**審核紀錄的動作為 `Invalid`；沒有紀錄或最後一筆為 `Valid` 即有效 |
| **有效第一名**（每個搶答單位） | 本輪該單位的送出依**原始名次**由小到大，取第一個不在無效鍵的送出；全部無效則為「無有效答案」 |
| **遞補後名次** | 該單位內排除無效者後，依原始名次由 1 起連續編號；無效者無遞補後名次 |
| **有效結果**（`build_result`） | 每題：該題所屬單位的有效第一名組別，與該組在**這一題**的答案；無有效答案則 `winnerGroup`／`answer` 為 `null`；該單位有送出但全被駁回時，該題項目另附 `noValid: true`（沒有送出的題目不帶此欄位） |
| **領先題數**（`leadTally`） | 以題目為單位計算有效第一名（N 題題組計 N 題） |

**題組**：成員題的送出共用組別與原始名次，單位層級判斷即整組生效；同一題組內各題的有效狀態與遞補後名次永遠相同。

## 看板名次項目（`board.questions[].ranking[]` 修改，僅老師）

| 欄位 | 型別 | 說明 |
|------|------|------|
| `rank` | int | 原始名次（不變） |
| `group` | str | 組名 |
| `submittedAt` | str | 後端接收時間（不變） |
| `answer` | str | 該題答案（僅老師看板；新增） |
| `status` | `"Valid"` \| `"Invalid"` | 目前審核狀態（新增） |
| `successionRank` | int \| null | 遞補後名次；無效者為 `null`（新增） |
| `reason` | str \| null | 最近一次審核理由；未審核為 `null`（新增） |

每題的 `leader` 改為**有效第一名**組名（沒有有效答案為 `null`），`leadTally` 依有效第一名計算。`submittedCount` 與 `bundleId` 不變。

## 驗證規則與狀態轉換

單一目標 `(round, 組別, 單位)` 的狀態：

```text
有效 ──駁回(理由)──▶ 無效 ──恢復(理由)──▶ 有效
有效 ──恢復──▶ （重複：changed=false，不新增紀錄）
無效 ──駁回──▶ （重複：changed=false，不新增紀錄）
```

審核請求通過的條件（缺一即拒絕、不寫入）：老師憑證有效、房間 `Open`、`phase == "Ended"`、請求 `round == room.round`、
`action ∈ {invalid, valid}`、單位存在、該組在該單位本輪有送出、理由非空且 ≤ 100 字元。

## 新增錯誤碼

| code | HTTP | 訊息 | 觸發 |
|------|------|------|------|
| `REVIEW_NOT_ALLOWED` | 400 | 目前不開放審核，請於搶答結束後審核最新一輪 | 階段不是 Ended，或請求的輪次不是最新一輪 |
| `REASON_REQUIRED` | 400 | 請填寫理由 | 理由為空或只有空白 |
| `REASON_TOO_LONG` | 400 | 理由最多 100 字元 | 理由超過 100 字元 |
| `UNIT_NOT_FOUND` | 400 | 找不到該題或題組 | `unitId` 不是本房間的題目或題組 id |
| `REVIEW_TARGET_NOT_FOUND` | 400 | 找不到該組在此題的送出 | 該組本輪在該單位沒有送出紀錄 |

沿用：`UNAUTHORIZED`（401）、`ROOM_CLOSED`（409）、`BAD_REQUEST`（400）。

## 對 Step 8 匯出的影響

`ExportRow` 追加四欄：`審核狀態`、`遞補後名次`、`審核理由`、`審核時間`（規則見 [contracts/csv-format.md](./contracts/csv-format.md)）。
