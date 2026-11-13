# Tasks: 答案自動寫入回原 Google Sheet

**Input**: `/specs/010-sheet-answer-backfill/` 下的 plan.md、spec.md、research.md、data-model.md、contracts/、quickstart.md
**Prerequisites**: plan.md、spec.md（皆已備齊）；Step 1～9 已實作完成（現有 205 個後端測試通過）
**Tests**: 依 plan.md 的 Testing 與 Constitution（原則 V 精準回填、III 學生端無回填資訊、II 不改動紀錄）加入 pytest；**全部不連線 Google**（以記憶體中的 `fake_sheet` 與 `httpx.MockTransport`）；真實試算表以 quickstart.md 手動驗證
**Format**: `- [ ] T### [P?] [Story?] 描述（含檔案路徑）`；`[P]` = 可平行（不同檔案、無未完成相依）

> 使用者故事對應：US1＝老師一鍵把獲勝答案回填到原試算表（P1）、US2＝精準寫入且不破壞原試算表的其他內容（P1）、US3＝無法回填時清楚告知、且只有老師能回填（P1）、US4＝回填前確認、可重新回填並留下回填紀錄（P2）
>
> 名詞：**作答格**＝`Question.cell`（如 `'學習單'!H6`）；**計畫**＝回填計畫（寫入／清空／保留／略過）；**fake_sheet**＝測試用可讀可寫的記憶體試算表。**不修改** `Submission`、`ReviewRecord`、`Question`、`SheetSource`；**不新增依賴**；學生端與學生 WebSocket **不修改**。
>
> 與 plan 的差異：`backfill_public()` 放在 `models.py`（與 `bundle_public` 同處），避免 `rooms.py`↔`backfill.py` 循環匯入。

## Phase 1: Setup

- [X] T001 執行 `cd backend && uv run pytest` 與 `cd frontend && npx tsc -b`（於 `frontend/` 內 `nvm use`），確認 Step 1～9 基準全數通過（預期後端 205 個測試）後才開始；記下通過的測試數。本步驟不新增任何依賴

---

## Phase 2: Foundational（阻擋所有故事的共用基礎）

**⚠️ 完成前不得開始任何使用者故事**；完成後既有 205 個測試必須仍全數通過（沒有回填時行為與 Step 9 完全相同）

