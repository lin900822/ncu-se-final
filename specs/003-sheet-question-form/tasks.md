# Tasks: Google Sheet 連結與題目表單生成

**Input**: `/specs/003-sheet-question-form/` 下的 plan.md、spec.md、research.md、data-model.md、contracts/、quickstart.md
**Prerequisites**: plan.md、spec.md（皆已備齊）；Step 1、Step 2 已實作完成
**Tests**: 依 plan.md 的 Testing 加入 pytest（解析器、Sheets 用戶端、題目 API、憑證不外洩）；真實 Google 讀取以 quickstart.md 手動驗證
**Format**: `- [ ] T### [P?] [Story?] 描述（含檔案路徑）`；`[P]` = 可平行（不同檔案、無未完成相依）

> 使用者故事對應：US1＝老師貼連結、預覽並確認建立房間（P1）、US2＝學生端依題目動態生成填空格（P1）、US3＝老師端確認題目清單（P2）
>
> 範例檔（專案根目錄，皆為單一分頁「學習單」）：單題＝Q1～Q6（作答格 `G5`、`G7`、`G9`、`G11`、`G13`、`G15`）；題組＝識別碼 `1-1`（`H5`）、`1-2`（`H6`）、`2-1`（`H8`）、`2-2`（`H9`）、`3`（`G11`）、`4`（`G13`）。

## Phase 1: Setup

- [X] T001 修改 `backend/pyproject.toml`：執行 `uv add google-auth httpx python-dotenv` 與 `uv add --dev openpyxl`（`httpx` 由 dev 依賴改為正式依賴）
- [X] T002 [P] 修改根目錄 `.gitignore`：新增 `.env`、`backend/.env`、`*.service-account*.json`、`credentials/`，確保服務帳號金鑰與 `.env` 不會被提交；並新增 `backend/.env.example`，內容為註解說明與 `GOOGLE_SERVICE_ACCOUNT_FILE=/絕對路徑/服務帳號金鑰.json`（不得含任何真實金鑰）
- [X] T003 [P] 將專案根目錄兩份範例學習單**複製**（不移動、不修改原檔）為 `backend/tests/fixtures/single.xlsx`（取自 `軟工期末專案_單題_範例 的副本.xlsx`）與 `backend/tests/fixtures/group.xlsx`（取自 `軟工期末專案_題組_範例 的副本.xlsx`）

---

## Phase 2: Foundational（阻擋所有故事的共用基礎）

**⚠️ 完成前不得開始任何使用者故事**

- [X] T005 修改 `backend/app/models.py`：新增 dataclass `Question`（`id: str` 如 `"3"`／`"1-2"`、`number: int` ≥ 1、`sub: int | None`、`label: str` 如 `Q3`／`Q1（2）`、`cell: str` A1 表示法含分頁名如 `'學習單'!H6`，**僅伺服器保存**）與 `SheetSource`（`url`、`spreadsheet_id`、`sheet_id: int`、`sheet_title`、`read_at`(UTC)、`fingerprint`）；`Room` 新增 `sheet: SheetSource | None = None`、`questions: list[Question]`（預設空 list）；新增 `question_public(q) -> dict`，只回 `{"id","number","sub","label"}`（不含 `cell`，原則 III）
- [X] T006 修改 `backend/app/models.py` 的 `AppError` 與錯誤表：`AppError` 新增選填 `details: dict | None`；`_ERRORS` 新增並對應 contracts/rest-api.md：`SHEET_URL_INVALID` 400「請貼上有效的 Google Sheet 連結」、`SHEETS_NOT_CONFIGURED` 503「伺服器尚未設定 Google 機器人」、`SHEET_FORBIDDEN` 403、`SHEET_NOT_FOUND` 404「找不到該試算表」、`SHEET_TIMEOUT` 504「讀取逾時，請稍後再試」、`SHEET_FORMAT_UNRECOGNIZED` 422「無法辨識學習單格式」、`SHEET_NO_QUESTIONS` 422「找不到填空格」、`SHEET_QUESTIONS_INVALID` 422、`SHEET_TOO_MANY_QUESTIONS` 422「題數超過上限（50）」、`SHEET_CHANGED` 409「試算表內容已變動，請重新讀取並確認」；並修改 `backend/app/main.py` 的 `AppError` 例外處理器，當 `details` 存在時輸出 `{"error":{"code","message","details"}}`
- [X] T007 [P] 新增 `backend/app/config.py`：以 `python-dotenv` 載入 `backend/.env`（`load_dotenv` 指向 `backend/.env`）；提供 `get_sheets_config()`，讀取環境變數 `GOOGLE_SERVICE_ACCOUNT_FILE`——未設定、檔案不存在或 JSON 缺少 `client_email`／`private_key` 時回傳 `None`（呼叫端以 `SHEETS_NOT_CONFIGURED` 處理）；成功時回傳含 `key_file` 與 `client_email` 的物件。**不得**在日誌、例外訊息或回傳物件的 `repr` 中包含 `private_key`；常數 `SHEETS_SCOPE = "https://www.googleapis.com/auth/spreadsheets.readonly"`（回填步驟才改為讀寫）
- [X] T008 [P] 新增 `backend/app/sheets/__init__.py` 與 `backend/app/sheets/url.py`：`parse_sheet_url(url) -> (spreadsheet_id, gid | None)`——只接受 `https://docs.google.com/spreadsheets/d/<id>/…`，`<id>` 須符合 `[A-Za-z0-9_-]+`；`gid` 取自 `#gid=` 或 `?gid=`；不合時拋 `SHEET_URL_INVALID`；不使用使用者提供的主機名稱發送請求。同檔或 `parser.py` 先定義 `Grid` dataclass（`rows`、`merges`）供 T004 與 T011 使用

