# Research: Google Sheet 連結與題目表單生成

規格無 NEEDS CLARIFICATION。範例檔（`軟工期末專案_單題_範例 的副本.xlsx`、`軟工期末專案_題組_範例 的副本.xlsx`，皆為單一分頁「學習單」）的實際結構如下，解析規則據此設計。

## 範例檔實測結構

| 項目 | 單題範例 | 題組範例 |
|------|----------|----------|
| 標題 | `B2:H2` 合併（「計算機概論基礎 學習單」） | 同左 |
| 表頭列（第 4 列） | B4「題號」、C4:F4「題目」（合併）、G4:H4「作答」（合併） | 同左 |
| 題號欄（B） | 數字 1～6，每題佔一列，題與題之間夾一個合併的空白間隔列（如 `B6:H6`） | 數字 1～4；題號 1、2 各以 `B5:B6`、`B8:B9` 垂直合併，跨兩個小題列 |
| 題目欄（C:F 合併） | 每題一列題目文字 | 每個小題列各有題目文字 |
| 作答欄（G:H） | 每題 `G:H` 合併的**空白格**（如 `G5:H5`），為作答位置 | 小題列：G 有標籤「（1）」「（2）」、H 為空白作答格；無小題的題號：`G:H` 合併空白格 |
| 題數 | 6 題 | 4 個題號、6 個作答格 |

結論：題號是**純數字**（顯示為 Q1…），不是「Q1」文字；題組以「題號垂直合併＋作答欄（n）標籤」表示。

## D1：服務帳號認證，路徑放 `.env`
- **Decision**: `backend/.env` 設 `GOOGLE_SERVICE_ACCOUNT_FILE=<JSON 金鑰檔路徑>`；啟動時以 `python-dotenv` 載入；以 `google.oauth2.service_account.Credentials.from_service_account_file` 載入並取得 access token。`.env` 與金鑰檔列入 `.gitignore`，提供 `.env.example`。
- **Rationale**: 使用者已建立機器人並下載 JSON；服務帳號不需 API key、不需老師登入。未設定時伺服器仍可啟動，僅「讀取試算表」回 503，不貼連結的建房不受影響。
- **Alternatives**: 把 JSON 內容直接放環境變數——長且易外洩於 process 列表；OAuth 使用者授權——要老師登入，過度複雜。

## D2：Scope
- **Decision**: 本步驟使用 `https://www.googleapis.com/auth/spreadsheets.readonly`；回填步驟再改 `https://www.googleapis.com/auth/spreadsheets`。
- **Rationale**: 最小權限，且規格 FR-012 要求本步驟不修改試算表。即使機器人在試算表上是編輯者，只讀 scope 的 token 也無法寫入。
- **Alternatives**: 現在就開讀寫——權限超出需要。

## D3：呼叫方式
- **Decision**: `google-auth` 取 token（同步，放進執行緒池）＋ `httpx.AsyncClient` 呼叫 `GET https://sheets.googleapis.com/v4/spreadsheets/{id}?includeGridData=true&fields=sheets(properties(sheetId,title),merges,data(startRow,startColumn,rowData(values(formattedValue))))`，逾時 10 秒。
- **Rationale**: 一次請求同時取得格值與合併範圍（合併是辨識題組的關鍵）；`httpx.MockTransport` 讓錯誤對應可離線測試；依賴少。
- **Alternatives**: `google-api-python-client`（龐大、同步）；`gspread`（取不到完整合併資訊且多一層抽象）。

## D4：連結解析
- **Decision**: 只接受 `https://docs.google.com/spreadsheets/d/<id>/...`；`<id>` 為 `[A-Za-z0-9_-]+`；`gid` 取自 `#gid=` 或 `?gid=`，無則取第一個分頁。
- **Rationale**: 後端只會對固定的 Google 網域送出請求，不使用使用者提供的主機名稱，無 SSRF 風險。

