# Tasks: 搶答歷史紀錄 CSV 匯出

**Input**: `/specs/008-export-records-csv/` 下的 plan.md、spec.md、research.md、data-model.md、contracts/、quickstart.md
**Prerequisites**: plan.md、spec.md（皆已備齊）；Step 1～7 已實作完成（現有 123 個後端測試通過）
**Tests**: 依 plan.md 的 Testing 與 Constitution（原則 III 不外洩、未授權）加入 pytest；真實畫面以 quickstart.md 手動驗證
**Format**: `- [ ] T### [P?] [Story?] 描述（含檔案路徑）`；`[P]` = 可平行（不同檔案、無未完成相依）

> 使用者故事對應：US1＝老師一鍵匯出作答明細 CSV（P1）、US2＝CSV 內容完整、正確且能被試算表正確開啟（P1）、US3＝只有老師能匯出（P1）、US4＝活動結束後仍能匯出（P2）
>
> 全程**不新增依賴、不新增儲存、不修改 WebSocket 與學生端**；匯出為唯讀（FR-022）。CSV 欄位標題固定為 `輪次,題號,題組,組別,答案,接收時間,排名`。

## Phase 1: Setup

- [X] T001 執行 `cd backend && uv run pytest` 與 `cd frontend && npx tsc -b`（於 `frontend/` 內 `nvm use`），確認 Step 1～7 基準全數通過（預期後端 123 個測試）後才開始；記下通過的測試數

---

## Phase 2: Foundational（阻擋所有故事的共用基礎）

**⚠️ 完成前不得開始任何使用者故事**

- [X] T002 修改 `backend/app/models.py` 的 `_ERRORS`：新增 `"NO_RECORDS": ("尚無送出紀錄可匯出", 404)` 與 `"RECORDS_GONE": ("紀錄已不存在，請於活動結束後盡快匯出", 404)`；不修改任何資料類別
- [X] T003 新增 `backend/app/services/export.py`（只匯入標準函式庫 `csv`、`io` 與 `..models`，避免循環匯入；**純函式、唯讀、整段同步不得 await**）：(a) `COLUMNS = ["輪次", "題號", "題組", "組別", "答案", "接收時間", "排名"]`；(b) `safe_cell(text: str) -> str`：若 `text` 非空且第一個字元屬於 `{'=', '+', '-', '@', '\t', '\r', '\n'}`，回傳 `"'" + text`，否則原樣回傳（只套用在使用者提供的「組別」與「答案」；補上的前綴去掉第一個字元即為原文）；(c) `build_rows(room) -> list[list]`：走訪 `room.submissions`（**所有輪次**，題組成員各一筆即各一列），每列依序為 `[s.round, 題號, 題組, safe_cell(s.group_name), safe_cell(s.answer), models.iso(s.submitted_at), s.rank]`；題號＝`room.questions` 中 `q.id == s.question_id` 的 `q.label`（找不到時用 `s.question_id`）；題組＝`s.bundle_id` 對應的 `room.bundles` 成員題號依題目順序以「、」相連（如 `Q3、Q4`），`s.bundle_id is None` 為空字串 `""`；排序鍵 `(s.round, 題目在 room.questions 中的索引, s.rank)` 由小到大（穩定排序）；**不得**輸出 `seq`、`normalized_name`、`bundle_id`、`cell`、憑證、恢復碼；(d) `render_csv(room) -> str`：以 `csv.writer(io.StringIO(), lineterminator="\r\n")`（預設最小引號策略）寫入標題列 `COLUMNS` 與 `build_rows(room)`，回傳字串**最前面加 BOM `"﻿"`**；(e) 模組 docstring 註明：僅供老師路徑、含各組答案與名次（原則 III）、純讀取（原則：僅追加）、時間為後端 UTC（原則 II）
- [X] T004 [P] 修改 `backend/tests/conftest.py`：新增 `get_export(client, code, token=None, params=None)`（`GET /api/rooms/{code}/records.csv`，有 `token` 時帶 `Authorization: Bearer <token>`，回傳 response）與 `parse_csv(response) -> list[list[str]]`（以 `response.content.decode("utf-8-sig")` 解碼，用 `csv.reader(io.StringIO(text, newline=""))` 解析，回傳含標題列的二維清單）
- [X] T005 [P] 修改 `frontend/src/lib/api.ts`：新增並 `export` `async function exportRecords(code: string, token: string): Promise<void>`：以 `fetch(`/api/rooms/${encodeURIComponent(code)}/records.csv`, { headers: { Authorization: `Bearer ${token}` } })` 取得回應（`fetch` 失敗拋 `ApiError('NETWORK', ...)`，與 `request()` 一致）；`!res.ok` 時解析 JSON 的 `error.code/message/details` 並拋 `ApiError`；成功時 `await res.blob()`，檔名為 `搶答紀錄_${code}_${YYYYMMDD}.csv`（**YYYYMMDD 取瀏覽器本地日期**，月日補零），以 `URL.createObjectURL` 建立暫時 `<a download>` 並 `click()`，之後立即 `revokeObjectURL` 與移除元素。憑證**只放標頭，不得放網址**