- [X] T004 [P] 新增 `backend/tests/grid_helper.py`（原列 Phase 1，因依賴 T008 的 `Grid` 型別而移至此處；任務編號不變）：提供 `xlsx_to_grid(path) -> (Grid, sheet_title)`，以 `openpyxl` 讀取第一個分頁，輸出與 `app/sheets/parser.py` 的 `Grid` 相同的結構（`rows: list[list[str]]` 為顯示字串，數字 `1.0` 轉成 `"1"`、空格為 `""`；`merges` 為 0 起算、結束不含的 `(start_row, end_row, start_col, end_col)`）。`Grid` 型別由 T008 定義，本任務須在 T008 之後做

**Checkpoint**: 型別、錯誤碼、設定與 URL 解析就緒；既有測試仍全數通過（`uv run pytest`）

---

## Phase 3: User Story 1 - 老師貼上連結、預覽並確認建立房間 (Priority: P1) 🎯 MVP

**Goal**: 老師貼上 Google Sheet 連結，系統讀取並預覽題號清單；老師按「確認建立」才建立房間；各種失敗都不建立房間。

**Independent Test**: 貼上單題範例連結 → 預覽 Q1～Q6 → 確認建立 → 老師端有該房間；貼上題組範例得到 6 個作答格；錯誤連結／未共用／題號重複皆被擋下且不建房。

### Tests for User Story 1