## D5：解析演算法（純函式，輸入為格線＋合併範圍）
1. 找表頭列：同一列含「題號」「題目」「作答」三個儲存格（去空白）；取其欄位（含合併範圍的欄寬，作答區為 G:H）。找不到 → `SHEET_FORMAT_UNRECOGNIZED`。
2. 表頭下方逐列掃描：題號欄（取合併範圍左上角的值）為數字（容許全形數字、前後空白、`Q3` 寫法）者開啟一個題號；該題號的列範圍＝其垂直合併範圍，無合併則為單列；空白或非數字列忽略。
3. 題號列範圍內，題目欄有文字的每一列是一個作答格：
   - 作答欄最左格為標籤 `（n）` / `(n)` → 作答格位置為其右一格，小題編號為 n；
   - 否則 → 作答格位置為作答欄最左格（合併範圍左上角）。
   - 該題號只有一個作答格且無標籤 → 單題，識別碼 `n`；有多個作答格 → 每個須有 `（1）…（k）` 連續標籤，識別碼 `n-i`；不合 → 回報錯誤。
4. 驗證（FR-010）：題號 1..N 連續且不重複；小題編號連續；作答格數＝題目列數；題數 ≤ 50。違規一次列出所有有問題的題號。
5. 輸出扁平題目清單，依題號再依小題編號排序；每題含識別碼、題號、小題編號、顯示標籤（`Q3`／`Q1（2）`）、儲存格位置（A1 表示法，含分頁名稱，僅伺服器保存）。
- **Rationale**: 範例檔的兩種結構都能涵蓋；不依賴固定欄位字母（以表頭定位）；扁平清單符合 Constitution I。

## D6：預覽與建立的一致性
- **Decision**: 預覽回傳題目與 `fingerprint`（題目識別碼與儲存格位置的 SHA-256）。建立房間時帶 `sheetUrl`＋`fingerprint`，後端重新讀取並比對；不符 → 409 `SHEET_CHANGED`，要求老師重新預覽。
- **Rationale**: 保證「老師確認的」就是「房間採用的」，且不需在伺服器暫存預覽結果。
- **Alternatives**: 伺服器快取預覽——需過期管理；直接信任前端送來的題目——客戶端可竄改儲存格位置。

## D7：資料外送範圍
- **Decision**: 對學生與老師只送 `{id, number, sub, label}`；儲存格位置與試算表其他內容只留在伺服器。老師端另可看到來源分頁名稱。
- **Rationale**: 規格 FR-006/FR-012 與原則 III。

## D8：學生端草稿
- **Decision**: `localStorage` 鍵 `draft:<房間代碼>` 存 `{ round, values: { <題目識別碼>: 文字 } }`，所有讀寫包 try/catch；`round` 增加時清空（沿用 Step 2）；房間結束或學生離開時刪除；單格上限 500 字元。
- **Rationale**: FR-013；與 Step 2 的輪次規則並存；儲存失敗時仍可輸入。

## D9：預覽端點的存取控制
- **Decision**: `POST /api/sheets/preview` 不需房間憑證（建房前尚無憑證），僅限能讀到「已共用給機器人」的試算表；視為課堂內部使用，不另做速率限制，已知風險記錄於此。
- **Rationale**: 簡潔性；可讀取的範圍已由「是否共用給機器人」限制。若日後公開部署，再加速率限制。

## D10：題目文字於開始搶答後才顯示（需求變更，FR-014、SC-007）
- **Decision**: 解析器同時讀取「題目」欄文字存入 `Question.text`（上限 2000 字元，僅伺服器保存）。開始搶答後伺服器在 `phase_changed` 之後送出獨立事件 `question_texts`；學生 `joined.texts` 僅在房間為搶答中時有內容，其餘階段一律為 `{}`。預覽、題號清單與指紋都不含題目文字；老師的 `snapshot.room.texts` 一律完整。結束搶答時只由前端隱藏，伺服器不再補送，重連也拿不到。
- **Rationale**: 在伺服器端控制揭露時間，學生即使檢查網路封包也看不到搶答前的題目。使用獨立事件而非擴充 `phase_changed`，讓 Step 2 的契約與測試維持不變。預覽不含文字，避免「不需登入的預覽端點」多洩漏內容（見 D9）。
- **Alternatives**: 把文字放進 `phase_changed`——破壞 Step 2 的鍵集合契約；加入時一併送出、只靠畫面隱藏——學生可從封包取得，違背保密需求。
- **已知取捨**: 學生在搶答開始後已收到的文字會留在該瀏覽器記憶體中，結束後僅隱藏；課堂情境可接受。