- [X] T002 修改 `backend/app/config.py` 與 `backend/app/models.py`：(a) `config.py` 保留 `SHEETS_SCOPE`（唯讀，**不可更動**，既有測試斷言 `endswith("spreadsheets.readonly")`），新增 `SHEETS_WRITE_SCOPE = "https://www.googleapis.com/auth/spreadsheets"`，註解註明「只用於回填寫入」；(b) `models.py` 新增 `@dataclass BackfillRecord`：`round: int`、`at: datetime`（後端 UTC）、`result: Literal["Success", "Failed"]`、`written: dict[str, str] = field(default_factory=dict)`（成功才有內容：`{作答格位址: 寫入的文字}`，僅伺服器保存、**不外送**）、`cleared: list[str] = field(default_factory=list)`、`skipped_count: int = 0`、`kept_count: int = 0`、`reason: str | None = None`（失敗時的錯誤碼）、`by: str = "Teacher"`；docstring 註明僅追加、不修改、不刪除；(c) `Room` 新增 `backfills: list[BackfillRecord] = field(default_factory=list)`；(d) 新增 `backfill_public(r) -> dict`：`{"round","at"（iso）,"written": len(r.written),"skipped": r.skipped_count,"cleared": len(r.cleared),"kept": r.kept_count,"result": r.result,"reason": r.reason,"message": _ERRORS[r.reason][0] if r.reason in _ERRORS else None}`（**不含儲存格位置與答案內容**）；(e) `_ERRORS` 新增：`"BACKFILL_NOT_ALLOWED": ("目前不開放回填，請於搶答結束後回填最新一輪", 400)`、`"BACKFILL_NO_SHEET": ("此房間未綁定試算表，無法回填", 400)`、`"BACKFILL_NOTHING": ("沒有可回填的答案", 400)`、`"BACKFILL_IN_PROGRESS": ("回填進行中，請稍候", 409)`、`"SHEET_STRUCTURE_CHANGED": ("試算表已變動，請重新建立房間後再回填", 409)`、`"SHEET_NOT_EDITABLE": ("無法寫入，請將試算表共用給機器人並設為編輯者", 403)`、`"SHEET_QUOTA": ("試算表服務使用額度已滿，請稍後再試", 429)`、`"SHEET_WRITE_FAILED": ("寫入試算表失敗，未做任何變更", 502)`
- [X] T003 新增 `backend/app/sheets/a1.py`：`parse_a1(cell: str) -> tuple[int, int]`，解析 Step 3 記錄的位址（`parser._address` 格式：`'<分頁名>'!<欄字母><列號>`，分頁名內的單引號以**兩個單引號**跳脫），回傳 **0 起算**的 `(row, col)`（例：`'學習單'!H6` → `(5, 7)`；`'a''b'!AA10` → `(9, 26)`）；格式不符丟 `ValueError`。只依標準函式庫
- [X] T004 修改 `backend/app/sheets/client.py`：(a) `_default_token_provider(config, scope)` 改為接受範圍參數，建立憑證時 `scopes=[scope]`，讀取路徑呼叫時傳 `SHEETS_SCOPE`（行為不變）；(b) 新增 `async def write_cells(self, spreadsheet_id: str, sheet_id: int, updates: list[tuple[int, int, str | None]]) -> None`：以 `SHEETS_WRITE_SCOPE` 取得權杖，對 `https://sheets.googleapis.com/v4/spreadsheets/{id}:batchUpdate` 發出**單一請求**，本文 `{"requests": [...]}`，每個 `(row, col, text)` 一個 `updateCells`：`range = {"sheetId": sheet_id, "startRowIndex": row, "endRowIndex": row+1, "startColumnIndex": col, "endColumnIndex": col+1}`、`rows = [{"values": [{"userEnteredValue": {"stringValue": text}}]}]`（`text is None` 時 `values = [{}]` 表示清空）、`fields = "userEnteredValue"`（**只寫值**）；逾時 10 秒（沿用 `TIMEOUT_SECONDS`）；(c) 寫入回應對應（契約見 `contracts/google-sheets-write.md`）：`401`／`403` → `AppError("SHEET_NOT_EDITABLE", ..., 403, {"serviceAccountEmail": email})`（訊息含機器人 email 與「設為編輯者」）；`404` → `SHEET_NOT_FOUND`；`429` → `SHEET_QUOTA`；`400` 且回應文字含 `protected`（不分大小寫）→ `SHEET_NOT_EDITABLE`；其他 `400` → `SHEET_WRITE_FAILED`；連線逾時、`5xx`、其餘非 200 → `SHEET_TIMEOUT`；錯誤與日誌**不得含金鑰內容**（沿用 `_token` 的處理）
- [X] T005 修改 `backend/app/services/sheets.py`：新增 `async def read_for_backfill(room) -> tuple[Grid, list[Question], str]`：以 `room.sheet.spreadsheet_id`、`room.sheet.sheet_id` 呼叫既有 `_fetch`（唯讀）取得 `(grid, title, sheet_id)`，再 `parse_questions(grid, title)` 得題目，回傳 `(grid, questions, fingerprint_of(questions))`；`parse_questions` 丟出的辨識錯誤（`SHEET_FORMAT_UNRECOGNIZED`、`SHEET_NO_QUESTIONS`、`SHEET_QUESTIONS_INVALID`、`SHEET_TOO_MANY_QUESTIONS`）一律轉成 `err("SHEET_STRUCTURE_CHANGED")`（表頭被改壞視同結構變動）；其餘錯誤（`SHEET_NOT_FOUND`、`SHEET_FORBIDDEN`、`SHEET_TIMEOUT`、`SHEETS_NOT_CONFIGURED`）原樣丟出
- [X] T006 新增 `backend/app/services/backfill.py` 的**純函式部分**（此檔稍後在 US1～US4 擴充；本任務只含不連線、不 await 的函式；匯入 `..models`、`..sheets.a1`、`.results`、`.effective` 不需要）：(a) `@dataclass PlanItem`：`question_id`、`label`、`action: Literal["write","clear","keep","skip"]`、`cell`、`answer: str | None`、`overwrite: bool`；`@dataclass BackfillPlan`：`items: list[PlanItem]` 與屬性 `counts -> dict`（`write`、`skip`、`clear`、`keep`、`overwrite` 五個整數）與 `can_backfill: bool`（`write + clear > 0`）；(b) `system_written(room) -> dict[str, str]`：依時間先後套用 `room.backfills` 中 `result == "Success"` 的紀錄——先 `update(r.written)`，再從結果移除 `r.cleared` 的格；Failed 紀錄**不影響**；(c) `build_plan(room, result: dict, grid: Grid) -> BackfillPlan`：`result` 為 `results.build_result(room)`（含 `results` 清單）；對 `room.questions` 每一題依序判定（每題恰一類）：有 `winnerGroup`（非 `None`）→ `write`，`answer` 為該題 `answer`，`overwrite` ＝目標格目前內容（`grid.raw(row, col)` 去除前後空白後）**非空且不等於**答案；沒有有效第一名且該題 `cell` 在 `system_written` 中：目前內容**等於**當初寫入的文字 → `clear`、**不等於** → `keep`；其餘 → `skip`；目前內容一律以 `parse_a1(q.cell)` 得到的 `(row, col)` 從 `grid` 讀取（合併儲存格以記錄的左上格為準）；(d) `target_updates(plan) -> list[tuple[int, int, str | None]]`：`write` → `(row, col, answer)`、`clear` → `(row, col, None)`，依題目順序
- [X] T007 [P] 修改 `backend/tests/conftest.py`：新增 `fake_sheet` fixture（取代 `use_sheet` 時使用；`use_sheet` 保持不變）：建立 `FakeSheet` 物件，欄位 `grid`（以 `xlsx_to_grid(FIX / name)` 載入，預設 `single.xlsx`）、`title`、`sheet_id = 0`、`writes: list[list[tuple]]`（每次批次寫入的 `updates` 清單）、`fail_next: AppError | None`；方法 `use(name)` 切換範例檔、`snapshot()` 回傳 `grid.rows` 的深拷貝、`set_cell(row, col, text)`（模擬老師手動編輯）、`insert_row(at)`（在第 `at` 列前插入空列，模擬結構變動，並同步位移 `merges`）；fixture 以 `monkeypatch` 取代 `app.services.sheets._fetch`（回傳目前 `(grid, title, sheet_id)`）與 `app.services.backfill._write_batch`（`async (spreadsheet_id, sheet_id, updates)`：若 `fail_next` 設定則丟出並清除、**不套用任何更新**；否則記錄到 `writes` 後**原子地**套用：`None` 清為 `""`、其餘設為該字串，必要時擴充 `rows`）。另新增輔助函式 `post_backfill(client, code, token, round_no=None, preview=False)`：`POST /api/rooms/{code}/backfill[/preview]`，本文 `{"round": ...}`（預設取房間目前輪次），憑證只放標頭
- [X] T008 [P] 修改 `frontend/src/lib/api.ts`：新增並 `export` 型別 `BackfillCounts = { write: number; skip: number; clear: number; keep: number; overwrite?: number }`、`BackfillItem = { questionId: string; label: string; action: 'write' | 'clear' | 'keep' | 'skip'; overwrite: boolean; answer: string | null }`、`BackfillPreview = { round: number; sheetTitle: string; sheetUrl: string; canBackfill: boolean; counts: BackfillCounts; items: BackfillItem[] }`、`BackfillRecordItem = { round: number; at: string; written: number; skipped: number; cleared: number; kept: number; result: 'Success' | 'Failed'; reason: string | null; message: string | null }`、`BackfillResult = { round: number; sheetUrl: string; counts: BackfillCounts; record: BackfillRecordItem }`；新增並 `export` `backfillPreview(code, token, round)` 與 `backfillConfirm(code, token, round)`：`POST /api/rooms/${code}/backfill/preview` 與 `/backfill`，本文 `{ round }`，標頭 `Authorization: Bearer <token>` 與 `Content-Type: application/json`，沿用既有 `request()`（憑證**只放標頭**）
- [X] T009 修改 `backend/app/services/rooms.py` 的 `snapshot()`：`room` 新增 `"backfills": [backfill_public(r) for r in room.backfills]` 與 `"sheetUrl": room.sheet.url if room.sheet else None`（僅老師）；自 `..models` 匯入 `backfill_public`