- [X] T009 [P] [US1] 新增 `backend/tests/test_sheet_parser.py`：(a) 用 `grid_helper.xlsx_to_grid` 載入 `single.xlsx`，斷言辨識出 6 題，識別碼 `"1"`～`"6"`、`sub` 皆為 None、標籤 `Q1`～`Q6`、`cell` 為 `'學習單'!G5`、`G7`、`G9`、`G11`、`G13`、`G15`；(b) 載入 `group.xlsx`，斷言識別碼依序為 `1-1`（`H5`）、`1-2`（`H6`）、`2-1`（`H8`）、`2-2`（`H9`）、`3`（`G11`）、`4`（`G13`），標籤為 `Q1（1）`、`Q1（2）`、`Q2（1）`、`Q2（2）`、`Q3`、`Q4`；(c) 合成格線測試錯誤：題號 1、2、2、4 → `SHEET_QUESTIONS_INVALID` 且 `details.duplicates == [2]`、`details.missing == [3]`；小題（1）（3）→ `details.invalidSubs` 含該題號；找不到表頭 → `SHEET_FORMAT_UNRECOGNIZED`；有表頭但無題號 → `SHEET_NO_QUESTIONS`；51 題 → `SHEET_TOO_MANY_QUESTIONS`；(d) 容錯：題號欄為全形「２」、前後空白、`Q3` 寫法皆視為題號；題號 10 排在 9 之後（數字排序）
- [X] T010 [P] [US1] 新增 `backend/tests/test_sheet_client.py`：以 `httpx.MockTransport` 與注入的假 token 提供者測試 `SheetsClient`：(a) 200 回應（含 `merges` 與 `rowData`）正確轉成 `Grid`，且 `gid` 指定時取對應分頁、未指定取第一個；(b) 403 → `SHEET_FORBIDDEN` 且 `details.serviceAccountEmail` 為設定的 `client_email`；(c) 404 → `SHEET_NOT_FOUND`；(d) 逾時／連線錯誤 → `SHEET_TIMEOUT`；(e) 設定為 `None` → `SHEETS_NOT_CONFIGURED`；(f) 對所有錯誤與日誌輸出（`caplog`）斷言不含 `private_key` 字串；(g) 請求網址主機固定為 `sheets.googleapis.com`，scope 為只讀
- [X] T011 [P] [US1] 新增 `backend/tests/test_questions_api.py` 的預覽與建立部分（以 monkeypatch 讓 `services.sheets` 讀取回傳 `xlsx_to_grid` 的結果，不連 Google）：(a) `POST /api/sheets/preview` 回 200，`questions` 與 `fingerprint` 正確，且回應 JSON **不含** `cell`／儲存格位置；(b) 無效連結 400 `SHEET_URL_INVALID`；(c) `POST /api/rooms` 無 Body 仍 201 且 `questions == []`、`sheetTitle` 為 null；(d) 帶正確 `sheetUrl`＋`fingerprint` 建房成功，回應含 `questions`，`store.rooms[code].questions` 含 `cell`；(e) 指紋不符 → 409 `SHEET_CHANGED` 且 `store.rooms` 沒有新增房間；(f) 只帶其一 → 400 `BAD_REQUEST`；(g) 任一 `SHEET_*` 錯誤時 `store.rooms` 皆未新增

### Implementation for User Story 1

