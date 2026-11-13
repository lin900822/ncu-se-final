# Implementation Plan: 答案自動寫入回原 Google Sheet

**Branch**: `010-sheet-answer-backfill`（規格目錄；實際在目前分支開發） | **Date**: 2026-11-11 | **Spec**: [spec.md](./spec.md)

**Input**: Feature specification from `/specs/010-sheet-answer-backfill/spec.md`

## Summary

老師在面板點「回填至 Google Sheet」→ 後端先**預覽**（唯讀）：重新讀取原試算表、以 Step 3 的結構指紋驗證作答格位置沒變，
再由「最新一輪的有效結果＋題目的作答格位置＋先前回填紀錄＋試算表現況」推導**回填計畫**（要寫入、要略過、要清空、其中幾格會覆寫已有內容），
回傳確認摘要；老師按「確認回填」後，後端**以確認當下的結果重新產生計畫**，用**一次批次更新**把所有作答格寫入
（Google 的批次更新為全有或全無），答案以**字串值**寫入（不會被當成公式、不會被轉成數字或日期），只動作答格的「值」、不動格式。
成功與失敗都追加一筆**回填紀錄**（僅追加）；老師端以 `backfill_updated` 與 `snapshot.room.backfills` 即時／還原顯示。

權限：讀取維持唯讀範圍（最小權限）；只有回填的寫入動作才使用讀寫範圍（FR-021）。機器人需被共用為**編輯者**，否則寫入回 `SHEET_NOT_EDITABLE`（顯示機器人 email）。
回填只讀取結果，不改動任何送出、名次、審核紀錄；學生端與 WebSocket 學生協定完全不變。沿用 FastAPI + 記憶體儲存 + React/Vite + 既有 `httpx`，**不新增依賴**。

## Technical Context

**Language/Version**: 後端 Python 3.12（uv）；前端 TypeScript、Node.js 22 LTS（沿用）

**Primary Dependencies**: 沿用 FastAPI、Pydantic、httpx、google-auth、React 19、Vite、Tailwind v4；**不新增依賴**

**Storage**: 沿用僅記憶體。`Room` 新增 `backfills: list[BackfillRecord]`（僅追加）；回填計畫與「先前由本系統寫入的格」皆由紀錄與現況推導，不另存

**Testing**: pytest。以可寫入的 `fake_sheet`（在記憶體中模擬試算表：支援讀取與批次寫入，並記錄每次請求）取代真實 Google；另以 `httpx.MockTransport` 驗證實際送往 Google 的請求本文與錯誤對應。重點：
(1) 精準：Q1、Q2 有第一名 → 預覽與確認後，`fake_sheet` 中 Q1、Q2 作答格等於各自第一名的答案原文，其餘作答格不變；老師審核遞補後再回填 → 該格為遞補者的答案；
(2) 不破壞：回填前後整份格線逐格比對，目標作答格以外全部相同（含題號欄、題目欄、其他分頁）；請求只含 `userEnteredValue`（不碰格式）；
(3) 純文字：答案 `=1+1`、`+1`、`@A1`、`007`、`3/4`、含換行／逗號／雙引號／中文、500 字元，經 `MockTransport` 驗證以 `stringValue` 送出；`fake_sheet` 讀回完全相同；
(4) 位置：題組小題（`group.xlsx`）與老師綁定題組（Q3+Q4）各寫各自的格且內容為各題自己的答案；合併儲存格以記錄的左上格為準；
(5) 略過與清空：無人搶答或全被駁回 → 不寫入該格；先前由本系統寫入、現已無有效答案、且格內容仍等於當初寫入的文字 → 清空；格內容已被老師改過 → 保留不動（`kept`）；沒被本系統寫過的格絕不碰；
(6) 預覽：計入「將覆寫的格數」（目標格原本有內容且與答案不同）；預覽不寫入（`fake_sheet` 無寫入請求）；沒有任何可寫入或清空 → `canBackfill: false`，確認端點回 `BACKFILL_NOTHING` 且不產生回填紀錄；
(7) 全有或全無：模擬寫入失敗 → `fake_sheet` 內容完全不變，回填紀錄為失敗＋原因；
(8) 結構驗證：試算表被插入列／改題號／改分頁名（指紋不符）→ `SHEET_STRUCTURE_CHANGED` 且無寫入請求；分頁被刪除 → `SHEET_NOT_FOUND`；
(9) 權限與錯誤：寫入收到 403 → `SHEET_NOT_EDITABLE`（details 含機器人 email）；404 → `SHEET_NOT_FOUND`；429 → `SHEET_QUOTA`；逾時／5xx → `SHEET_TIMEOUT`；未設定機器人 → `SHEETS_NOT_CONFIGURED`；以上皆不寫入且記為失敗紀錄（預覽階段的失敗不記錄）；
(10) 時機與權限：搶答中／尚未開始、`round` 不是最新一輪、房間未綁定試算表 → 拒絕且無寫入；房間結束後保留期內仍可回填；無憑證、錯誤憑證、換裝置後的舊憑證、憑證放網址 → 401；學生 WebSocket 傳回填訊息被忽略；
(11) 重複與併發：回填進行中再次確認 → `BACKFILL_IN_PROGRESS`、只寫入一次、只有一筆紀錄（重複 100 次）；結果不變時再次回填 → 無錯誤、內容不變、另有一筆紀錄；
(12) 紀錄：每次嘗試（成功／失敗）各一筆，含輪次、UTC 時間、操作者、寫入／略過／清空／保留格數、結果與原因；僅追加；`snapshot.room.backfills` 與 `backfill_updated` 格式一致；換裝置回復後仍在；公開格式不含儲存格位置與答案內容；
(13) 靜態審核：回填服務只被 `api/rooms.py` 引用，學生路徑（`api/ws.py`、`realtime.py` 的學生廣播）不引用；寫入範圍字串只出現在回填寫入路徑，讀取仍用唯讀範圍；
(14) 規模：50 題一次批次寫入的請求只有一次、產生計畫 < 1 秒

