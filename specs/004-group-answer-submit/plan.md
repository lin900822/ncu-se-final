# Implementation Plan: 組別答案提交與防重複送出

**Branch**: `004-group-answer-submit`（規格目錄；實際在 master 開發） | **Date**: 2026-11-10 | **Spec**: [spec.md](./spec.md)

**Input**: Feature specification from `/specs/004-group-answer-submit/spec.md`

## Summary

學生對單一題目送出答案；後端在「無 await 的同步區段」內檢查搶答中、答案有效性與「同組同題同輪是否已有紀錄」，
通過才追加一筆僅追加的送出紀錄（伺服器 UTC 時間）。結果以三種不同內容的事件扇出：
同組所有視窗收到「已送出＋內容」、老師收到「組別＋題目＋內容＋時間」、其他組別只收到不含任何組資訊的
「本題已有組別送出」。為支援同組多視窗，連線登記由「每組一條連線」改為「每組一組連線集合」，並移除 Step 1 的
「該組目前在線」拒絕規則（每組視窗上限 10）。加入、重連時由後端還原該組本輪已送出的內容與他組送出提示。
沿用 Step 1～3 的 FastAPI + 記憶體儲存 + React/Vite 架構，不新增服務或依賴。

## Technical Context

**Language/Version**: 後端 Python 3.12（uv）；前端 TypeScript、Node.js 22 LTS（沿用）

**Primary Dependencies**: 沿用 FastAPI、React 19、Vite、Tailwind v4；**不新增依賴**

**Storage**: 沿用僅記憶體；`Room` 新增 `submissions`（僅追加 list）與去重索引；重啟後消失（與房間一致，已接受，持久化與匯出留給後續步驟）

**Testing**: pytest。重點：(1) 防重複——同組同題連續 10 次與兩視窗並發，恰一筆（含以 `asyncio.gather` 直接並發呼叫服務）；(2) 保密——他組連線收到的所有訊息序列化後不含答案、組名、草稿，提示不含組數與時間（原則 III）；(3) 時間由後端產生（原則 II）；(4) 階段閘門與「結束搶答瞬間」的一致性；(5) 同組多視窗同步、加入上限、離線/在線判定；(6) 重連還原；(7) 新一輪重設但舊紀錄保留

**Target Platform**: 本機/單機、單一 worker；現代桌面與手機瀏覽器

**Project Type**: web-application（frontend + backend）

**Performance Goals**: 送出後 2 秒內同組視窗與老師端更新（SC-001、SC-002、SC-007）；單房間 40 組、每組數個視窗（≤ 10）時扇出仍為記憶體內迭代

**Constraints**: 單一 worker（原子性依賴單一事件迴圈與無 await 的同步區段）；時間一律後端 UTC；答案上限 500 字元；題目識別碼沿用 Step 3；他組事件只含題目識別碼與輪次

**Scale/Scope**: ≤ 40 組、每組 ≤ 10 視窗、≤ 50 題；前端修改學生端與老師端

## Constitution Check

*GATE: Must pass before Phase 0 research. Re-check after Phase 1 design.*

| 原則 / 約束 | 本階段判定 | 說明 |
|-------------|-----------|------|
| I 組別為唯一單位 | ✅ 通過 | 送出、去重、同步皆以組別為單位；同組多視窗共享一份送出結果；不記錄個別學生 |
| II 後端依送出時間仲裁 | ✅ 通過（前置） | 送出時間由後端在收到並接受時產生（UTC）；去重與階段檢查在同一同步區段，結果唯一；本步驟不做勝負仲裁，順序僅記錄供後續使用 |
| III 作答保密 | ✅ 通過 | 他組只收到 `{questionId, round}` 的匿名提示；答案內容只送給同組視窗與老師；草稿不送後端；有自動化測試檢查他組訊息不含答案／組名／組數／時間 |
| IV 防壟斷與仲裁 | ➖ 不適用 | 後續步驟（FR-013 明訂本步驟不做） |
| V 回填與歷程 | ✅ 前置通過 | 送出紀錄含組別、題目、輪次、內容、UTC 時間，僅追加；匯出與回填留待後續 |
| VI PlantUML 設計優先 | ✅ 通過 | `diagrams/` 已含 Submission、提交服務、提交時序（含防重複、同組同步、匿名提示）；實作後須驗證一致 |
| 即時同步與斷線還原 | ✅ 通過 | 加入/重連由後端還原本輪已送出內容與他組提示 |
| 資料完整性（append-only） | ✅ 通過 | 送出紀錄不覆寫；新一輪不刪舊紀錄；去重靠索引而非修改紀錄 |
| 時間來源 | ✅ 通過 | 後端 UTC |
| 隱私 | ✅ 通過 | 不新增個資 |
| 測試要求 | ✅ 通過 | 見 Testing；涵蓋原則 II（並發）與 III（不外洩） |
| 簡潔性 | ✅ 通過 | 無新依賴；單一 `services/submissions.py`；連線登記沿用 `Realtime`，僅把值改為集合 |

**對先前步驟的修改**：移除 Step 1 的 `GROUP_ONLINE` 拒絕（規格 FR-014 已記錄並於 Step 1 規格加註）；`Group.online` 語意改為「至少一個視窗在線」。

**Post-Phase 1 重新檢查**：設計後仍全部通過，無需填寫 Complexity Tracking。

## Project Structure

### Documentation (this feature)

```text
specs/004-group-answer-submit/
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
diagrams/                        # 已更新：Submission、提交服務、提交時序

backend/app/
├── models.py                    # 修改：Submission；Room 加 submissions/索引；錯誤碼；移除 GROUP_ONLINE
├── realtime.py                  # 修改：students 值改為連線集合；組別/他組/老師扇出方法
├── services/
│   ├── groups.py                # 修改：join 不再拒絕同組、加視窗上限；disconnect 以剩餘視窗判斷離線
│   ├── submissions.py           # 新增：submit（驗證＋去重＋追加）、狀態查詢、扇出
│   └── rooms.py                 # 修改：snapshot 含 submissions
└── api/ws.py                    # 修改：submit 訊息接上服務；joined 含 mySubmissions/submittedByOthers

backend/tests/
├── test_submissions.py          # 新增：提交、去重、並發、閘門、時間
├── test_submission_privacy.py   # 新增：他組不外洩（原則 III）
└── test_multiwindow.py          # 新增：同組多視窗、上限、在線判定、重連還原

frontend/src/
├── components/QuestionFields.tsx  # 修改：每題送出按鈕、已送出狀態、他組匿名提示
├── pages/StudentJoin.tsx          # 修改：送出、同步事件、還原、移除 GROUP_ONLINE 重試邏輯
└── pages/TeacherRoom.tsx          # 修改：顯示本輪送出清單（組別、題目、內容、時間）
```

**Structure Decision**: 沿用前後端分離。圖中「提交服務」對應 `services/submissions.py`；
同組多視窗的改動集中在 `realtime.py` 與 `services/groups.py`，不另建新模組。

## Complexity Tracking

無違反項目，不需填寫。