**Checkpoint**: 匯出核心函式、錯誤碼、測試輔助與前端下載函式就緒；既有測試仍通過

---

## Phase 3: User Story 1 - 老師一鍵匯出作答明細 CSV (Priority: P1) 🎯 MVP

**Goal**: 老師按「匯出紀錄」，2 秒內下載 CSV，內容含題號、組別、答案、接收時間與排名。

**Independent Test**: 兩組在 Q1 先後送出、一組送出 Q2 後按「匯出紀錄」，下載的 CSV 有 3 列資料，各列欄位與排名正確。

### Tests for User Story 1

- [X] T006 [P] [US1] 新增 `backend/tests/test_export.py`（使用 `use_sheet`、`make_started_room`、`join_student`、`flush`〔自 `tests/test_submission_privacy.py`〕、T004 的 `get_export`／`parse_csv`）：(a) 第 1、2 組依序送出 Q1、第 1 組送 Q2 後，老師呼叫匯出 → `200`，`parse_csv` 第一列等於 `["輪次","題號","題組","組別","答案","接收時間","排名"]`，其後恰好 3 列；(b) Q1 兩列為 `["1","Q1","","第 1 組","<答案>","<時間>","1"]` 與 `["1","Q1","","第 2 組","<答案>","<時間>","2"]`，Q2 為排名 `"1"`；(c) 接收時間符合 `^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}Z$`，且與 `store.rooms[code].submissions` 中該筆 `submitted_at` 的 `iso()` 相同（客戶端不能影響時間）；(d) 搶答進行中即可匯出（尚未結束搶答）；(e) 尚無任何送出時 → `404`、`error.code == "NO_RECORDS"`、`error.message == "尚無送出紀錄可匯出"`，且回應本文不是 CSV；(f) 回應標頭：`content-type` 以 `text/csv` 開頭且含 `charset=utf-8`、`content-disposition` 以 `attachment` 開頭且含 `records_<房間代碼>_` 與 `filename*=UTF-8''`、`cache-control == "no-store"`；(g) 題組小題範例（`use_sheet("group.xlsx")`）的題號欄為 `Q1（2）` 這類標示

### Implementation for User Story 1

- [X] T007 [US1] 修改 `backend/app/api/rooms.py`：新增 `@router.get("/{code}/records.csv")`（參數 `authorization: str | None = Header(default=None)`），流程：`room = rooms.verify_teacher(code, _bearer(authorization))` → 若 `room.submissions` 為空 `raise err("NO_RECORDS")`（**在產生檔案前判斷**）→ `body = export.render_csv(room)` → 回傳 `Response(content=body.encode("utf-8"), media_type="text/csv; charset=utf-8", headers={"Content-Disposition": f"attachment; filename=\"records_{room.code}_{utc日期YYYYMMDD}.csv\"; filename*=UTF-8''{urllib.parse.quote(f'搶答紀錄_{room.code}_{utc日期YYYYMMDD}.csv')}", "Cache-Control": "no-store"})`。**憑證只讀標頭**（不讀 query 參數）；**不呼叫 `rooms.touch()`**、不修改任何欄位。使 T006 通過
- [X] T008 [US1] 修改 `frontend/src/pages/TeacherRoom.tsx`：新增「匯出紀錄」區塊 `<section>`，標題「匯出紀錄」、一顆按鈕「匯出紀錄」與一行說明「下載所有輪次的作答明細（CSV）」；**放在任何 `closed`／`!closed` 條件之外**，使搶答中、已結束、房間已結束皆可見；狀態 `exporting: boolean`，點擊時 `setError('')`、`setExporting(true)`，呼叫 `exportRecords(session.code, session.teacherToken)`，`finally` 還原；按鈕在 `exporting` 時停用並顯示「匯出中…」（防止連點）；錯誤沿用既有 `error` 狀態顯示 `(e as Error).message`（`NO_RECORDS` 即顯示「尚無送出紀錄可匯出」，不下載）。`npx tsc -b` 通過

