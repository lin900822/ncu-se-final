# Data Model: Google Sheet 連結與題目表單生成

僅存後端記憶體（草稿除外，草稿在學生瀏覽器）。對應 `diagrams/class.puml`。

## Question（扁平清單，依題號再依小題編號排序）

| 欄位 | 型別 | 說明 |
|------|------|------|
| `id` | string | 識別碼：單題 `"3"`；題組小題 `"1-2"`。房間內唯一 |
| `number` | int | 題號，≥ 1；整份學習單須 1..N 連續且不重複 |
| `sub` | int \| null | 小題編號（題組）；單題為 null；同題號下須 1..k 連續 |
| `label` | string | 顯示標籤：`Q3`、`Q1（2）` |
| `text` | string | 「題目」欄文字（去除前後空白，上限 2000 字元）；**僅伺服器保存，搶答開始後才送給學生**；老師端可見 |
| `cell` | string | 作答格位置（A1 表示法含分頁名，如 `'學習單'!H6`）；**僅伺服器保存，不外送**；供回填使用 |

**驗證 / 規則**
- 題數 ≤ 50（FR-009）；題號從 1 起連續且每個恰出現一次；小題編號從 1 起連續；題號數與作答格數一致（FR-010）。
- 無「題型」欄位；單題／題組由同一題號下的作答格數量自然得知。
- 建立後不可變（不隨試算表更動）。

## SheetSource

| 欄位 | 型別 | 說明 |
|------|------|------|
| `url` | string | 老師貼上的連結 |
| `spreadsheetId` | string | 由連結解析 |
| `sheetId` | int | 讀取的分頁（連結 gid 或第一個分頁） |
| `sheetTitle` | string | 分頁名稱（如「學習單」） |
| `readAt` | datetime(UTC) | 讀取時間（後端產生） |
| `fingerprint` | string | 題目識別碼＋儲存格位置的 SHA-256；用於預覽與建立的一致性檢查 |

## Room（擴充）

| 新增欄位 | 型別 | 說明 |
|----------|------|------|
| `sheet` | SheetSource \| null | 不貼連結建房時為 null |
| `questions` | list<Question> | 不貼連結時為空清單 |

## 學生端草稿（瀏覽器，非後端資料）

`localStorage["draft:<房間代碼>"] = { "round": int, "values": { "<Question.id>": "文字(≤500字元)" } }`
- `round` 增加時清空；房間結束／離開房間時刪除；儲存不可用時只影響還原，不影響輸入。

## 設定（非資料模型）

| 設定 | 來源 | 說明 |
|------|------|------|
| `GOOGLE_SERVICE_ACCOUNT_FILE` | `backend/.env` | 服務帳號 JSON 金鑰檔路徑；未設定時試算表功能回 503 |

## 對外送出的題目形狀

- 題號清單：`{ "id": "1-2", "number": 1, "sub": 2, "label": "Q1（2）" }`（不含 `cell`、不含 `text`；預覽與學生加入時皆然）。
- 題目文字：另以 `texts: { "<id>": "文字" }` 傳送，**學生僅在房間為搶答中時才收到**（`question_texts` 事件，或搶答中加入／重連時 `joined.texts`）；老師的 `snapshot` 一律含 `texts`。