**Target Platform**: 本機/單機、單一 worker；現代桌面與手機瀏覽器

**Performance Goals**: 50 題從確認到結果摘要 10 秒內（SC-001）；一次讀取、一次批次寫入，單次對外連線逾時 10 秒（沿用 Step 3）

**Constraints**: 單一 worker；回填計畫以確認當下結果為準；同房間同時只允許一個回填進行；寫入為單一批次（全有或全無）；只寫作答格的值；答案長度 ≤ 500、題數 ≤ 50（Step 3 上限）；不修改任何送出／名次／審核紀錄；不做復原、多輪回填、回填組名

**Scale/Scope**: 後端新增 `services/backfill.py`、`sheets/a1.py`，擴充 `sheets/client.py` 與 `config.py`、兩個端點、一則老師事件、八個錯誤碼；前端新增回填面板元件與 API 函式，老師頁串接

## Constitution Check

*GATE: Must pass before Phase 0 research. Re-check after Phase 1 design.*

| 原則 / 約束 | 本階段判定 | 說明 |
|-------------|-----------|------|
| I 組別為唯一單位；題目僅以題號管理 | ✅ 通過 | 回填以題目（作答格）為單位；寫入內容只有答案文字，不含任何個別學生身分；不改變題目結構 |
| II 後端依送出時間仲裁 | ✅ 通過 | 回填只讀取有效結果（名次由後端決定），不重算、不改寫任何名次或時間 |
| III 作答保密 | ✅ 通過 | 回填、預覽、回填紀錄、`backfill_updated` 皆僅老師路徑；憑證只放標頭；學生端與其收到的任何資料不含回填資訊；回填紀錄公開格式不含答案與儲存格位置；有靜態審核與學生訊息測試 |
| IV 防壟斷與仲裁 | ➖ 不適用 | 本步驟不做；回填取用「有效第一名」，日後遞補／仲裁規則改變時自動反映 |
| V 回填與歷程 | ✅ 通過（關鍵） | 實作「依題號精準回填、不錯位、不遺漏、不改寫答案文字」：以建立房間時記錄的作答格位置寫入、寫入前以結構指紋再驗證、答案以字串值原樣寫入、全有或全無；回填紀錄可與匯出歷程核對 |
| VI PlantUML 設計優先 | ✅ 通過 | `diagrams/` 已於 specify 階段加入 `BackfillRecord`／`BackfillPlan`、回填服務與回填時序並已產 PNG；實作後須再比對一次（見 quickstart） |
| 即時同步與斷線還原 | ✅ 通過 | `snapshot.room.backfills` 還原回填紀錄；`backfill_updated` 同步老師各視窗 |
| 資料完整性（append-only） | ✅ 通過 | 回填紀錄僅追加；計畫與「先前寫入的格」由紀錄推導；不修改既有紀錄 |
| 時間來源 | ✅ 通過 | 回填時間由後端 UTC 產生 |
| 學習單回填約束（題號數＝空格數） | ✅ 通過 | 作答格位置沿用 Step 3 已驗證的記錄；寫入前再驗證指紋 |
| 隱私 | ✅ 通過 | 寫入試算表的只有答案文字，不含組名、名次、時間；試算表是老師自己的 |
| 測試要求 | ✅ 通過 | 覆蓋 V（精準、不錯位、原樣文字、全有或全無）、III（學生端無回填資訊）、II（不改動紀錄） |
| 簡潔性 | ✅ 通過 | 無新依賴、無新儲存表；單一服務檔；寫入沿用既有 `httpx` 與服務帳號流程 |

