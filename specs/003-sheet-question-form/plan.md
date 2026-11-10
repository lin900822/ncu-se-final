# Implementation Plan: Google Sheet 連結與題目表單生成

**Branch**: `003-sheet-question-form`（規格目錄；實際在 master 開發） | **Date**: 2026-11-10 | **Spec**: [spec.md](./spec.md)

**Input**: Feature specification from `/specs/003-sheet-question-form/spec.md`；另依使用者補充與專案根目錄的兩份範例學習單（單題、題組）調整。

## Summary

老師建立房間時貼上 Google Sheet 連結 → 後端以 Google 機器人（服務帳號）讀取試算表 → 依表頭「題號／題目／作答」
辨識出題目清單（單題與題組自動辨識，每個作答格是獨立一題）→ 老師端先預覽、按「確認建立」才建房 → 題目存入房間，
經 `joined`／`snapshot` 送給學生與老師 → 學生端依題目動態生成填空格，草稿存在自己的瀏覽器。
**題目文字（試算表「題目」欄）只在老師開始搶答後才送給學生**：伺服器在 `phase_changed(Answering)` 之後以 `question_texts` 事件送出；搶答前與結束後（含重連）學生拿到的 `texts` 一律為空；預覽與題號清單不含題目文字（FR-014）。

技術做法：服務帳號 JSON 金鑰的路徑放在 `backend/.env`（`GOOGLE_SERVICE_ACCOUNT_FILE`），後端啟動時讀取；
以 `google-auth` 取得 token、`httpx` 呼叫 Sheets REST v4（只讀 scope）；解析器為純函式（格線 → 題目），以兩份範例檔做測試；
預覽與建立之間以題目指紋（fingerprint）防止試算表被中途修改。

## Technical Context

**Language/Version**: 後端 Python 3.12（uv）；前端 TypeScript、Node.js 22 LTS（沿用）

**Primary Dependencies**: 沿用 FastAPI、React 19、Vite、Tailwind v4；新增後端 `google-auth`（服務帳號取 token）、`httpx`（呼叫 Sheets API，已為 dev 依賴，升為正式依賴）、`python-dotenv`（讀 `.env`）；新增 dev 依賴 `openpyxl`（測試時把範例 xlsx 轉成格線）

**Storage**: 沿用僅記憶體；`Room` 新增 `sheet`（來源）與 `questions`（題目清單）

**Testing**: pytest。解析器以兩份範例檔（單題／題組）與合成的錯誤格式（重複、缺漏、無表頭、小題不連續）測試；Sheets 用戶端以 `httpx.MockTransport` 測錯誤對應（403/404/逾時）與「憑證不外洩」；API 測試涵蓋預覽、確認建立、指紋不符、`joined`/`snapshot` 帶題目、學生看不到儲存格位置。真實 Google 讀取以 quickstart 手動驗證

**Target Platform**: 沿用單機、單一 worker；伺服器需能連外到 `sheets.googleapis.com`、`oauth2.googleapis.com`

**Project Type**: web-application（frontend + backend）

**Performance Goals**: 預覽 10 秒內完成（SC-001，單題 50 題內）；學生加入 2 秒內看到題目（題目已在記憶體，隨 `joined` 送出）

**Constraints**: 憑證僅在伺服器端、不入版控、不寫入日誌或回應；題目文字（上限 2000 字元）僅在搶答中才送給學生；本步驟只用只讀 scope；題數上限 50、單格輸入 500 字元；題目建立後固定

**Scale/Scope**: 單房間 ≤ 50 題、≤ 40 組；前端修改首頁（建立流程）、老師端、學生端三個畫面

## Constitution Check

*GATE: Must pass before Phase 0 research. Re-check after Phase 1 design.*

