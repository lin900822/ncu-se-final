# Implementation Plan: 搶答歷史紀錄 CSV 匯出

**Branch**: `008-export-records-csv`（規格目錄；實際在目前分支開發） | **Date**: 2026-11-11 | **Spec**: [spec.md](./spec.md)

**Input**: Feature specification from `/specs/008-export-records-csv/spec.md`

## Summary

新增一個**唯讀**的老師端點 `GET /api/rooms/{code}/records.csv`（憑證放在 `Authorization: Bearer` 標頭，不放網址）。
後端在同一個無 await 區段內，把 `room.submissions`（所有輪次、每筆有效送出一列；題組成員各一列）整理成 CSV：
欄位為 **輪次、題號、題組、組別、答案、接收時間、排名**，依「輪次 → 題目順序 → 名次」排序。
所有資料都直接取自既有送出紀錄的 `round`／`rank`／`submitted_at`，**不重新計算名次、不另存任何資料**。

檔案以 UTF-8 加 BOM 輸出（Excel 直接開啟中文不亂碼）、CRLF 換行、標準雙引號跳脫；組別與答案若以
`=`、`+`、`-`、`@`、Tab 或換行開頭，**前面補一個單引號**，避免被試算表當成公式（FR-017）。
沒有任何有效送出時回 `404 NO_RECORDS`；房間已被清除時回 `404 RECORDS_GONE`；憑證錯誤回 `401`。
房間結束後只要仍在 24 小時保留期內，老師憑證仍有效，因此仍可匯出（US4）。

前端：`api.ts` 新增 `exportRecords()`（帶標頭 fetch → 取得 Blob → 以本地日期命名後觸發下載）；老師端新增常駐的
「匯出紀錄」區塊（搶答中、已結束、房間已結束都可用）。學生端與 WebSocket **完全不變**。
沿用 FastAPI + 記憶體儲存 + React/Vite，使用 Python 標準函式庫 `csv`，**不新增依賴**。

## Technical Context

**Language/Version**: 後端 Python 3.12（uv）；前端 TypeScript、Node.js 22 LTS（沿用）

**Primary Dependencies**: 沿用 FastAPI、React 19、Vite、Tailwind v4；CSV 使用標準函式庫 `csv`，**不新增依賴**

**Storage**: 沿用僅記憶體；匯出為由 `room.submissions` 推導的唯讀快照，不新增欄位、不保存匯出檔

**Testing**: pytest。重點：
(1) 內容：兩組先後送 Q1、一組送 Q2 → 3 列；欄位、題號標示（含題組小題 `Q1（2）`）、組別、答案原文、接收時間（`YYYY-MM-DDTHH:MM:SSZ`）、排名皆正確；
(2) 與既有資料一致：逐筆對照 `snapshot.room.submissions` 與 `ranking.build_board`（排名、時間、答案，缺漏／多出／重複皆 0）；
(3) 多輪：兩輪紀錄皆在、以輪次欄區分、排序為輪次→題目順序→名次；
(4) 題組：題組內每題各一列、同組別／同時間／同排名、題組欄為成員題號（如 `Q3、Q4`），未綁定為空；
(5) 檔案格式：以 `utf-8-sig` 解碼後用 `csv` 解析可還原；開頭為 BOM；CRLF；含逗號、雙引號、換行、中文的答案與組名原樣還原且列數不變；500 字答案不截斷；
(6) 公式安全：答案／組名以 `=`、`+`、`-`、`@`、Tab、CR、LF 開頭時儲存格以 `'` 開頭，且去掉前綴後等於原文；一般文字不被加前綴；
(7) 權限：無標頭、錯誤憑證、只帶房間代碼、換裝置後的舊憑證 → 401 且回應不含任何答案或組名；以恢復碼取得的新憑證可匯出；憑證放網址參數無效；靜態掃描確認匯出服務只被 `api/rooms.py` 使用、不被學生 WebSocket 路徑引用；
(8) 狀態：搶答中、已結束、房間手動結束後、閒置自動結束後皆可匯出且內容一致；房間被清除後 → 404 `RECORDS_GONE`；沒有紀錄 → 404 `NO_RECORDS`；
(9) 唯讀：匯出前後 `submissions`／`next_seq`／`rank_counts`／`last_activity_at` 皆不變；連續匯出 10 次內容完全相同；
(10) 標頭：`Content-Type: text/csv; charset=utf-8`、`Content-Disposition: attachment`、`Cache-Control: no-store`；
(11) 規模：40 組 × 50 題 × 3 輪（6000 列）產生時間 < 1 秒；
(12) 保密：內容不含 teacher_token、恢復碼、儲存格位置（`cell`）、`seq`

**Target Platform**: 本機/單機、單一 worker；現代桌面瀏覽器（Chrome、Edge、Safari、Firefox）與常見試算表軟體

**Project Type**: web-application（frontend + backend）