**Checkpoint**: US1 可獨立驗證——點擊後下載含正確欄位與排名的 CSV

---

## Phase 4: User Story 2 - CSV 內容完整、正確且能被試算表正確開啟 (Priority: P1)

**Goal**: 多輪與題組完整還原、與老師端逐筆一致、中文不亂碼、特殊字元不破壞檔案、公式字元不被執行。

**Independent Test**: 建立含兩輪搶答與一個題組的紀錄，其中答案含逗號／雙引號／換行、另一個以 `=` 開頭；匯出後內容與欄位正確、列數不變、`=` 開頭者以文字呈現。

### Tests for User Story 2

- [X] T009 [P] [US2] 新增 `backend/tests/test_export_format.py`（直接以 `export.render_csv`／`export.safe_cell` 與端點測試）：(a) 本文以 `"﻿"` 開頭（位元組 `EF BB BF`）、列分隔為 `\r\n`；(b) 答案 `含逗號, 與 "引號"`、`第一行\n第二行`、中文 `中央處理器`、組名 `A,B組` 經 `parse_csv` 還原後與原文完全相同，且資料列數不因換行增加；(c) 500 字元答案完整保留不截斷；(d) 公式安全：`safe_cell` 對 `=1+1`、`+1`、`-5`、`@SUM(A1)`、`\t=1`、`\r=1`、`\n=1` 各回傳 `"'"` 加原文，且去掉第一個字元後等於原文；對 `CPU`、`1=1`、` =1`（空白開頭）、空字串原樣回傳；(e) 經端點匯出後，答案 `=1+1` 與組名 `=SUM(1)` 在 `parse_csv` 解析出的儲存格以 `'` 開頭；(f) 匯出內容（整份文字）不含該房間的 `teacher_token`、`recovery_code`、任何 `Question.cell` 值（如 `H6`）、`seq` 數值欄與 `B1` 這類內部題組識別碼
- [X] T010 [P] [US2] 新增 `backend/tests/test_export_history.py`：(a) 兩輪搶答（結束後再開始）各有送出 → 匯出含兩輪全部紀錄，輪次欄為 `"1"`、`"2"`，排序為輪次→題目順序→排名；(b) 題組（`make_bundle_room`，Q3+Q4）整組送出 → 兩列（Q3、Q4），組別／接收時間／排名相同，題組欄皆為 `"Q3、Q4"`，未綁定題目的題組欄為空；兩組先後送出同一題組 → 排序為 Q3(排名1)、Q3(排名2)、Q4(排名1)、Q4(排名2)；(c) 一致性：匯出列數等於 `len(room.submissions)`；逐筆與老師 `snapshot.room.submissions`（組別、題目、答案、輪次、`submittedAt`、`rank`）比對無缺漏／多出／重複，且當輪排名與 `ranking.build_board(room)` 各題 `ranking` 一致；(d) 被拒絕的送出（空白、超長、非搶答中）不出現在 CSV；(e) 唯讀：匯出前後 `submissions` 長度、`next_seq`、`rank_counts`、`last_activity_at` 皆不變；連續匯出 10 次內容完全相同；(f) 規模：以 `services.rooms.create_room()` 直接建 40 組 × 50 題 × 3 輪共 6000 筆送出（仿 `test_bundle_concurrency.py` 的 `_room` 寫法），`render_csv` 耗時 < 1 秒、列數為 6000 + 標題列；(g) 題組各題「一定同時出現」：每個題組在 CSV 中的成員列數相同

### Implementation for User Story 2

- [X] T011 [US2] 檢查並補強 `backend/app/services/export.py` 使 T009、T010 全部通過：確認 `safe_cell` 套用於且僅套用於「組別」與「答案」兩欄（題號、題組、接收時間、排名不套用）；確認 `build_rows` 在題組成員紀錄上題組欄一致、未知題目 id 時退回使用 id 不丟例外；確認整個 `build_rows` 沒有 `await` 與任何寫入。若 T009、T010 已全部通過則只需確認並在任務註記「無需修改」

**Checkpoint**: US1＋US2 可獨立驗證——內容完整、格式正確、公式安全

---

## Phase 5: User Story 3 - 只有老師能匯出，學生與他人不能取得 (Priority: P1)