- [X] T012 [US1] 實作 `backend/app/sheets/parser.py`：純函式 `parse_questions(grid: Grid, sheet_title: str) -> list[Question]`，依 research.md D5：(1) 找同一列含「題號」「題目」「作答」（去空白）的表頭列並取各欄位，作答區取表頭合併範圍的欄寬；(2) 表頭下逐列掃描，題號欄（取合併範圍左上角的值）為數字（容許全形數字、前後空白、`Q3` 寫法）者開啟題號，列範圍＝其垂直合併範圍（無合併為單列），空白或非數字列忽略；(3) 題號列範圍內題目欄有文字的每列是一個作答格——作答欄最左格為 `（n）`／`(n)` 標籤則作答格為其右一格並記小題編號 n，否則為作答欄最左格（合併左上角）；單一作答格無標籤＝單題（識別碼 `n`、標籤 `Qn`），多個須為 `（1）…（k）` 連續（識別碼 `n-i`、標籤 `Qn（i）`）；(4) 驗證：「題數 ≤ 50（FR-009）；題號從 1 起連續且每個恰出現一次；小題編號從 1 起連續；題號數與作答格數一致」，違規一次列出所有有問題的題號於 `details`（`duplicates`、`missing`、`invalidSubs`）；(5) 輸出依題號再依小題編號排序的扁平清單，`cell` 為 A1 表示法含分頁名（如 `'學習單'!H6`）。無 `題型` 欄位。使 T009 全數通過
- [X] T013 [US1] 實作 `backend/app/sheets/client.py`：`SheetsClient(config, http=None, token_provider=None)`，`async fetch(spreadsheet_id, gid) -> (Grid, sheet_title, sheet_id)`。以 `google.oauth2.service_account.Credentials.from_service_account_file(config.key_file, scopes=[SHEETS_SCOPE])` 取得 token（同步呼叫放進 `asyncio.to_thread`）；以 `httpx.AsyncClient`（逾時 10 秒）呼叫 `GET https://sheets.googleapis.com/v4/spreadsheets/{id}?includeGridData=true&fields=sheets(properties(sheetId,title),merges,data(startRow,startColumn,rowData(values(formattedValue))))`；依 `gid` 選分頁（無則第一個）；將回傳的 `merges`（`startRowIndex/endRowIndex/startColumnIndex/endColumnIndex`）與 `rowData` 轉成 `Grid`（需處理 `data.startRow/startColumn` 位移）；錯誤對應見 T010；任何錯誤與日誌皆不得含 `private_key`。使 T010 全數通過
- [X] T014 [US1] 實作 `backend/app/services/sheets.py`：`async def read_questions(url) -> ReadResult`（解析網址 → 取設定（無則 `SHEETS_NOT_CONFIGURED`）→ `SheetsClient.fetch` → `parse_questions`），回傳 `questions`、`SheetSource`（含 `readAt` 用 `utcnow()`、`fingerprint`）；`fingerprint` ＝ 對「各題 `id` 與 `cell` 依序串接」做 SHA-256 的十六進位字串；`async def preview(url)` 回傳公開形狀（`sheetTitle`、`questions` 用 `question_public`、`fingerprint`），不含 `cell`
- [X] T015 [US1] 新增 `backend/app/api/sheets.py`：`POST /api/sheets/preview`（Body `{"url": str}`，無需憑證）呼叫 `services.sheets.preview`；並在 `backend/app/main.py` `include_router`
- [X] T016 [US1] 修改 `backend/app/services/rooms.py` 的 `create_room` 與 `backend/app/api/rooms.py` 的 `POST /api/rooms`：Body 改為選填 `{"sheetUrl","fingerprint"}`——兩者皆無則行為同 Step 1；只帶其一回 `BAD_REQUEST`；兩者皆有則 `read_questions` 重新讀取並比對指紋，不符拋 `SHEET_CHANGED`；**全部驗證通過後才建立 `Room`**（任何 `SHEET_*` 錯誤皆不得留下房間或恢復碼索引），再把 `sheet` 與 `questions` 寫入房間；回應新增 `sheetTitle` 與 `questions`（`question_public`；無連結為 `null`／`[]`）。使 T011 全數通過
- [X] T017 [P] [US1] 修改 `frontend/src/lib/api.ts`：新增型別 `QuestionItem = { id: string; number: number; sub: number | null; label: string }`；新增 `previewSheet(url): Promise<{ sheetTitle: string; questions: QuestionItem[]; fingerprint: string }>`；`createRoom(opts?: { sheetUrl: string; fingerprint: string })` 在有參數時以 JSON Body 呼叫；`ApiError` 新增 `details` 欄位並於 `request` 解析 `error.details`
- [X] T018 [US1] 修改 `frontend/src/pages/Home.tsx`：老師建立區新增「Google Sheet 連結」輸入框與「讀取題目」按鈕——讀取成功後顯示題號清單與題數（題組依題號分組顯示 `label`）、「確認建立」與「重新讀取／修改連結」；按確認才呼叫 `createRoom({sheetUrl, fingerprint})`；錯誤以中文顯示，`SHEET_FORBIDDEN` 時顯示 `details.serviceAccountEmail` 並提示「請將試算表共用給此帳號」，`SHEET_QUESTIONS_INVALID` 列出重複與缺漏題號，`SHEET_CHANGED` 提示重新讀取；保留既有「直接建立房間（不使用試算表）」按鈕；預覽期間不建立房間，改連結即清除預覽

**Checkpoint**: US1 可獨立驗證（quickstart 情境 1、2、6～12 的老師端部分）

---

## Phase 4: User Story 2 - 學生端依題目動態生成填空格 (Priority: P1)

**Goal**: 學生加入後看到依題目生成的填空格（題組分組），可各自輸入；草稿存在自己的瀏覽器；鎖定／解鎖沿用 Step 2。

**Independent Test**: 老師建好含題目的房間，學生加入後看到對應題號的填空格，只能在老師開始搶答後輸入，各格內容互不影響，重新整理後同一輪內文字還原。

### Tests for User Story 2

- [X] T019 [P] [US2] 於 `backend/tests/test_questions_api.py` 新增測試：(a) 含題目的房間，學生 WebSocket `joined` 含 `questions`，每筆鍵集合**恰為** `{"id","number","sub","label"}`（不含 `cell`）；(b) 無連結的房間 `joined.questions == []`；(c) 學生斷線後重新加入，`questions` 與先前相同（FR-008）；(d) 學生收到的任何訊息序列化後不含試算表位置字串（如 `!G5`、`!H6`）