**Checkpoint**: 位址解析、寫入客戶端、計畫推導、測試用假試算表與前端型別就緒；既有 205 個測試仍全數通過、`npx tsc -b` 通過

---

## Phase 3: User Story 1 - 老師一鍵把獲勝答案回填到原試算表 (Priority: P1) 🎯 MVP

**Goal**: 搶答結束後，老師點「回填至 Google Sheet」→ 確認摘要 → 確認回填，各題有效第一名的答案寫回對應作答格；沒有有效答案的題不寫入。

**Independent Test**: Q1、Q2 各有第一名，搶答結束後預覽（不寫入）再確認：`fake_sheet` 中 Q1、Q2 作答格等於各自第一名答案，其餘作答格不變；面板顯示結果摘要與試算表連結。

### Tests for User Story 1

- [X] T010 [P] [US1] 新增 `backend/tests/test_backfill.py`（使用 `fake_sheet`、`make_ranked_room`〔Q1 由第 1、2、3 組依序送出〕、`make_bundle_room`、`post_backfill`、`post_review`、`join_student`、`flush`）：(a) **預覽唯讀**：結束搶答後 `preview` → `200`，`canBackfill == true`、`counts == {"write":1,"skip":5,"clear":0,"keep":0,"overwrite":0}`（單題範例只有 Q1 有送出），`items` 共 6 筆且 Q1 為 `write`、`answer == "ans-1"`；此時 `fake_sheet.writes == []` 且 `room.backfills == []`；(b) **確認寫入**：`POST /backfill` → `200`，`record.result == "Success"`、`written == 1`；`fake_sheet.grid` 中 Q1 作答格（以 `parse_a1(question.cell)` 取位置）內容為 `"ans-1"`，其餘作答格與回填前相同；`writes` 恰 1 次批次、含 1 筆更新；(c) **遞補**：駁回 Q1 第 1 組（Step 9）後回填 → Q1 作答格為 `"ans-2"`；(d) **無有效答案不寫入**：另一題沒人送出，其作答格維持原值；(e) **題組與小題**：`make_bundle_room`（Q3+Q4）兩組先後整組送出，回填後 Q3、Q4 各自的作答格為第一名**各題自己的答案**（`g1-3`、`g1-4`，互不串接）；`use_sheet`/`fake_sheet.use("group.xlsx")` 的題組小題（`1-1`、`1-2`…）各寫各自的格；(f) 回應 `counts`、`sheetUrl`（等於 `room.sheet.url`）與 `record` 欄位齊全；(g) 結果摘要的 `written` 等於實際寫入的格數

### Implementation for User Story 1

