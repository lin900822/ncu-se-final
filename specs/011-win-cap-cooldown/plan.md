# Implementation Plan: 公平機制：獲勝上限與冷卻限制

**Branch**: `011-win-cap-cooldown`（規格目錄；實際在目前分支開發） | **Date**: 2026-11-11 | **Spec**: [spec.md](./spec.md)

**Input**: Feature specification from `/specs/011-win-cap-cooldown/spec.md`

## Summary

老師在建立房間時（預覽之後、確認之前）可選填**每組獲勝上限**與**冷卻秒數**；規則隨房間確定、之後不可改，並公開給學生（等待搶答階段顯示）。

核心是把 Step 9 的「有效第一名」推導升級成一個**確定性的分配演算法**，仍集中在 `services/effective.py`：
1. 取本輪所有**未被駁回**的送出作為「資格申請」，依**後端處理序 `seq`** 由先到後逐筆判定；
2. 一筆申請若其單位已有人取得 → 標示「名次落後」；否則檢查資格——該組目前取得題數 **< 上限**，且距離上一次取得已達**冷卻秒數**——符合就取得該單位（題組計 N 題），不符則**讓位**（單位保持開放，由原始名次下一順位的後續申請遞補）；
3. 全部判定完仍沒有人取得、但有有效送出的單位，由**原始名次最前者「保留」**（題目不懸空）。

這個結果以 `Allocation`（每個單位的獲勝送出＋每筆送出的狀態）回傳，`effective_winners()` 仍回傳各單位的獲勝送出，所以**結果公布、老師看板、領先題數、回填試算表、匯出 CSV 全部自動採用讓位後的結果**；不改動任何 `Submission`（原始答案、時間、處理序、名次永不改寫）。
老師駁回／恢復後整輪重新分配（可能連動其他題目），`review_updated` 多帶 `changedUnits` 讓老師看出連動；看板每筆多帶 `outcome` 與規則，CSV 追加「獲勝狀態」「未獲勝原因」兩欄。沿用 FastAPI + 記憶體儲存 + React/Vite，**不新增依賴、不新增儲存**。

## Technical Context

**Language/Version**: 後端 Python 3.12（uv）；前端 TypeScript、Node.js 22 LTS（沿用）

**Primary Dependencies**: 沿用 FastAPI、Pydantic、React 19、Vite、Tailwind v4；**不新增依賴**

**Storage**: 沿用僅記憶體。`Room` 新增 `fairness: FairnessRule`（`win_cap: int | None`、`cooldown_seconds: int`），建立後不可修改；分配結果為推導資料，不另存；`Submission`、`ReviewRecord` **不修改**

**Testing**: pytest。重點：
(1) **驗證效果情境**：上限 2，第 1 組依序對 Q1～Q5 都最快送出，第 2 組對 Q3 送出（第 2 名）→ Q1、Q2 為第 1 組、Q3 為第 2 組；Q4、Q5 無其他送出者 → 第 1 組以「保留」取得；若第 3 組也送出 Q4，則 Q4 由第 3 組取得；
(2) **讓位順序**：一題原始名次為「已達上限、已達上限、未達上限」→ 由第三順位取得；兩組皆達上限且無人可遞補 → 名次最前者保留；
(3) **處理序語意**：「成功搶得 2 題」依處理序較早取得的兩個單位（以不同送出順序驗證取得的是哪兩題）；
(4) **審核連動**：駁回第 1 組的 Q1 使其空出名額，原本讓位的 Q3 改回第 1 組、第 2 組失去 Q3；恢復後回到原狀；`changedUnits` 列出被連動的單位；
(5) **題組**：取得題組計 N 題；取得前題數 < 上限即可取得（可略超過一次）；題組大於上限仍可被取得；
(6) **冷卻**：冷卻 30 秒、第 0 秒取得 Q1、第 10 秒對 Q2 最快 → Q2 讓位；第 50 秒對 Q3 最快 → 取得；被讓位／被駁回的送出不啟動冷卻；冷卻只看後端記錄的 `submitted_at`（以注入的送出時間驗證，與客戶端時鐘無關）；上限＋冷卻同時生效；
(7) **確定性與性質**：至少 100 組隨機送出／駁回序列，每步以**獨立的簡單參考實作**重算比對；相同輸入重複計算 100 次結果完全相同；任何情況下不動 `Submission`（逐欄比對）；每個有有效送出的單位必有獲勝者；上限在「有其他符合資格者可遞補」時不被突破；
(8) **向下相容**：未設定規則的房間，`results`／`board`／匯出／回填與 Step 10 完全相同（既有 289 個測試在僅調整欄位數斷言後全數通過）；
(9) **建立房間驗證**：上限 0、負數、非整數、大於題目數、冷卻負數／大於 600／非整數、無試算表卻帶規則 → `400 FAIRNESS_INVALID`（`details.reason`）且不建立房間；`null`／省略／上限等於題目數／冷卻 0 皆可；規則在建立回應、`joined`、老師 `snapshot` 一致；以恢復碼回復後不變；
(10) **一致性**：同一份讓位後結果在老師 `snapshot.result`、學生 `round_result`／`joined.result`、`build_board.leader`、`leadTally`、CSV「獲勝狀態」、回填寫入內容逐題一致；
(11) **保密**：搶答進行中學生收到的所有訊息不含分配結果、名次、獲勝題數、是否達上限；學生唯一能取得的公平資訊是規則本身（`joined.fairness` 只含 `winCap`、`cooldownSeconds`）；結算後學生只收到各題獲勝組名與答案，不含 `outcome`、`Yielded`、`Kept`；
(12) **匯出**：CSV 新增兩欄；獲勝者「獲勝」、原因空白；未獲勝者依序為被駁回／已達上限／冷卻中／名次落後；舊輪也依該輪規則與審核重算；
(13) **規模**：40 組 × 50 題 × 3 輪（6000 筆送出）一次分配 < 1 秒

