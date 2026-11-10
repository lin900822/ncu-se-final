# Implementation Plan: 搶答結果公布看板

**Branch**: `006-results-reveal-board`（規格目錄；實際在 master 開發） | **Date**: 2026-11-10 | **Spec**: [spec.md](./spec.md)

**Input**: Feature specification from `/specs/006-results-reveal-board/spec.md`

## Summary

老師結束搶答（Step 2 的 `end_answering`）後，系統從該輪各題「名次 1」的送出紀錄（Step 5）推導出「結果」：
每題第一名組別名稱與其答案，無人送出者標示無人搶答。結果在結束搶答時以一則 `round_result` 事件同時推給
**全體學生連線與老師**，並在學生 `joined`（加入、重連、結束後才加入）與老師 `snapshot` 中於「已結束」階段還原。
結果**由送出紀錄推導、不另存**：階段一旦為 Ended，`submit()` 的階段閘門即拒絕新送出，該輪紀錄不再變動，
因此結果天然確定且不可改寫（重複結束搶答不觸發新事件）。學生端在「已結束且有結果」時切換為結果頁、新一輪開始
即離開。公布前學生協定完全不變，維持 Step 4、5 的保密。沿用 FastAPI + 記憶體儲存 + React/Vite，不新增服務或依賴。

## Technical Context

**Language/Version**: 後端 Python 3.12（uv）；前端 TypeScript、Node.js 22 LTS（沿用）

**Primary Dependencies**: 沿用 FastAPI、React 19、Vite、Tailwind v4；**不新增依賴**

**Storage**: 沿用僅記憶體；結果為推導資料，不新增欄位、不另存

**Testing**: pytest。重點：(1) 結束搶答後所有在線學生（含同組多視窗、他組）收到 `round_result`，每題僅含第 1 名組別與答案，與 `ranking.build_board` 各題 leader 一致；(2) 無人送出的題目 `winnerGroup/answer` 為 `null`；全題無人搶答也正常；(3) 保密——公布前（Waiting、Answering）學生連線收到的訊息不含 `round_result`、第一名、他組答案；公布後序列化內容不含非第一名組別的組名與答案、不含 `rank`／`board`／`leadTally`（原則 III）；(4) 離線／重整／結束後才加入的學生 `joined.result` 與公布內容相同；(5) 新一輪開始後 `joined.result` 為 `null`、學生收到階段變更；舊輪紀錄保留；(6) 重複結束搶答不重複廣播且結果不變；(7) 結束搶答瞬間的送出競態：結果只含被接受的送出；(8) 老師 `snapshot.room.result` 與學生結果一致

**Target Platform**: 本機/單機、單一 worker；現代桌面與手機瀏覽器

**Project Type**: web-application（frontend + backend）

**Performance Goals**: 結束搶答後 2 秒內全體學生畫面切換至結果頁（SC-001）；≤ 40 組、每組 ≤ 10 視窗、≤ 50 題，結果為單次 O(送出數) 推導與記憶體內扇出

**Constraints**: 單一 worker；結果只含各題第 1 名（組名＋答案）；公布前不得外送；名次與看板（Step 5）仍僅老師可見；本步驟不做遞補／仲裁／計分／回填

**Scale/Scope**: 後端新增一個推導函式與一則事件、`joined`/`snapshot` 各加一欄；前端新增學生結果頁元件並接入階段切換，老師端小幅標示

## Constitution Check

*GATE: Must pass before Phase 0 research. Re-check after Phase 1 design.*

| 原則 / 約束 | 本階段判定 | 說明 |
|-------------|-----------|------|
| I 組別為唯一單位 | ✅ 通過 | 結果以組別呈現，無個別學生 |
| II 後端依送出時間仲裁 | ✅ 通過 | 結果直接取自後端判定的名次 1，不重新比較任何時間；客戶端不參與判定 |
| III 作答保密 | ✅ 通過（關鍵） | 憲法明訂「其餘組別僅能於結算後看到獲勝內容」：公布時機＝結算（Ended）；內容僅限各題第 1 名的組名與答案，其餘組別名次與答案不外送；公布前協定不變；有自動化測試掃描公布前後的學生訊息 |
| IV 防壟斷與仲裁 | ➖ 不適用（前置） | FR-014 明訂本步驟不做；結果由單一函式從名次 1 推導，後續加入遞補／仲裁時只需改此推導 |
| V 回填與歷程 | ✅ 前置通過 | 結果僅讀取不改動送出紀錄；歷程維持僅追加；回填與匯出留待後續 |
| VI PlantUML 設計優先 | ✅ 通過 | `diagrams/` 已含結果服務、`RoundResult/ResultItem`、結算與晚加入時序；實作後須驗證一致 |
| 即時同步與斷線還原 | ✅ 通過 | `joined`／`snapshot` 於 Ended 階段由後端還原結果，不依賴客戶端狀態 |
| 資料完整性（append-only） | ✅ 通過 | 不新增可覆寫資料；結果為推導；Ended 階段閘門使該輪紀錄凍結 |
| 時間來源 | ✅ 通過 | 不新增時間欄位 |
| 隱私 | ✅ 通過 | 只公布組名與答案，無個資 |
| 測試要求 | ✅ 通過 | 涵蓋原則 III（公布前後不外洩）；II 沿用 Step 5 併發測試 |
| 簡潔性 | ✅ 通過 | 無新依賴、無新儲存；單一 `services/results.py`；不新增實體 |

**Post-Phase 1 重新檢查**：設計後仍全部通過，無需填寫 Complexity Tracking。

## Project Structure

### Documentation (this feature)

```text
specs/006-results-reveal-board/
├── plan.md
├── research.md
├── data-model.md
├── quickstart.md
├── contracts/
│   └── websocket.md
├── checklists/requirements.md
└── tasks.md             # 由 /speckit-tasks 產生
```

### Source Code (repository root)

```text
diagrams/                        # 已更新：結果服務、RoundResult/ResultItem、結算與晚加入時序

backend/app/
├── realtime.py                  # 修改：新增 broadcast_result()（全體學生，僅結果內容）；更新保密註解
├── services/
│   ├── results.py               # 新增：build_result(room)（由各題 rank=1 推導；僅 Ended 階段回傳）
│   ├── phase.py                 # 修改：end_answering 於階段廣播後送 round_result 給學生與老師
│   └── rooms.py                 # 修改：老師 snapshot 加 result
└── api/ws.py                    # 修改：學生 joined 加 result（僅 Ended 且房間開放）

backend/tests/
├── test_results.py              # 新增：結算內容、無人搶答、與看板一致、重複結束、新一輪
├── test_results_rejoin.py       # 新增：離線／重整／晚加入／同組多視窗／老師 snapshot
└── test_results_privacy.py      # 新增：公布前不外洩、公布後只含第 1 名（原則 III）

frontend/src/
├── components/ResultBoard.tsx   # 新增：學生結果頁（逐題第一名組別與答案、本組搶下、無人搶答）
├── pages/StudentJoin.tsx        # 修改：處理 round_result／joined.result；已結束且有結果→顯示結果頁；新一輪離開
└── pages/TeacherRoom.tsx        # 修改：已結束時進度板標示「最終結果」並處理 round_result（小幅）
```

**Structure Decision**: 沿用前後端分離。圖中「結果服務」對應 `services/results.py`；公布時機掛在既有的
`phase.end_answering`，不新增端點。

## Complexity Tracking

無違反項目，不需填寫。