**Post-Phase 1 重新檢查**：設計後仍全部通過，無需填寫 Complexity Tracking。

## Project Structure

### Documentation (this feature)

```text
specs/010-sheet-answer-backfill/
├── plan.md
├── research.md
├── data-model.md
├── quickstart.md
├── contracts/
│   ├── rest-api.md
│   ├── websocket.md
│   └── google-sheets-write.md
├── checklists/requirements.md
└── tasks.md             # 由 /speckit-tasks 產生
```

### Source Code (repository root)

```text
diagrams/                          # 已更新：BackfillRecord／BackfillPlan、回填服務、回填時序

backend/app/
├── config.py                      # 修改：新增 SHEETS_WRITE_SCOPE（讀寫）；SHEETS_SCOPE 維持唯讀
├── models.py                      # 修改：BackfillRecord、Room.backfills；錯誤碼（見 data-model）
├── sheets/
│   ├── a1.py                      # 新增：parse_a1("'分頁'!H6") → (row, col)（0 起算）
│   └── client.py                  # 修改：token provider 可指定範圍；新增 write_cells()（單一批次、字串值、只寫值）與寫入錯誤對應
├── services/
│   ├── sheets.py                  # 修改：新增 read_for_backfill()（回傳 Grid＋題目＋指紋，供回填驗證與現況比對）
│   ├── backfill.py                # 新增：build_plan()（純函式）、preview()、execute()（鎖＋寫入＋紀錄＋廣播）、backfill_public()
│   └── rooms.py                   # 修改：snapshot 加 backfills、sheetUrl
└── api/rooms.py                   # 修改：POST /api/rooms/{code}/backfill/preview、POST /api/rooms/{code}/backfill

backend/tests/
├── conftest.py                    # 修改：fake_sheet fixture（可讀可寫的記憶體試算表）
├── test_sheet_write_client.py     # 新增：請求本文（stringValue／只寫值／批次）、範圍、錯誤對應（MockTransport）
├── test_backfill_plan.py          # 新增：計畫推導（寫入／略過／清空／保留／覆寫計數）
├── test_backfill.py               # 新增：端到端精準回填、不破壞其他格、純文字、題組與合併儲存格
├── test_backfill_errors.py        # 新增：權限、時機、結構變動、各種外部錯誤、全有或全無、未授權、靜態審核
└── test_backfill_records.py       # 新增：確認流程、重複／併發、重新回填、清空殘留、回填紀錄與還原

frontend/src/
├── lib/api.ts                     # 修改：backfillPreview()、backfillConfirm()、BackfillItem／BackfillSummary 型別
├── components/BackfillPanel.tsx   # 新增：回填按鈕、確認摘要、結果摘要與試算表連結、回填紀錄清單
└── pages/TeacherRoom.tsx          # 修改：串接面板、處理 backfill_updated、401 視為身分失效
```

**Structure Decision**: 沿用前後端分離。圖中「回填服務」對應 `services/backfill.py`；對外寫入集中在 `sheets/client.py` 的單一方法，
服務層以可替換的 `_write_batch()` 縫隙呼叫，方便以 `fake_sheet` 測試。學生端與 `api/ws.py` 不修改。

## Complexity Tracking

無違反項目，不需填寫。