**Performance Goals**: 點擊後 2 秒內開始下載（SC-001），最大規模 6000 列的產生為 O(n log n)、記憶體內完成、約數十毫秒

**Constraints**: 單一 worker；匯出只讀、不修改任何紀錄；憑證只放標頭；回應不快取；內容只含送出紀錄（不含遞補／仲裁，尚未實作）；本步驟不做篩選、JSON、永久儲存、回填

**Scale/Scope**: 後端新增一個服務檔與一個端點、兩個錯誤碼；前端新增一個函式與一個按鈕區塊；不動 WebSocket 協定

## Constitution Check

*GATE: Must pass before Phase 0 research. Re-check after Phase 1 design.*

| 原則 / 約束 | 本階段判定 | 說明 |
|-------------|-----------|------|
| I 組別為唯一單位；題目僅以題號管理 | ✅ 通過 | 欄位只有組別名稱，不含任何個別學生身分；題組欄只是把既有題組成員的題號列出，不改變題目結構 |
| II 後端依送出時間仲裁 | ✅ 通過 | 匯出的排名與時間直接讀取送出紀錄的 `rank`／`submitted_at`（後端於送出時寫入），不重新計算、不採用任何客戶端時間 |
| III 作答保密 | ✅ 通過（關鍵） | 匯出內容含各組答案與名次，故只開放持老師憑證者；憑證放標頭（不進網址／日誌）；回應 `no-store`；學生端與 WebSocket 不含匯出；有未授權與靜態掃描測試 |
| IV 防壟斷與仲裁 | ➖ 不適用（前置） | FR-023 明訂不做；日後遞補／仲裁以新增欄位的方式擴充 |
| V 回填與歷程 | ✅ 部分達成（符合本步驟範圍） | 提供送出紀錄的可匯出 CSV，與看板／結果可逐筆核對；「結果、遞補、教師仲裁事件」待後續步驟實作後再擴充欄位；回填不在本步驟 |
| VI PlantUML 設計優先 | ✅ 通過 | `diagrams/` 已於 specify 階段加入 `ExportRow`、匯出服務與匯出時序並已產 PNG；實作後須再比對一次（見 quickstart） |
| 即時同步與斷線還原 | ✅ 通過 | 匯出每次由後端紀錄產生，不依賴客戶端狀態；換裝置以恢復碼回復後可匯出 |
| 資料完整性（append-only） | ✅ 通過 | 匯出純讀取，不修改、刪除或重排任何紀錄 |
| 時間來源 | ✅ 通過 | 接收時間為後端 UTC，原樣以 UTC 輸出（Clarification Q1） |
| 隱私 | ✅ 通過 | 只含組名與答案；不含憑證、恢復碼、儲存格位置、處理序號 |
| 測試要求 | ✅ 通過 | 覆蓋 III（未授權、不外洩）與歷程核對；II 沿用既有併發測試，匯出只讀 |
| 簡潔性 | ✅ 通過 | 無新依賴（標準 `csv`）、無新儲存、無新實體；單一 `services/export.py` |

**Post-Phase 1 重新檢查**：設計後仍全部通過，無需填寫 Complexity Tracking。

## Project Structure

### Documentation (this feature)

```text
specs/008-export-records-csv/
├── plan.md
├── research.md
├── data-model.md
├── quickstart.md
├── contracts/
│   ├── rest-api.md
│   └── csv-format.md
├── checklists/requirements.md
└── tasks.md             # 由 /speckit-tasks 產生
```

### Source Code (repository root)

```text
diagrams/                          # 已更新：ExportRow、匯出服務、匯出時序

backend/app/
├── models.py                      # 修改：新增錯誤碼 NO_RECORDS、RECORDS_GONE
├── services/
│   └── export.py                  # 新增：build_rows(room)、render_csv(room)、safe_cell()（純函式，唯讀）
└── api/rooms.py                   # 修改：GET /api/rooms/{code}/records.csv（驗證老師憑證→回 CSV）

backend/tests/
├── test_export.py                 # 新增：內容、多輪、題組、排序、與看板一致、狀態、唯讀、規模
├── test_export_format.py          # 新增：BOM／CRLF／跳脫、公式安全、500 字、保密欄位
└── test_export_auth.py            # 新增：未授權／失效憑證／網址憑證無效／靜態掃描（原則 III）

frontend/src/
├── lib/api.ts                     # 修改：exportRecords()（標頭帶憑證 → Blob → 下載）；describeError 補匯出錯誤
└── pages/TeacherRoom.tsx          # 修改：常駐「匯出紀錄」區塊（含房間已結束畫面）；401 視為身分失效
```

**Structure Decision**: 沿用前後端分離。圖中「匯出服務」對應 `services/export.py`；`ExportRow` 為推導資料，不建立資料類別，
只在函式內產生列。學生端與 `api/ws.py` 不修改。

## Complexity Tracking

無違反項目，不需填寫。