- [X] T011 [US1] 修改 `backend/app/services/backfill.py`（接續 T006，新增 async 部分）：(a) `async def _write_batch(spreadsheet_id: str, sheet_id: int, updates) -> None`：建立 `SheetsClient(config)`（`config.get_sheets_config()` 為 `None` 時丟 `SHEETS_NOT_CONFIGURED`）並呼叫 `write_cells`；此函式是測試替換用的**縫隙**；(b) `async def preview(room, round_no) -> dict`：驗證（本任務先做基本版：`room.sheet is None` → `BACKFILL_NO_SHEET`；`room.phase != "Ended"` 或 `round_no != room.round` → `BACKFILL_NOT_ALLOWED`）→ `sheets.read_for_backfill(room)` → `build_plan(room, results.build_result(room), grid)` → 回傳契約格式（`round`、`sheetTitle`、`sheetUrl`、`canBackfill`、`counts`〔含 `overwrite`〕、`items`〔`questionId`、`label`、`action`、`overwrite`、`answer`（只有 `write` 有值）〕）；**不寫入、不追加紀錄、不廣播**；(c) `async def execute(room, round_no) -> dict`：同樣的基本驗證 → 讀取並重新推導計畫（**以確認當下結果為準**）→ `target_updates(plan)` 為空 → `BACKFILL_NOTHING` → `await _write_batch(room.sheet.spreadsheet_id, room.sheet.sheet_id, updates)` → 成功時追加 `BackfillRecord(round=room.round, at=utcnow(), result="Success", written={cell: answer for write 項}, cleared=[cell for clear 項], skipped_count=…, kept_count=…)`，`rooms.touch(room)`，回傳 `{"round","sheetUrl","counts":{write,skip,clear,keep},"record": backfill_public(record)}`；(d) `async def publish(room)`：對老師廣播 `{"type": "backfill_updated", "backfills": [backfill_public(r) for r in room.backfills]}`，**只經 `realtime.broadcast_to_teachers`**，成功寫入後呼叫。錯誤處理、結構驗證、互斥與失敗紀錄在 US2～US4 補強。使 T010 通過
- [X] T012 [US1] 修改 `backend/app/api/rooms.py`：新增 `class BackfillBody(BaseModel)`（`round: int`）與 `@router.post("/{code}/backfill/preview")`、`@router.post("/{code}/backfill")`（皆 `authorization: str | None = Header(default=None)`）：`room = rooms.verify_teacher(code, _bearer(authorization))`（**憑證只讀標頭**；`verify_teacher` 不檢查房間狀態，房間結束後保留期內仍可回填）→ 分別呼叫 `backfill.preview(room, body.round)`、`backfill.execute(room, body.round)` 並回傳其結果；`from ..services import backfill`。契約見 `contracts/rest-api.md`
- [X] T013 [P] [US1] 新增 `frontend/src/components/BackfillPanel.tsx`：props `{ code: string; token: string; round: number; canBackfill: boolean; disabledReason?: string; sheetUrl: string | null; records: BackfillRecordItem[]; onUnauthorized: () => void }`；(a) 標題「回填至 Google Sheet」、說明「把各題獲勝組別的答案寫回原試算表（需將試算表共用給機器人並設為編輯者）」；(b) 按鈕「回填至 Google Sheet」：`canBackfill` 為假時停用並顯示 `disabledReason`；(c) 點擊 → `backfillPreview` → 顯示**確認摘要**：「將寫入 N 格、略過 M 題、清空 K 格、保留 X 格；其中 J 格原有內容將被覆寫」（`overwrite > 0` 時以醒目樣式）與 `canBackfill === false` 時的「沒有可回填的答案」（不提供確認）；摘要有「確認回填」與「取消」按鈕（取消只關閉摘要，不呼叫任何寫入）；(d) 按「確認回填」→ `backfillConfirm`，期間兩顆按鈕停用並顯示「回填中…」（防連點）；成功後顯示結果摘要（寫入／略過／清空格數、完成時間）與「開啟試算表」連結（`<a href={sheetUrl} target="_blank" rel="noreferrer">`）；(e) 錯誤以 `role="alert"` 顯示伺服器訊息；`ApiError` 且 `code === 'UNAUTHORIZED'` 時呼叫 `onUnauthorized()`；(f) 回填紀錄清單於 T023 補充。`npx tsc -b` 通過
- [X] T014 [US1] 修改 `frontend/src/pages/TeacherRoom.tsx`：(a) 新增狀態 `backfills: BackfillRecordItem[]`、`sheetUrl: string | null`；`snapshot` 事件設定 `backfills = room.backfills ?? []`、`sheetUrl = room.sheetUrl ?? null`（型別補欄位）；(b) 新增 `case 'backfill_updated'`：以 `msg.backfills` 整份覆蓋；(c) 在「匯出紀錄」區塊之前新增 `<BackfillPanel>`（**不放在 `closed` 條件內**，房間結束後仍可使用）：`canBackfill = hasSheet && roomPhase === 'Ended'`（`hasSheet` 為 `sheetTitle !== null`），`disabledReason`：未綁定試算表 →「此房間未綁定試算表」、`roomPhase === 'Answering'` →「搶答結束後才能回填」、`roomPhase === 'Waiting'` →「請先開始並結束搶答」；`onUnauthorized` 與匯出相同（`clearTeacherSession()` 並 `setRevoked(true)`）。`npx tsc -b` 通過

**Checkpoint**: US1 可獨立驗證——結束搶答後能預覽並確認回填，試算表（fake）被正確填入

---

## Phase 4: User Story 2 - 精準寫入且不破壞原試算表的其他內容 (Priority: P1)

**Goal**: 只改作答格的值；答案純文字原樣寫入；結構被改過就拒絕；任一格失敗整批不生效。

**Independent Test**: 含題組與合併儲存格的試算表回填前後逐格比對，只有目標作答格改變且內容逐字相同（含 `=1+1`、`007`、換行、500 字元）。

### Tests for User Story 2