| 原則 / 約束 | 本階段判定 | 說明 |
|-------------|-----------|------|
| I 組別為唯一單位；題目僅以題號管理 | ✅ 通過（含註記） | 題目為扁平清單，識別碼為「題號」或「題號-小題」，**不另存題型欄位**；題組的小題被視為獨立的一題（Spec Assumptions）。若老師希望搶答以整個題號為單位，須於 Step 4 前與 Constitution 一併修訂 |
| II 後端仲裁 | ➖ 不適用 | 本步驟無搶答 |
| III 作答保密 | ✅ 通過 | 題目清單只含識別碼與顯示標籤；儲存格位置與試算表其他內容不送出；題目文字僅在搶答中才送給學生（開始前伺服器不送，重連亦同），並有測試檢查搶答前的訊息不含題目文字；草稿只在學生瀏覽器，不送後端 |
| IV 防壟斷與仲裁 | ➖ 不適用 | 後續步驟 |
| V 回填與歷程 | ✅ 前置通過 | 建立時記錄每題的儲存格位置（A1 表示法），並驗證題號數與作答格數一致（技術約束「學習單回填」）；回填寫入留待後續 |
| VI PlantUML 設計優先 | ✅ 通過 | `diagrams/` 已含 Question、SheetSource、學習單服務、預覽/確認時序；本計畫另補指紋與憑證設定，實作後驗證一致 |
| 即時同步與斷線還原 | ✅ 通過 | 題目隨 `joined`/`snapshot` 送出，重連後由後端還原 |
| 資料完整性（append-only） | ✅ 通過 | 題目建立後不改；未新增可覆寫的歷程 |
| 隱私 | ✅ 通過 | 不蒐集個資；服務帳號 email 僅在「未共用」錯誤提示時顯示給老師（非機密） |
| 測試要求 | ✅ 通過 | 見 Testing |
| 簡潔性 | ✅ 通過 | 不引入 Google 官方大型 SDK，以 `google-auth`＋`httpx` 為最小組合；解析器為單一純函式模組 |

**使用者補充的處理**：「API key」不需要（服務帳號用 JSON 金鑰即可）；使用者要的「`.env` 填 JSON 路徑」已納入設計（`GOOGLE_SERVICE_ACCOUNT_FILE`）。
「完整存取」：本步驟只需讀取，採只讀 scope（最小權限）；回填步驟再改為讀寫 scope。試算表須共用給機器人的 `client_email`（目前檢視者即可，回填前需編輯者）。

**Post-Phase 1 重新檢查**：設計後仍全部通過，無需填寫 Complexity Tracking。

## Project Structure

### Documentation (this feature)

```text
specs/003-sheet-question-form/
├── plan.md
├── research.md
├── data-model.md
├── quickstart.md
├── contracts/
│   ├── rest-api.md
│   └── websocket.md
├── checklists/requirements.md
└── tasks.md             # 由 /speckit-tasks 產生
```

### Source Code (repository root)

```text
.gitignore                       # 修改：忽略 .env 與服務帳號金鑰檔

backend/
├── .env.example                 # 新增：GOOGLE_SERVICE_ACCOUNT_FILE 範本（不含任何金鑰）
├── pyproject.toml               # 新增依賴 google-auth、httpx、python-dotenv；dev: openpyxl
├── app/
│   ├── config.py                # 新增：載入 .env、讀取服務帳號設定（不記錄金鑰內容）
│   ├── models.py                # 修改：Question、SheetSource；Room 加 sheet/questions；新錯誤碼
│   ├── sheets/
│   │   ├── __init__.py
│   │   ├── url.py               # 解析 spreadsheetId 與 gid
│   │   ├── client.py            # 取 token、呼叫 Sheets REST、錯誤對應
│   │   └── parser.py            # 純函式：格線 → 題目清單（單題/題組、驗證）
│   ├── services/
│   │   ├── sheets.py            # preview(url)、fingerprint
│   │   ├── rooms.py             # 修改：create_room 可帶 sheetUrl+fingerprint；snapshot 含題目與 texts
│   │   └── phase.py             # 修改：開始搶答後廣播 question_texts（FR-014）
│   └── api/
│       ├── sheets.py            # 新增：POST /api/sheets/preview
│       ├── rooms.py             # 修改：POST /api/rooms 接受選填 body
│       └── ws.py                # 修改：joined 含 questions；texts 僅搶答中才有內容
└── tests/
    ├── fixtures/                # 範例學習單（單題、題組）複本，供 openpyxl 轉格線
    ├── test_sheet_parser.py
    ├── test_sheet_client.py
    └── test_questions_api.py

frontend/src/
├── lib/
│   ├── api.ts                   # 修改：previewSheet、createRoom 帶參數
│   ├── drafts.ts                # 新增：草稿存取（localStorage，皆 try/catch）
│   └── questions.ts             # 新增：依題號分組的共用函式（groupByNumber）
├── components/
│   └── QuestionFields.tsx       # 新增：依題目動態生成填空格（題組分組顯示）；搶答中顯示題目文字
└── pages/
    ├── Home.tsx                 # 修改：貼連結 → 預覽 → 確認建立；或直接建立
    ├── TeacherRoom.tsx          # 修改：顯示題目清單
    └── StudentJoin.tsx          # 修改：以 QuestionFields 取代 Step 2 的單一輸入框
```

**Structure Decision**: 沿用前後端分離。「學習單服務」對應 `services/sheets.py` ＋ `sheets/` 套件
（URL 解析、Google 用戶端、解析器三者分開，解析器為純函式以利以範例檔測試）。

## Complexity Tracking

無違反項目，不需填寫。