**Target Platform**: 本機/單機、單一 worker；現代桌面與手機瀏覽器

**Performance Goals**: 駁回／恢復後 2 秒內全班一致（沿用 Step 9）；分配為 O(n log n)（以 `seq` 排序一次）的記憶體內推導；看板、結果、匯出各自呼叫一次，6000 筆 < 1 秒

**Constraints**: 單一 worker；分配只依後端處理序與後端 `submitted_at`；達上限的組別仍可送出（不阻擋）；規則建立後不可改；每輪獨立計算；不改動任何送出／名次／審核紀錄；學生端結算前無分配資訊；不做跨輪累計、動態調整規則、重開題目、指定獲勝組別

**Scale/Scope**: 後端新增 `services/fairness.py`（驗證）、`FairnessRule` 與一個錯誤碼，改寫 `effective.py` 的獲勝者推導並新增 `allocate()`；修改 `ranking`／`export`／`review`／`rooms`／`api` 與 `ws`；前端新增規則設定元件並修改預覽頁、學生頁、看板與老師頁

## Constitution Check

*GATE: Must pass before Phase 0 research. Re-check after Phase 1 design.*

| 原則 / 約束 | 本階段判定 | 說明 |
|-------------|-----------|------|
| I 組別為唯一單位 | ✅ 通過 | 上限與冷卻都以組別為單位；不涉及個別學生；搶答單位沿用 Step 7 |
| II 後端依送出時間仲裁 | ✅ 通過（關鍵） | 分配只依後端處理序 `seq` 與後端 `submitted_at`；**原始名次、時間、答案永不改寫**；讓位只改變「誰取得首選資格」並可由紀錄完整重現；確定性（同輸入同輸出）；無客戶端時間參與 |
| III 作答保密 | ✅ 通過（關鍵） | 分配、名次、獲勝題數、是否達上限只在老師路徑；學生結算前收不到任何分配資訊，結算後仍只收到各題獲勝組名＋答案；學生唯一得到的是「規則本身」（公開，憲章 IV 要求）；有學生訊息掃描測試 |
| IV 防壟斷與仲裁 | ✅ 通過（本步驟落實） | 實作「單一組別可獲勝題數上限，達上限後後續題目的順位遞補給次順位組別」；規則於活動開始前公開（等待搶答階段顯示）、建立後固定不可改；與 Step 9 的教師仲裁（駁回／恢復）並存且連動重算；**重開題目、指定獲勝組別仍未做**（FR-017） |
| V 回填與歷程 | ✅ 通過 | 回填與匯出共用同一份分配結果；CSV 新增「獲勝狀態／未獲勝原因」讓遞補歷程可核對 |
| VI PlantUML 設計優先 | ✅ 通過 | `diagrams/` 已於 specify 階段加入 `FairnessRule`、`EffectiveResult` 狀態、公平規則元件與建立房間／結算時序並已產 PNG；實作後須再比對一次（見 quickstart） |
| 即時同步與斷線還原 | ✅ 通過 | 規則由 `joined`／`snapshot` 還原；結果由後端推導，重連自動一致 |
| 資料完整性（append-only） | ✅ 通過 | 分配為推導；不新增可覆寫資料；`Submission`／`ReviewRecord` 不修改 |
| 時間來源 | ✅ 通過 | 冷卻以後端 `submitted_at`（UTC）計算 |
| 學習單回填約束 | ✅ 通過 | 回填取得「保留」規則後不會出現無人取得的空格 |
| 隱私 | ✅ 通過 | 不新增任何個資 |
| 測試要求 | ✅ 通過 | 覆蓋 II（確定性、原始資料不變、處理序）、III（結算前無分配資訊）、IV（上限、讓位、連動、規則固定與公開） |
| 簡潔性 | ✅ 通過 | 無新依賴、無新儲存；分配集中在既有的 `effective.py`，下游全部自動沿用 |