- [X] T015 [P] [US2] 新增 `backend/tests/test_sheet_write_client.py`（仿 `test_sheet_client.py` 的 `make_client(handler)` 與 `httpx.MockTransport`）與 `backend/tests/test_a1.py`：(a) `write_cells(spreadsheet_id, 0, [(5, 7, "CPU"), (6, 7, None)])` 只送出**一次**請求到 `.../spreadsheets/<id>:batchUpdate`，本文 `requests` 兩筆 `updateCells`：第一筆 `range == {"sheetId":0,"startRowIndex":5,"endRowIndex":6,"startColumnIndex":7,"endColumnIndex":8}`、`rows == [{"values":[{"userEnteredValue":{"stringValue":"CPU"}}]}]`、`fields == "userEnteredValue"`；清空那筆 `rows == [{"values":[{}]}]`；(b) 答案 `=1+1`、`+1`、`@A1`、`007`、`3/4`、`含逗號, 與 "引號"`、`第一行\n第二行`、`中文`、500 字元皆以 `stringValue` **原文**送出（斷言送出的 JSON 字串與原文完全相同，且請求中不出現 `formulaValue`、`numberValue`）；(c) 所有請求的 `fields` 皆為 `"userEnteredValue"`（不含 `userEnteredFormat` 等其他欄位），且請求中**只含目標格**；(d) 寫入使用讀寫範圍 `SHEETS_WRITE_SCOPE`、讀取仍使用 `SHEETS_SCOPE`（以注入的 `token_provider` 記錄收到的 scope 驗證；`SHEETS_SCOPE.endswith("spreadsheets.readonly")` 仍成立）；(e) 錯誤對應：`403`／`401` → `SHEET_NOT_EDITABLE` 且 `details.serviceAccountEmail` 為機器人 email、訊息含「編輯者」；`404` → `SHEET_NOT_FOUND`；`429` → `SHEET_QUOTA`；`400` 回應文字含 `This range is protected` → `SHEET_NOT_EDITABLE`；其他 `400` → `SHEET_WRITE_FAILED`；`503`、逾時（`httpx.TimeoutException`）→ `SHEET_TIMEOUT`；以上錯誤訊息與日誌（`caplog`）皆不含 `SECRET` 金鑰字串；(f) `test_a1.py`：`'學習單'!H6` → `(5, 7)`、`'Sheet1'!A1` → `(0, 0)`、`'a''b'!AA10` → `(9, 26)`、`'x'!Z1` → `(0, 25)`、`'x'!AZ3`→`(2, 51)`；格式錯誤（`H6`、`'x'!6`、空字串）→ `ValueError`
- [X] T016 [P] [US2] 新增 `backend/tests/test_backfill_precision.py`（使用 `fake_sheet`、`make_ranked_room`、`make_bundle_room`、`post_backfill`）：(a) **逐格比對**：回填前 `before = fake_sheet.snapshot()`，回填後 `after`，所有儲存格（含題號欄、題目欄、其他列）中**只有目標作答格**內容不同，且目標格＝有效第一名答案；`merges` 不變；(b) **純文字原樣**：以學生送出下列答案作為第一名並回填，`fake_sheet` 讀回與原文**完全相同**：`=1+1`、`+1`、`-5`、`@SUM(A1)`、`007`、`3/4`、`含逗號, 與 "引號"`、`第一行\n第二行`、`中央處理器`、500 字元；(c) **結構變動拒絕**：預覽成功後 `fake_sheet.insert_row(2)`（插入一列使位置位移）再 `preview` 與 `POST /backfill` → `409`、`SHEET_STRUCTURE_CHANGED`，`fake_sheet.writes == []`、內容完全不變；分頁刪除（模擬 `_fetch` 丟 `SHEET_NOT_FOUND`）→ `404`、`SHEET_NOT_FOUND` 且無寫入；表頭被改壞（把「題號」表頭改成其他字）→ `SHEET_STRUCTURE_CHANGED`；(d) **全有或全無**：`fake_sheet.fail_next = err("SHEET_WRITE_FAILED")` 後回填 → `502`、`SHEET_WRITE_FAILED`，`fake_sheet.snapshot()` 與回填前**完全相同**（沒有任何一格被改動）；(e) 合併儲存格：作答格位於合併範圍時（在 `fake_sheet.grid.merges` 加入涵蓋作答格的合併），寫入落在記錄的左上格、`merges` 不變；(f) 一次批次：多題回填只呼叫 `_write_batch` 一次

### Implementation for User Story 2

- [X] T017 [US2] 修改 `backend/app/services/backfill.py`：在 `preview()` 與 `execute()` 讀取試算表之後加入**結構驗證**：`grid, questions, fingerprint = await sheets.read_for_backfill(room)`，若 `fingerprint != room.sheet.fingerprint` → `raise err("SHEET_STRUCTURE_CHANGED")`（**在任何寫入之前**）；確認 `execute()` 在驗證失敗或 `_write_batch` 丟出時**不追加 Success 紀錄、不呼叫第二次寫入**（失敗紀錄於 US3 的 T019 補）。使 T016(c)(d) 通過；T016 其餘項目應已由 T004～T006 通過，若有失敗一併修正

**Checkpoint**: US1＋US2 可獨立驗證——精準、純文字、不破壞其他格、結構變動被攔下

---

## Phase 5: User Story 3 - 無法回填時清楚告知，且只有老師能回填 (Priority: P1)

