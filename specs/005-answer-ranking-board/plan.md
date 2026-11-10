# Implementation Plan: 搶答順位仲裁與即時進度板

**Branch**: `005-answer-ranking-board`（規格目錄；實際在 master 開發） | **Date**: 2026-11-10 | **Spec**: [spec.md](./spec.md)

**Input**: Feature specification from `/specs/005-answer-ranking-board/spec.md`

## Summary

Step 4 的 `submit()` 已在「無 await 的同步區段」內完成階段檢查、去重與追加。本步驟在**同一個同步區段**
內，為新追加的有效送出同時賦予「單調遞增的全域序號 `seq`」與「該題該輪的名次 `rank`＝同題同輪既有紀錄數＋1」，
兩者寫入送出紀錄後不可改寫；順位因此是「後端處理先後」的直接結果，與時間戳記是否相同、客戶端時鐘無關，
且天然唯一不並列。老師端進度板（每題最快組別、依名次清單、各組領先題數）由送出紀錄**即時推導**，
每筆新送出後只推給老師連線一則 `board`（完整的本輪看板，量小），snapshot 亦帶 `board` 以支援重整與換裝置還原。
學生端與其他組別完全不收到名次、領先組別或看板資料。沿用 Step 1～4 的 FastAPI + 記憶體儲存 + React/Vite，
不新增服務或依賴。

## Technical Context

**Language/Version**: 後端 Python 3.12（uv）；前端 TypeScript、Node.js 22 LTS（沿用）

**Primary Dependencies**: 沿用 FastAPI、React 19、Vite、Tailwind v4；**不新增依賴**

**Storage**: 沿用僅記憶體；`Submission` 新增 `seq`、`rank` 兩欄，`Room` 新增 `next_seq` 計數與「每題每輪已排名數」索引；看板為推導資料、不另存

**Testing**: pytest。重點：(1) 並發——以 `asyncio.gather` 讓多組同時對同題送出（重複 100 次），名次恰為 1..n 且不重複不並列；(2) 先處理者名次優於後處理者，與任何客戶端時間無關（送出訊息夾帶假時間仍被忽略）；(3) 被拒絕／重複的送出不佔名次、不改動既有名次；(4) 看板內容：最快組別、名次清單、領先題數、「尚無組別送出」；(5) 重連／換裝置還原（snapshot 的 board）；(6) 新一輪看板清空但舊紀錄與舊名次保留；(7) 保密——所有學生連線（含同組、他組）收到的訊息序列化後不含 `rank`、`board`、他組組名與領先資訊（原則 III）

**Target Platform**: 本機/單機、單一 worker；現代桌面與手機瀏覽器

**Project Type**: web-application（frontend + backend）

**Performance Goals**: 新送出後 2 秒內老師端看板更新（SC-003）；單房間 ≤ 40 組、≤ 50 題，每次重算看板為 O(送出數) 記憶體內迭代

**Constraints**: 單一 worker（原子性依賴單一事件迴圈與無 await 的同步區段）；順位以後端處理序為準、時間一律後端 UTC；看板與名次僅送老師；「第 1 名」＝最快送出，不是最終獲勝

**Scale/Scope**: ≤ 40 組、≤ 50 題；後端新增一個推導服務與一則老師事件，前端僅老師端新增看板元件

## Constitution Check

*GATE: Must pass before Phase 0 research. Re-check after Phase 1 design.*

| 原則 / 約束 | 本階段判定 | 說明 |
|-------------|-----------|------|
| I 組別為唯一單位 | ✅ 通過 | 名次與看板皆以組別為單位，不出現學生個人 |
| II 後端依送出時間仲裁 (NON-NEGOTIABLE) | ✅ 通過 | 名次由後端在同步區段內依處理序賦予；以全域 `seq` 為唯一仲裁鍵，時間戳記僅供顯示，即使同時刻也不並列；客戶端時間不被讀取；名次寫入後不改寫（無任何更新路徑） |
| III 作答保密 | ✅ 通過 | 名次、看板、領先組別只經 `broadcast_to_teachers`；學生事件格式不變（無 rank）；有自動化測試掃描學生訊息 |
| IV 防壟斷與仲裁 | ➖ 不適用 | FR-014 明訂本步驟不做遞補與老師仲裁；順位資料（`rank`、`seq`）為其前置輸入 |
| V 回填與歷程 | ✅ 前置通過 | 每筆送出紀錄帶 `rank`、`seq`、UTC 時間，僅追加，可互相核對；匯出與回填留待後續 |
| VI PlantUML 設計優先 | ✅ 通過 | `diagrams/` 已含順位服務與看板推送；實作後須驗證一致（見 Phase 1 同步調整） |
| 即時同步與斷線還原 | ✅ 通過 | 看板由後端紀錄推導，snapshot 帶 `board`，重連即還原 |
| 資料完整性（append-only） | ✅ 通過 | 不新增可覆寫狀態；名次是紀錄的不可變欄位；看板不另存 |
| 時間來源 | ✅ 通過 | 後端 UTC |
| 隱私 | ✅ 通過 | 無新個資 |
| 測試要求 | ✅ 通過 | 涵蓋原則 II（併發名次）與 III（不外洩）；見 Testing |
| 簡潔性 | ✅ 通過 | 無新依賴、無新儲存；名次折疊進 `Submission` 欄位而非另建實體；推導邏輯集中於單一 `services/ranking.py` |

**Post-Phase 1 重新檢查**：設計後仍全部通過，無需填寫 Complexity Tracking。

## Project Structure

### Documentation (this feature)

```text
specs/005-answer-ranking-board/
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
diagrams/                        # 已更新：順位服務、名次欄位、看板推送

backend/app/
├── models.py                    # 修改：Submission 加 seq/rank；Room 加 next_seq、rank_counts
├── services/
│   ├── submissions.py           # 修改：submit() 同一同步區段內賦予 seq/rank；老師事件帶 rank
│   ├── ranking.py               # 新增：由送出紀錄推導 board（每題領先/名次清單/領先題數）
│   ├── phase.py（既有）         # 修改：新一輪開始時推送空白 board
│   └── rooms.py                 # 修改：老師 snapshot 加 board；submissions 帶 rank
└── api/ws.py                    # 修改：新送出後 broadcast_to_teachers(board)

backend/tests/
├── test_ranking.py              # 新增：名次唯一、先後、拒絕不佔名次、看板推導、新一輪
├── test_ranking_concurrency.py  # 新增：asyncio.gather 並發 100 次
└── test_ranking_privacy.py      # 新增：學生訊息不含 rank/board/他組組名（原則 III）

frontend/src/
├── components/RankingBoard.tsx  # 新增：每題最快組別、名次清單、各組領先題數、尚無送出
└── pages/TeacherRoom.tsx        # 修改：接 board 事件與 snapshot，顯示看板
```

**Structure Decision**: 沿用前後端分離。圖中「順位服務」對應 `services/submissions.py` 內的名次賦予（需與送出在同一同步區段）
與 `services/ranking.py` 的看板推導；學生端不改動。

## Complexity Tracking

無違反項目，不需填寫。