**Post-Phase 1 重新檢查**：設計後仍全部通過，無需填寫 Complexity Tracking。

## Project Structure

### Documentation (this feature)

```text
specs/011-win-cap-cooldown/
├── plan.md
├── research.md
├── data-model.md
├── quickstart.md
├── contracts/
│   ├── rest-api.md
│   ├── websocket.md
│   └── csv-format.md
├── checklists/requirements.md
└── tasks.md             # 由 /speckit-tasks 產生
```

### Source Code (repository root)

```text
diagrams/                          # 已更新：FairnessRule、EffectiveResult 狀態、公平規則元件、建立房間／結算時序

backend/app/
├── models.py                      # 修改：FairnessRule、Room.fairness、fairness_public()、錯誤碼 FAIRNESS_INVALID
├── services/
│   ├── fairness.py                # 新增：validate_fairness(questions, raw) → FairnessRule（範圍驗證）
│   ├── effective.py               # 修改：新增 allocate()（資格判定、讓位、保留、題組計 N 題、冷卻）；
│   │                              #       effective_winners() 改回傳分配後的獲勝送出；其餘函式不變
│   ├── ranking.py                 # 修改：每筆 ranking 加 outcome；看板加 fairness（規則）
│   ├── export.py                  # 修改：追加「獲勝狀態」「未獲勝原因」兩欄
│   ├── review.py                  # 修改：publish_review 計算 changedUnits（審核前後獲勝者有變的其他單位）
│   └── rooms.py                   # 修改：create_room 收 fairness；snapshot 加 fairness
└── api/
    ├── rooms.py                   # 修改：CreateBody.fairness；建立回應加 fairness
    └── ws.py                      # 修改：joined 加 fairness（僅規則）

backend/tests/
├── test_fairness_create.py        # 新增：建立房間驗證、下發、固定不可改
├── test_fairness_allocation.py    # 新增：驗證效果情境、讓位順序、處理序、保留、題組、審核連動、向下相容
├── test_fairness_cooldown.py      # 新增：冷卻規則與時間來源
├── test_fairness_property.py      # 新增：100 組隨機序列對照參考實作、確定性、原始資料不變、規模
├── test_fairness_sync.py          # 新增：結果／看板／匯出／回填一致、保密（結算前無分配資訊）、changedUnits
└── （修改）test_export*.py、test_review_export.py   # 欄位數 11 → 13

frontend/src/
├── lib/api.ts                     # 修改：createRoom 帶 fairness；FairnessRule 型別；describeError 補 FAIRNESS_INVALID
├── components/FairnessEditor.tsx  # 新增：預覽頁的「每組最多搶得」與「冷卻秒數」輸入與即時檢查
├── components/RankingBoard.tsx    # 修改：每筆顯示 outcome 標籤；顯示規則與「x/上限」；列出連動影響的題目
├── pages/Home.tsx                 # 修改：預覽頁加入 FairnessEditor，確認建立時送出
├── pages/StudentJoin.tsx          # 修改：等待搶答階段顯示規則說明（joined.fairness）
└── pages/TeacherRoom.tsx          # 修改：保存 fairness、處理 changedUnits 並顯示提示
```

**Structure Decision**: 沿用前後端分離。圖中「公平規則」對應 `effective.allocate()` 與 `services/fairness.py`；
不新增端點，規則經既有的 `POST /api/rooms`、`joined`、`snapshot` 傳遞。學生協定只多一個唯讀的規則欄位。

## Complexity Tracking

無違反項目，不需填寫。