**Goal**: 各種無法回填的情況都給明確原因且不寫入；失敗的嘗試留下紀錄；只有老師憑證能回填；學生端沒有回填資訊。

**Independent Test**: 寫入收到 403 時得到「請將試算表共用給〈機器人 email〉並設為編輯者」且試算表不變；以學生連線、無憑證、錯誤憑證嘗試回填都被拒。

### Tests for User Story 3

- [X] T018 [P] [US3] 新增 `backend/tests/test_backfill_errors.py`：(a) **時機**：搶答中（`make_ranked_room(end=False)`）與尚未開始搶答 → `400`、`BACKFILL_NOT_ALLOWED`；`round` 不是最新一輪（開第二輪後仍送 `round: 1`）→ `BACKFILL_NOT_ALLOWED`；未綁定試算表的房間（`create_room` 不帶 `sheetUrl`）→ `400`、`BACKFILL_NO_SHEET`；以上皆 `fake_sheet.writes == []` 且 `room.backfills == []`；房間手動結束後（`POST /close`）在保留期內仍可預覽與回填 → `200`；(b) **權限**：無標頭、`Bearer wrong`、`Basic xxx`、只帶房間代碼 → `401`、`UNAUTHORIZED`，回應本文不含答案與組名，試算表不變；憑證放網址參數（`?token=`）且無標頭 → `401`；老師以恢復碼換裝置後，**舊憑證** → `401`、**新憑證** → `200`；學生 WebSocket 傳 `{"type":"backfill"}`、`{"type":"backfill_preview"}` 被忽略（不寫入、不回傳紀錄）；兩個端點皆需憑證；(c) **外部錯誤對應（經端點）**：模擬寫入丟出 `SHEET_NOT_EDITABLE`（`details.serviceAccountEmail` 存在）→ `403` 且 `error.details.serviceAccountEmail` 為機器人 email、訊息含「編輯者」；`SHEET_QUOTA` → `429`；`SHEET_TIMEOUT` → `504`；`SHEET_NOT_FOUND` → `404`；`SHEETS_NOT_CONFIGURED`（`_write_batch` 丟出）→ `503`；以上皆試算表不變；(d) **失敗紀錄**：確認端點在**開始讀取之後**的失敗（結構變動、寫入錯誤、讀取 `SHEET_FORBIDDEN`／`SHEET_NOT_FOUND`／`SHEET_TIMEOUT`）各追加一筆 `Failed` 紀錄（`reason` 為錯誤碼、`written == {}`、`cleared == []`）並廣播 `backfill_updated`；前置檢查失敗（憑證、未綁定、階段、輪次）與**預覽端點**的任何錯誤**不**追加紀錄；(e) **驗證順序**：同時不滿足多項時依序回報（未授權優先於階段、階段優先於試算表錯誤）；(f) **靜態審核**（仿 `test_export_auth.py` 的逐行正規表示式掃描，讀檔 `read_text(encoding="utf-8")`）：`backfill` 服務只被 `api/rooms.py` 匯入，`api/ws.py`、`realtime.py`、`services/groups.py`、`services/submissions.py`、`services/phase.py` 不引用；`SHEETS_WRITE_SCOPE` 只出現在 `config.py` 與 `sheets/client.py` 的寫入路徑；學生訊息（以 `make_ranked_room` 的學生連線收集）序列化後不含 `backfill`、`sheetUrl`、`backfills`

### Implementation for User Story 3

- [X] T019 [US3] 修改 `backend/app/services/backfill.py`：(a) 把 `preview()`／`execute()` 的前置驗證整理為共用函式 `_precheck(room, round_no)`，**固定順序**：`room.sheet is None` → `BACKFILL_NO_SHEET`；`room.phase != "Ended"` 或 `round_no != room.round` → `BACKFILL_NOT_ALLOWED`；（憑證與房間存在由端點的 `verify_teacher` 先處理）；(b) `execute()` 在通過前置檢查、**開始讀取之後**，以 `try/except AppError` 包住「讀取、結構驗證、推導、寫入」：發生錯誤時追加 `BackfillRecord(round=room.round, at=utcnow(), result="Failed", reason=e.code)`，`await publish(room)` 後**重新丟出**同一個例外（HTTP 回應仍是該錯誤）；`BACKFILL_NOTHING` 不屬於失敗嘗試（不追加紀錄）；`preview()` 的錯誤一律**不**追加紀錄、不廣播；(c) 其他非 `AppError` 的意外例外同樣追加 `Failed`（`reason="SHEET_TIMEOUT"`）後轉成 `err("SHEET_TIMEOUT")`，不洩漏內部資訊。使 T018 通過
- [X] T020 [US3] 修改 `frontend/src/components/BackfillPanel.tsx`：(a) 預覽或確認失敗時顯示 `ApiError.message`；`code === 'SHEET_NOT_EDITABLE'` 時另顯示說明「請在 Google 試算表的『共用』把機器人帳號設為『編輯者』後再試」，並從 `details.serviceAccountEmail` 顯示可複製的機器人 email；`SHEET_STRUCTURE_CHANGED` 顯示「試算表已變動，請重新建立房間後再回填」；`SHEET_QUOTA`、`SHEET_TIMEOUT` 顯示「請稍後再試」且可直接重試；(b) 錯誤顯示後面板回到可重新點擊的狀態，不殘留確認摘要；(c) `BACKFILL_NOT_ALLOWED`／`BACKFILL_NO_SHEET` 的訊息同樣顯示（伺服器訊息）。`npx tsc -b` 通過