**Goal**: 無憑證、錯誤憑證、只知房間代碼、網址憑證、失效憑證一律被拒且不洩漏內容；學生端沒有匯出入口。

**Independent Test**: 以學生連線、無憑證與錯誤憑證三種方式嘗試取得匯出內容，全部被拒；老師憑證成功。

### Tests for User Story 3

- [X] T012 [P] [US3] 新增 `backend/tests/test_export_auth.py`：(a) 房間已有送出紀錄（答案含獨特字串 `機密答案XYZ`、組名 `機密組`）時，下列呼叫皆回 `401`、`error.code == "UNAUTHORIZED"`，且 `response.text` 不含 `機密答案XYZ`、`機密組`：不帶標頭、`Authorization: Bearer wrong`、`Authorization: Basic xxx`、只帶房間代碼；(b) 憑證放在網址參數（`?token=<正確憑證>`、`?authorization=...`）且不帶標頭 → 仍 `401`（網址憑證無效）；(c) 老師以恢復碼回復（`POST /api/rooms/recover`）後，**舊憑證**匯出 → `401`，**新憑證**匯出 → `200` 且內容完整（FR-020）；(d) 學生連線（`join_student`）在整個作答與匯出過程收到的所有訊息序列化後不含匯出相關內容（`records.csv`、`輪次,題號`、CSV 標題列），且學生 WebSocket 傳送 `{"type":"export"}` 之類訊息被忽略、不回傳紀錄；(e) 靜態掃描（仿 `test_results_privacy.py::test_static_scan_result_channels`，讀檔一律 `read_text(encoding="utf-8")`）：`export.` 服務只被 `api/rooms.py` 匯入使用，`api/ws.py`、`realtime.py`、`services/groups.py`、`services/phase.py`、`services/submissions.py` 皆不引用 `export`

### Implementation for User Story 3

- [X] T013 [US3] 修改 `frontend/src/pages/TeacherRoom.tsx` 的匯出處理（接續 T008）：捕捉 `ApiError` 且 `code === 'UNAUTHORIZED'` 時視為老師身分失效——呼叫 `clearTeacherSession()` 並 `setRevoked(true)`（與 WebSocket 4401 的既有處理一致，顯示「身分已失效，請以恢復碼回復」），不顯示原始錯誤；其他錯誤維持顯示 `error`。確認學生頁 `frontend/src/pages/StudentJoin.tsx` 與 `components/` 學生端元件**沒有**任何匯出入口（本任務不修改學生端）。`npx tsc -b` 通過

**Checkpoint**: US1～US3 可獨立驗證——匯出僅限持有效老師憑證者

---

## Phase 6: User Story 4 - 活動結束後仍能匯出，供課後留存 (Priority: P2)

**Goal**: 結束搶答、結束房間（含閒置自動結束）後，在 24 小時保留期內仍可匯出；超過後明確提示。

**Independent Test**: 結束搶答後匯出內容與結束前相同；結束房間後在「房間已結束」畫面仍能匯出；房間被清除後匯出提示紀錄已不存在。

### Tests for User Story 4

- [X] T014 [P] [US4] 新增 `backend/tests/test_export_lifecycle.py`：(a) 結束搶答（`phase/end`）前後匯出內容完全相同；(b) 老師手動結束房間（`POST /api/rooms/{code}/close`）後以同一憑證匯出 → `200` 且與結束前內容相同；(c) 房間因閒置自動結束（呼叫 `main._sweep_once()` 並將 `room.last_activity_at` 設為 3 小時前、無連線）後仍可匯出；(d) 房間被清除（`store.remove_room(code)`，模擬超過保留期或服務重啟）後以原憑證匯出 → `404`、`error.code == "RECORDS_GONE"`、`error.message == "紀錄已不存在，請於活動結束後盡快匯出"`，且不是 CSV；(e) 不存在的房間代碼（從未建立）同樣回 `RECORDS_GONE`；(f) 已結束的房間沒有任何紀錄時仍回 `NO_RECORDS`（不是 `RECORDS_GONE`）

### Implementation for User Story 4

