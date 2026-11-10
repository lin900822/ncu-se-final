# Data Model: 搶答順位仲裁與即時進度板

僅存後端記憶體；時間皆為後端產生的 UTC。對應 `diagrams/class.puml`。

## Submission（Step 4，擴充兩欄；仍僅追加）

| 新增欄位 | 型別 | 說明 |
|----------|------|------|
| `seq` | int | 房間內單調遞增的處理序（1,2,3…），於接受當下取得；全序、唯一，為仲裁依據 |
| `rank` | int | 同一 `(round, questionId)` 的名次（1,2,3…）；＝接受當下該題該輪已有有效送出數＋1 |

**規則**
- `seq`、`rank` 與 Step 4 的欄位在同一同步區段內寫入，之後不可改寫。
- 被拒絕或重複的送出不建立紀錄，因此不取得 `seq`／`rank`。
- 同一 `(round, questionId)` 內，`rank` 必為 1..n 且不重複；依 `rank` 排序等同依 `seq` 排序。
- `submittedAt` 仍由後端產生，僅供顯示與核對，**不參與**排序判定。

## Room（擴充）

| 新增欄位 | 型別 | 說明 |
|----------|------|------|
| `next_seq` | int | 下一個處理序，初始 1 |
| `rank_counts` | dict[(round, questionId)] → int | 每題每輪已排名數；由 `submissions` 推得，用於 O(1) 取得下一個名次 |

## 推導資料（不另外儲存）

### 題目進度 QuestionProgress（僅本輪）
| 欄位 | 說明 |
|------|------|
| `questionId` | 題目識別碼 |
| `leader` | 第 1 名的組名；無人送出為 `null` |
| `submittedCount` | 本輪已送出組數 |
| `ranking` | 依名次排列的 `[{rank, group, submittedAt}]` |

### 組別領先統計 GroupLeadTally（僅本輪）
`[{group, leadCount}]`：該組為第 1 名的題數；依題數降序、同數依組名。

### 看板 Board
`{ round, questions: [QuestionProgress（依題目順序，含尚無送出者）], leadTally: [...] }`

## 對外形狀（依受眾）

| 受眾 | 可得內容 | 不得包含 |
|------|----------|----------|
| 老師 | `submission`（含 `rank`、`seq`）、`board`、snapshot（`submissions` 帶 `rank`，另含 `board`） | — |
| 同組視窗 / 他組 | Step 4 事件，**不變** | `rank`、`seq`、`board`、領先組別、他組組名 |