**Checkpoint**: US1～US3 可獨立驗證——錯誤、權限與時機邊界清楚，失敗不改動試算表

---

## Phase 6: User Story 4 - 回填前確認、可重新回填並留下回填紀錄 (Priority: P2)

**Goal**: 預覽正確計入覆寫；可重複回填並更新為最新結果；殘留答案被清空、老師改過的格被保留；同房間一次只能一個回填；每次嘗試都有紀錄且換裝置後可查看。

**Independent Test**: 先在某作答格手動打字，預覽顯示「覆寫 1 格」；確認後完成；老師駁回第一名再回填，格內容更新為遞補者答案，回填紀錄有兩筆。

### Tests for User Story 4

- [X] T021 [P] [US4] 新增 `backend/tests/test_backfill_records.py`（使用 `fake_sheet`、`make_ranked_room`、`post_backfill`、`post_review`、老師 WebSocket）：(a) **覆寫計數**：`fake_sheet.set_cell(...)` 在 Q1 作答格先填入其他文字 → 預覽 `counts.overwrite == 1`、`items` 中 Q1 `overwrite == true`；格內容**已等於**答案時 `overwrite == 0`（相同不算覆寫）；(b) **取消不寫入**：只呼叫預覽即結束 → `fake_sheet.writes == []`、`room.backfills == []`；(c) **重新回填**：回填後駁回 Q1 第 1 組（遞補第 2 組）再回填 → Q1 作答格為第 2 組答案、紀錄共 2 筆；結果不變時再回填 → 試算表不變、無錯誤、紀錄共多 1 筆；(d) **清空殘留**：Q1 只有第 1 組送出並回填；駁回該組使 Q1 無有效答案後再回填 → 預覽 `counts.clear == 1`、確認後 Q1 作答格為 `""`，紀錄 `cleared == 1`；之後再回填一次 → 該格已不在「先前寫入」集合（`system_written` 移除）、`skip`、不再清空；(e) **保留**：回填後以 `fake_sheet.set_cell` 把 Q1 作答格改成老師自己的文字，再駁回使無有效答案並回填 → 該格**不被清空**、`counts.keep == 1`、紀錄 `kept == 1`；從未被本系統寫過的非空作答格在無有效答案時**絕不被碰**；(f) **沒有可做的事**：所有題都沒有有效答案且沒有先前寫入 → 預覽 `canBackfill == false`、確認 → `400`、`BACKFILL_NOTHING`，不寫入、**不追加紀錄**；(g) **互斥（重複 100 次）**：以 `asyncio.gather` 同時呼叫兩次 `backfill.execute`（讓 `_write_batch` 內 `await asyncio.sleep(0)` 製造交錯）→ 恰一次成功、另一次 `BACKFILL_IN_PROGRESS`（409）、`fake_sheet.writes` 恰 1 次、`room.backfills` 恰 1 筆；第一次完成後再回填屬正常的新一次（可成功）；(h) **紀錄**：每次成功／失敗各一筆，欄位 `round`、`at`（UTC、遞增）、`written`／`skipped`／`cleared`／`kept` 格數、`result`、`reason`；僅追加（既有紀錄內容在後續操作後不變）；公開格式（`snapshot.room.backfills`、`backfill_updated.backfills`、端點回應 `record`）**不含**儲存格位置（如 `'學習單'!`）與答案內容；(i) **同步與還原**：回填後老師 WebSocket 收到 `backfill_updated`（整份 `backfills`）；老師以恢復碼換裝置後 `snapshot.room.backfills` 與 `sheetUrl` 完整；`snapshot.room` 在新一輪開始後仍保留舊輪的回填紀錄；(j) **學生看不到**：學生連線收到的所有訊息序列化後不含 `backfill`、`sheetUrl`
- [X] T022 [US4] 修改 `backend/app/services/backfill.py`：在 `execute()` 加入**每房間互斥**：模組層級 `_running: set[str]`；通過 `_precheck` 後、`await` 任何東西之前（同一同步區段）檢查 `room.code in _running` → `raise err("BACKFILL_IN_PROGRESS")`，否則加入集合；整個讀取／寫入／紀錄流程以 `try/finally` 在結束時 `_running.discard(room.code)`；`preview()` 不受互斥影響；確認 `BACKFILL_IN_PROGRESS` 本身不追加紀錄。確認 `build_plan` 的 `keep`／`clear`／`overwrite` 規則與 T021(a)(d)(e) 一致，必要時修正。使 T021 通過
- [X] T023 [US4] 修改 `frontend/src/components/BackfillPanel.tsx`：(a) 確認摘要可展開逐題清單（題號、動作：寫入／清空／保留／略過、`overwrite` 者標示「將覆寫原有內容」、`write` 者顯示答案預覽，`whitespace-pre-wrap` 安全顯示、不使用 `dangerouslySetInnerHTML`）；(b) `counts.clear > 0` 時以說明文字提示「這些格先前由本系統寫入、現已無有效答案，將被清空」，`counts.keep > 0` 時提示「這些格已被您修改過，將保留不動」；(c) 面板下方新增「回填紀錄」清單（`records`，**不放在 `closed` 條件內**）：本地時間、輪次、寫入／略過／清空／保留格數、結果（成功／失敗＋`message`），依時間先後；為空顯示「尚無回填紀錄」；(d) 確認進行中兩顆按鈕與「回填至 Google Sheet」按鈕皆停用（避免連點）。`npx tsc -b` 通過