### Implementation for User Story 2

- [X] T020 [US2] 修改 `backend/app/api/ws.py`：學生 `joined` 回應新增 `"questions": [question_public(q) for q in room.questions]`。使 T019 全數通過
- [X] T021 [P] [US2] 新增 `frontend/src/lib/drafts.ts`：`loadDraft(roomCode): { round: number; values: Record<string, string> } | null`、`saveDraft(roomCode, draft)`、`clearDraft(roomCode)`，鍵為 `draft:<房間代碼>`，**所有 `localStorage` 讀寫皆包 try/catch**，失敗時靜默（不得拋錯、不得影響輸入）；值內每格文字上限 500 字元（儲存前截斷）
- [X] T022 [P] [US2] 新增 `frontend/src/components/QuestionFields.tsx`：props `{ questions: QuestionItem[]; values: Record<string,string>; disabled: boolean; onChange(id, text) }`；依 `questions` 順序動態生成填空格——`sub` 為 null 的題目直接顯示 `label`（如 `Q3`），同一 `number` 的多個小題分組並顯示各自 `label`（如 `Q1（1）`、`Q1（2）`）；每格為 `<input>`／`<textarea>`，`maxLength={500}`，字數達 500 時於該格下方顯示「已達 500 字上限」提示（FR-009），`disabled` 時鎖定並套用鎖定樣式；以 React 預設跳脫輸出文字（不得使用 `dangerouslySetInnerHTML`）；手機寬度可用；只顯示題號與填空格，不顯示任何題目敘述
- [X] T023 [US2] 修改 `frontend/src/pages/StudentJoin.tsx`：新增狀態 `questions`（由 `joined.questions` 設定）與 `values: Record<string,string>`；以 `QuestionFields` 取代 Step 2 的單一作答 `<textarea>`（`disabled` 沿用 `!unlocked`，即「搶答中且連線為 open」）；`questions` 為空時不顯示填空格；輸入時 `saveDraft({round: 目前輪次, values})`。**`joined` 處理順序（避免重新整理時誤清草稿）**：(1) 先 `loadDraft(room.code)`；(2) 把 `lastRound.current` 設為草稿的 `round`（無草稿則維持目前值）；(3) 若草稿存在且 `draft.round === joined.round`，以草稿 `values` 還原；(4) 最後才呼叫 `applyPhase(joined.phase, joined.round)`——`applyPhase` 僅在 `round` **大於** `lastRound.current` 時才清空 `values` 並 `clearDraft`，因此同一輪重新整理不會清掉草稿，新一輪（輪次較大）才清空；`phase_changed` 同樣走 `applyPhase`。`onLeave`、`room_closed` 時 `clearDraft` 並清空 `values`；既有 `lastRound` 與重設邏輯（Step 2 T026）保持有效

**Checkpoint**: US1 + US2 可獨立運作（quickstart 情境 3～5、11）

---

## Phase 5: User Story 3 - 老師端確認題目清單 (Priority: P2)

**Goal**: 老師端隨時可看到本房間題目清單與題數；重新整理或換裝置回復後仍一致。

**Independent Test**: 房間建立後重新整理老師端，或以恢復碼於另一裝置回復，仍顯示相同題號清單與題數。

### Tests for User Story 3

- [X] T024 [P] [US3] 於 `backend/tests/test_questions_api.py` 新增測試：(a) 老師 WebSocket 的 `snapshot.room` 含 `sheetTitle` 與 `questions`（鍵集合同 T019、不含 `cell`）；(b) 以恢復碼 `recover` 取得新憑證後連線，`snapshot.room.questions` 與建立時相同；(c) 無連結房間的 `snapshot.room.questions == []`、`sheetTitle` 為 null

### Implementation for User Story 3