- [X] T015 [US4] 修改 `backend/app/api/rooms.py` 的 `records.csv` 端點（接續 T007）：以 `try: room = rooms.verify_teacher(...) except AppError as e: if e.code == "ROOM_NOT_FOUND": raise err("RECORDS_GONE") from None; raise` 包住憑證驗證，只在**此端點**把房間不存在轉成 `RECORDS_GONE`（其他端點行為不變）；確認 `verify_teacher` 不檢查房間狀態，故 `Closed` 房間在保留期內仍可匯出。使 T014 通過
- [X] T016 [US4] 修改 `frontend/src/pages/TeacherRoom.tsx`：(a) 「房間已結束」提示區塊加一行說明「請先匯出紀錄；按下『回首頁』後將無法再匯出」（因 `clearTeacherSession()` 會清除老師憑證）；(b) `onClose` 的 `window.confirm` 文字補上「結束後仍可匯出紀錄，直到離開本頁」；(c) 確認 T008 的「匯出紀錄」區塊在 `closed === true` 時仍顯示且可用（`RECORDS_GONE` 顯示於既有 `error` 狀態）。`npx tsc -b` 通過

**Checkpoint**: 四個故事皆可驗證

---

## Phase 7: Polish & Cross-Cutting Concerns

- [X] T017 [P] 比對 `diagrams/class.puml`、`diagrams/component.puml`、`diagrams/sequence.puml` 與實作（匯出服務、`ExportRow` 欄位與排序、老師憑證驗證、`NO_RECORDS`／`RECORDS_GONE` 的檢查順序、公式防護、BOM／CRLF）；不一致時修正程式或更新圖表，並執行 `java -jar plantuml.jar -charset UTF-8 -tpng diagrams/*.puml`（無 Graphviz 時加 `-Playout=smetana`）重新產圖（Constitution VI 實作後驗證）
- [X] T018 [P] 更新 `README.md`（使用方式）：補上「老師端『匯出紀錄』可下載所有輪次的作答明細 CSV（輪次、題號、題組、組別、答案、接收時間 UTC、排名）；Excel 可直接開啟；紀錄只存在記憶體，房間結束後保留 24 小時、服務重啟即消失，請活動後盡快匯出」；確認 `specs/008-export-records-csv/quickstart.md` 與實作一致
- [X] T019 執行完整驗證：`cd backend && uv run pytest`（全數通過，含 Step 1～7 既有測試）、`cd frontend && npx tsc -b`、`npm run build`、`npm run lint`（警告數不得多於修改前）；依 `quickstart.md` 手動驗證情境 1～14 逐項走一遍，特別是「Excel 雙擊開啟中文不亂碼」「`=1+1` 顯示為文字」「含逗號與換行的答案在單一儲存格」「房間結束後仍可匯出」「無憑證／網址憑證回 401」

---

## Dependencies & Execution Order

### Phase Dependencies

- **Setup (P1)** → **Foundational (P2)** → 使用者故事 → **Polish (P7)**
- US1 為 MVP；US2、US3、US4 皆建立在 T003（匯出核心）與 T007（端點）之上
- 後端同檔任務須依序：`api/rooms.py`（T007 → T015）；`services/export.py`（T003 → T011）
- 前端同檔任務須依序：`TeacherRoom.tsx`（T008 → T013 → T016）；`api.ts`（T005）
- 測試同檔：各故事使用各自新檔，互不衝突

### Within Each Story

- 測試任務（T006、T009、T010、T012、T014）可先寫、先看到失敗
- T002 → T003 → T007；T005 → T008；T004 供所有後端測試使用

### Parallel Opportunities

- Foundational：T004、T005 可與 T003 平行（不同檔案）
- US1：T006（測試）與 T008（前端）可平行（T008 依 T005）
- US2：T009、T010 可平行
- US3：T012 可與 T013 平行
- Polish：T017、T018 可平行

## Parallel Example: User Story 2

```bash
# 可同時進行（不同檔案）：
Task: "T009 新增 backend/tests/test_export_format.py"
Task: "T010 新增 backend/tests/test_export_history.py"
# 之後：T011（修正 export.py 使兩者通過）
```

## Implementation Strategy

### MVP First

1. 完成 Phase 1、2（匯出核心、錯誤碼、測試輔助、前端下載函式）
2. 完成 US1（端點＋按鈕）→ 以 quickstart 情境 1～6 驗證，即達成驗證效果（下載含題號、組別、答案、接收時間、排名的 CSV）

### Incremental Delivery

1. Setup + Foundational → 基礎就緒
2. US1 → 可下載 CSV（MVP）
3. US2 → 多輪／題組完整、格式與公式安全（Excel 實際可用）
4. US3 → 權限與保密（Constitution III 測試）
5. US4 → 結束後仍可匯出與提示
6. Polish → 圖表一致性、文件、完整驗證