**Checkpoint**: 四個故事皆可驗證

---

## Phase 7: Polish & Cross-Cutting Concerns

- [X] T024 [P] 比對 `diagrams/class.puml`、`diagrams/component.puml`、`diagrams/sequence.puml` 與實作（`BackfillRecord` 欄位、`BackfillPlan` 推導規則〔寫入／清空／保留／略過、覆寫計數〕、回填服務的驗證順序與互斥、預覽唯讀與確認重算、單一批次全有或全無寫入與純文字寫入、失敗紀錄、`backfill_updated` 受眾、`SHEETS_WRITE_SCOPE` 只用於寫入）；不一致時修正程式或更新圖表，並執行 `java -jar plantuml.jar -charset UTF-8 -tpng diagrams/*.puml`（無 Graphviz 時加 `-Playout=smetana`）重新產圖（Constitution VI 實作後驗證）
- [X] T025 [P] 更新 `README.md`：(a) 「Google 試算表設定」第 4 點由「目前檢視者即可；之後回填答案需改為編輯者」改為「**要使用『回填至 Google Sheet』，請把試算表共用給該 email 並設為編輯者**（只搶答不回填時，檢視者即可）」；(b) 使用方式新增一點：搶答結束後老師按「回填至 Google Sheet」→ 先看確認摘要（寫入／略過／清空格數與將被覆寫的格數）→「確認回填」；只寫答案文字、只回填最新一輪、全有或全無、`=` 開頭的答案以文字寫入；審核後可再回填更新；有回填紀錄；不提供復原（請用 Google 試算表的版本記錄）；(c) 確認 `specs/010-sheet-answer-backfill/quickstart.md` 與實作一致
- [X] T026 執行完整驗證：`cd backend && uv run pytest`（全數通過，含 Step 1～9 既有測試）、`cd frontend && npx tsc -b`、`npm run build`、`npm run lint`（警告數不得多於修改前）；**畫面流程**以示範後端驗證（仿先前步驟：啟動使用 `fake_sheet` 邏輯取代 Google 讀寫的本機測試伺服器，提供已建置的前端），逐項走 `quickstart.md` 情境 1～10、13、16（確認摘要、取消不寫入、確認後結果摘要與連結、駁回後再回填、清空與保留、紀錄清單與換裝置還原、連點只寫一次、未綁定試算表停用）；情境 11、12、14、15 由自動化測試涵蓋；**真實 Google 試算表的驗證（機器人需共用為編輯者）請老師依 quickstart 手動進行**，結果不在本任務自動驗證範圍

---

## Dependencies & Execution Order

### Phase Dependencies

- **Setup (P1)** → **Foundational (P2)** → 使用者故事 → **Polish (P7)**
- US1 為 MVP（預覽＋確認＋寫入＋面板）；US2 依 T011（寫入路徑）；US3 依 T011、T017（錯誤與紀錄補強）；US4 依 T006（計畫推導）、T011、T019
- 後端同檔任務須依序：`services/backfill.py`（T006 → T011 → T017 → T019 → T022）；`api/rooms.py`（T012）；`sheets/client.py`（T004）
- 前端同檔任務須依序：`BackfillPanel.tsx`（T013 → T020 → T023）；`TeacherRoom.tsx`（T014）；`api.ts`（T008）
- 測試同檔：各故事使用各自新檔，互不衝突

### Within Each Story

- 測試任務（T010、T015、T016、T018、T021）可先寫、先看到失敗
- T002 → T003 → T004、T005、T006；T007、T008 與 T003～T006 可平行（不同檔案）；T013 與 T011、T012 可平行

### Parallel Opportunities

- Foundational：T007、T008 可與 T003～T006 平行
- US1：T010、T013 可平行（不同檔案）
- US2：T015、T016 可平行
- Polish：T024、T025 可平行

## Parallel Example: User Story 1

```bash
# 可同時進行（不同檔案）：
Task: "T010 新增 backend/tests/test_backfill.py"
Task: "T013 新增 frontend/src/components/BackfillPanel.tsx"
# 之後依序：T011 → T012（後端）；T014（前端，依 T013）
```

## Implementation Strategy

### MVP First

1. 完成 Phase 1、2（位址解析、寫入客戶端、計畫推導、假試算表、前端型別）
2. 完成 US1（預覽＋確認＋寫入＋老師端面板）→ 以 `fake_sheet` 與示範後端驗證，即達成驗證效果的主流程
3. 緊接 US2（精準與安全）——回填會修改老師的原始教材，所以 US1 與 US2 一起完成才適合給真實試算表使用

### Incremental Delivery

1. Setup + Foundational → 既有行為不變
2. US1 → 可回填（確認後寫入）
3. US2 → 純文字、只動作答格、結構驗證、全有或全無（憲章原則 V 的核心）
4. US3 → 錯誤、權限、時機與失敗紀錄（原則 III 測試）
5. US4 → 覆寫計數、清空與保留、互斥、回填紀錄與還原
6. Polish → 圖表一致性、README（編輯者權限）、完整驗證