- [X] T025 [US3] 修改 `backend/app/services/rooms.py` 的 `snapshot(room)`：`room` 欄位新增 `"sheetTitle": room.sheet.sheet_title if room.sheet else None` 與 `"questions": [question_public(q) for q in room.questions]`。使 T024 全數通過
- [X] T026 [US3] 修改 `frontend/src/pages/TeacherRoom.tsx`：處理 `snapshot` 時讀取 `msg.room.questions` 與 `sheetTitle`；新增「題目」區塊顯示來源分頁名稱、題數與題號清單（題組依題號分組顯示 `label`）；無題目時顯示「本房間未設定題目」；斷線重連後以新 `snapshot` 覆蓋

**Checkpoint**: 全部使用者故事可獨立運作

---

## Phase 6: Polish & Cross-Cutting

- [X] T027 執行 `cd backend && uv run pytest`，確認新舊測試（含 Step 1、2）全數通過；並執行 `cd frontend && npx tsc -b && npm run build`（需 Node 22，於 `frontend/` 內 `nvm use`）
- [X] T028 [P] 憑證不外洩檢查：`grep -rn "private_key" backend/app` 只應出現在讀取金鑰檔的程式與驗證缺漏欄位處，且不得出現在任何 `print`、`logging`、例外訊息或回應；確認 `git status` 不含 `.env` 與金鑰 JSON；確認 `.gitignore` 生效（`git check-ignore -v backend/.env`）
- [X] T029 [P] 更新 `README.md`：新增「Google 試算表設定」章節——啟用 Sheets API、把金鑰檔放在專案外、複製 `backend/.env.example` 為 `backend/.env` 並填入 `GOOGLE_SERVICE_ACCOUNT_FILE`、把試算表共用給金鑰內的 `client_email`（目前檢視者即可，回填前需編輯者）、學習單格式說明（表頭「題號／題目／作答」、單題與題組）
- [ ] T030 依 `specs/003-sheet-question-form/quickstart.md` 以真實 Google Sheet（單題、題組各一份，已共用給機器人）手動執行情境 1～13
- [X] T031 [P] 圖表一致性檢查（Constitution VI）：比對 `diagrams/class.puml`、`component.puml`、`sequence.puml` 與程式（`Question`、`SheetSource`、學習單服務、預覽／確認／指紋流程、`.env` 憑證設定）；不一致時修正程式或更新圖表，並執行 `cd diagrams && plantuml -tpng *.puml`

---

## Dependencies & Execution Order

- Phase 1 → Phase 2 → 使用者故事 → Polish → Phase 7（需求變更：題目文字於開始搶答後才顯示，依賴 US1～US3 已完成；T032 → T033 → T034／T035 → T036 → T037／T038 → T039）。
- Phase 1 內：T001 先行（安裝依賴）；T002、T003 可平行。T004 已移至 Phase 2，須在 T008 之後做。
- Phase 2 內：T005、T006 同檔（`models.py`）須循序；T007、T008 可與 T005／T006 平行（不同檔案）；T006 同時改 `main.py`。
- US1：測試 T009～T011 可平行（不同檔案；T011 與 T019、T024 同檔須依序追加）；實作順序 T012（parser）→ T013（client）→ T014（service，依 T012、T013）→ T015（API）→ T016（rooms，依 T014）；前端 T017 可與後端平行，T018 依 T017。
- US2 依賴 US1 的建房流程（需含題目的房間）：T020 → 前端 T021、T022 可平行 → T023（依 T021、T022）。
- US3 依賴 US1：T025 → T026。
- **同檔案須循序**：`backend/app/models.py`：T005 → T006；`backend/app/services/rooms.py`：T016 → T025；`backend/app/api/ws.py`：T020；`backend/tests/test_questions_api.py`：T011 → T019 → T024；`frontend/src/pages/StudentJoin.tsx`：T023；`frontend/src/pages/TeacherRoom.tsx`：T026；`frontend/src/lib/api.ts`：T017。

## Parallel Examples

- Phase 1：T002（`.gitignore`/`.env.example`）與 T003（fixtures）。
- Phase 2：T007（`config.py`）與 T008（`sheets/url.py`）。
- US1 測試：T009（parser）、T010（client）、T011（API）。
- US2 前端：T021（`drafts.ts`）與 T022（`QuestionFields.tsx`）。
- Polish：T028、T029、T031。

## Implementation Strategy

- **MVP**：Phase 1–3（US1）即可驗證「貼連結 → 辨識題號 → 預覽 → 確認建立房間」，但完整驗證效果需 US2（學生端填空格）。
- **增量交付**：Phase 2 完成後依 US1 → US2 → US3 完成並以各自 Independent Test 驗證；每個故事結束跑 `uv run pytest`。
- **真實 Google 驗證**需要使用者先完成 quickstart 的一次性設定（`.env`、共用試算表給機器人）；自動化測試不依賴真實連線。
- 實作過程中不得把金鑰內容寫入任何檔案、日誌或對話輸出。

---

## Phase 7: 變更需求 — 題目文字於開始搶答後才顯示（FR-014、SC-007）

- [X] T032 修改 `backend/app/models.py`：`Question` 新增 `text: str = ""`（「題目」欄文字，上限 2000 字元，僅伺服器保存）；新增 `question_texts(room) -> dict[str, str]`（`{id: text}`）；`question_public` 維持不含 `text` 與 `cell`
- [X] T033 修改 `backend/app/sheets/parser.py`：每個作答格同時讀取其列「題目」欄的文字（合併範圍取左上角，去除前後空白，超過 2000 字元截斷）存入 `Question.text`；指紋仍只含 `id` 與 `cell`
- [X] T034 修改 `backend/app/realtime.py` 與 `backend/app/services/phase.py`：`start_answering` 在廣播 `phase_changed` 之後，對老師與該房間所有學生廣播 `{"type":"question_texts","round":n,"texts":{id:text}}`（無題目時不送）；`end_answering` 不送題目文字；`phase_changed` 的鍵集合維持 `{type, phase, round, changedAt}`
- [X] T035 修改 `backend/app/api/ws.py` 與 `backend/app/services/rooms.py`：學生 `joined` 新增 `texts`——房間為 `Answering` 且 `Open` 時為 `question_texts(room)`，**其餘一律為 `{}`**；老師 `snapshot.room` 新增 `texts`（一律完整，老師已通過驗證）；預覽 API 與 `question_public` 不含題目文字
- [X] T036 修改 `backend/tests/test_sheet_parser.py`、`backend/tests/test_questions_api.py`、`backend/tests/test_phase.py`：(a) 範例檔解析出的 `text` 非空且對應題目欄（如單題 Q1 含「英文縮寫」）；(b) 預覽回應與 `question_public` 不含題目文字；(c) 搶答開始前學生加入，`joined.texts == {}`，且該學生連線收到的所有訊息序列化後不含任何題目文字；(d) 老師開始搶答後，學生與老師都收到 `question_texts`，內容與題號一一對應；`phase_changed` 鍵集合仍為 `{type, phase, round, changedAt}`；(e) 搶答中學生重新加入，`joined.texts` 完整；(f) 結束搶答後重新加入，`joined.texts == {}`；(g) 老師 `snapshot.room.texts` 完整
- [X] T037 修改 `frontend/src/components/QuestionFields.tsx` 與 `frontend/src/pages/StudentJoin.tsx`：`QuestionFields` 新增選填 props `texts?: Record<string,string>`，有值時在各題標籤下方顯示題目文字（保留換行，純文字輸出，不使用 `dangerouslySetInnerHTML`）；`StudentJoin` 新增 `texts` 狀態——`joined` 時設為 `msg.texts ?? {}`、收到 `question_texts` 時設為 `msg.texts`、收到 `phase_changed` 為 `Ended` 時清空、`room_closed`／離開房間時清空；僅在 `roomPhase === 'Answering'` 且連線為 open 時傳入 `texts`
- [X] T038 修改 `frontend/src/components/QuestionFields.tsx` 的 `QuestionList` 與 `frontend/src/pages/TeacherRoom.tsx`：`QuestionList` 新增選填 `texts`，有值時改以垂直清單顯示「題號：題目文字」；老師端讀取 `snapshot.room.texts` 並傳入，收到 `question_texts` 時同步更新
- [X] T039 執行 `cd backend && uv run pytest` 與 `cd frontend && npx tsc -b && npm run build`；更新 `diagrams/class.puml`（`Question.text`）與 `diagrams/sequence.puml`（開始搶答後送 `question_texts`、加入時 `texts` 僅搶答中）並重跑 `plantuml -tpng`；以真實試算表依 quickstart 情境 3、3b 手動驗證
