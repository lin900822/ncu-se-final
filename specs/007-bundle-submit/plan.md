# Implementation Plan: 題組打包提交機制

**Branch**: `007-bundle-submit`（規格目錄；實際在目前分支開發） | **Date**: 2026-11-10 | **Spec**: [spec.md](./spec.md)

**Input**: Feature specification from `/specs/007-bundle-submit/spec.md`

## Summary

老師在 Step 3 的「預覽 → 確認建立」之間，把相鄰題目（如 Q3、Q4）綁成**題組**；`POST /api/rooms` 多帶 `bundles`，
後端驗證（≥2 題、相鄰、不重疊、題目存在）後隨房間保存，建立後固定。題組設定經建立回應、學生 `joined`、老師 `snapshot`
下發。學生端把題組成員畫在同一張卡片、只有一顆送出鈕；送出時發 `submit_bundle {bundleId, answers}`。

後端在**同一個無 await 區段**內做全有或全無的驗證、以「組別 × 題組 × 輪次」去重，然後為題組內**每一題各追加一筆**
`Submission`，這些紀錄共用同一個 `seq`、`submitted_at`、`rank`，並標上 `bundle_id`。名次計數改以「搶答單位」
（單題＝題目 id；題組＝題組 id）為鍵。因為仍是逐題紀錄、且同題組各題的 rank 相同：
- Step 5 進度板（`build_board`）逐題結果自然一致，領先題數自動以題數計（Clarification Q1）；
- Step 6 結果（`build_result`）不用改，題組內各題同一個第 1 名；
- 後續回填仍逐題對應 `cell`（原則 V）。

前端：預覽頁加入題組設定 UI；學生 `QuestionFields` 依「搶答單位」分卡；老師進度板與結果頁依題組把各題框在一起。
沿用 FastAPI + 記憶體儲存 + React/Vite，不新增服務或依賴。

## Technical Context

**Language/Version**: 後端 Python 3.12（uv）；前端 TypeScript、Node.js 22 LTS（沿用）

**Primary Dependencies**: 沿用 FastAPI、Pydantic、React 19、Vite、Tailwind v4；**不新增依賴**

**Storage**: 沿用僅記憶體。`Room` 新增 `bundles: list[QuestionBundle]` 與推得的 `bundle_of: dict[questionId, bundleId]`；
`Submission` 新增 `bundle_id: str | None`；`rank_counts` 鍵由 `(round, questionId)` 改為 `(round, unitId)`

**Testing**: pytest。重點：
(1) 建立房間的題組驗證：<2 題、不相鄰、重疊、不存在的題目、無試算表卻帶題組 → `BUNDLES_INVALID` 且不建房；合法時回應與 `joined`／`snapshot` 皆含相同 `bundles`；
(2) 全有或全無：任一題空白／超長、缺題、多帶非成員題目 → 整筆拒絕、`submissions` 長度不變、`next_seq` 不變；
(3) 單題 `submit` 指到題組成員 → `QUESTION_IN_BUNDLE`；
(4) 去重：同組連點、同組兩視窗併發 `submit_bundle` → 每題恰 1 筆，且所有成員紀錄來自同一次送出（同 seq）；
(5) 名次：兩組併發送出同題組 → 題組內各題名次相同且唯一不並列；與其他單題的名次互不影響；
(6) 保密：他組只收到 `{type:"bundle_hint", bundleId, round}`，不含組名、答案、數量、時間；
(7) 進度板／結果：題組各題 leader 相同；領先題數以題數計；`build_result` 各題同一 winner；
(8) 重連還原 `mySubmissions`、`submittedByOthers` 含題組成員；新一輪清空、題組設定不變

**Target Platform**: 本機/單機、單一 worker；現代桌面與手機瀏覽器

**Project Type**: web-application（frontend + backend）

**Performance Goals**: 題組送出後 2 秒內本組所有視窗整張卡片「已送出」（SC-004）；≤ 40 組、每組 ≤ 10 視窗、≤ 50 題，題組驗證與追加為 O(題組大小)

**Constraints**: 單一 worker、asyncio 單執行緒——全有或全無與去重靠「同步區段內不 await」保證（沿用 Step 4/5 做法）；
題組建立後不可修改；題目清單仍為扁平、不改 `Question`；本步驟不做遞補／仲裁／回填

**Scale/Scope**: 後端新增 `services/bundles.py`（驗證與查詢）、`submissions.submit_bundle()`、一則學生訊息與三則事件、
建立房間 API 多一欄；前端新增預覽頁題組設定、學生題組卡片、老師端與結果頁的題組框線

## Constitution Check

*GATE: Must pass before Phase 0 research. Re-check after Phase 1 design.*

| 原則 / 約束 | 本階段判定 | 說明 |
|-------------|-----------|------|
| I 組別為唯一單位；題目僅以題號管理 | ✅ 通過（需說明） | `Question` 不變：仍是依題號排序的扁平清單，不新增題型或父子欄位。題組是**房間層級的「送出單位設定」**（`Room.bundles` 記錄 questionId 清單），由老師選用、不要求題型分類；送出紀錄仍逐題保存。此解讀見 research D1；不需修訂原則 I |
| II 後端依送出時間仲裁 | ✅ 通過（關鍵） | 題組送出在同一無 await 區段取得單一 `seq`，名次以搶答單位計數；併發測試覆蓋「同組兩視窗」與「兩組同時」；客戶端時間不參與 |
| III 作答保密 | ✅ 通過（關鍵） | 三種受眾沿用 Step 4：同組＝各題答案；老師＝組別＋答案＋時間＋名次；他組＝匿名 `bundle_hint`（只含 bundleId、round）。題組設定本身不含任何作答內容，可給所有學生 |
| IV 防壟斷與仲裁 | ➖ 不適用（前置） | FR-021 明訂不做；領先題數以題數計（Clarification Q1），之後的上限可直接沿用 |
| V 回填與歷程 | ✅ 通過 | 每題答案各自一筆、對應原 `cell`（FR-020）；`bundle_id`＋共用 `seq` 可在歷程中還原「同一次送出」（FR-019）；僅追加 |
| VI PlantUML 設計優先 | ✅ 通過 | `diagrams/` 已於 specify 階段加入 QuestionBundle、題組設定元件、題組設定與送出時序，並已產 PNG；實作後須再比對一次（見 quickstart） |
| 即時同步與斷線還原 | ✅ 通過 | `joined`／`snapshot` 帶 `bundles`；已送出狀態由逐題紀錄還原 |
| 資料完整性（append-only） | ✅ 通過 | 只追加；題組驗證失敗時不寫入任何紀錄 |
| 時間來源 | ✅ 通過 | `submitted_at` 由後端產生，題組各題共用 |
| 學習單回填約束（題號數＝空格數） | ✅ 通過 | 題組不改變題目與空格對應 |
| 測試要求 | ✅ 通過 | 覆蓋 II（併發）、III（他組只收匿名提示）；V 以逐題對應測試 |
| 簡潔性 | ✅ 通過 | 不新增實體儲存表，不新增「題組送出」第二份紀錄；只多一個小服務檔 |

**Post-Phase 1 重新檢查**：設計後仍全部通過（見 data-model 與 contracts），無需填寫 Complexity Tracking。

## Project Structure

### Documentation (this feature)

```text
specs/007-bundle-submit/
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
diagrams/                          # 已更新：QuestionBundle、題組設定元件、題組設定／送出時序

backend/app/
├── models.py                      # 修改：QuestionBundle、bundle_public()、Room.bundles／bundle_of、
│                                  #       Submission.bundle_id、新錯誤碼（BUNDLES_INVALID 等）
├── services/
│   ├── bundles.py                 # 新增：validate_bundles(questions, raw) → list[QuestionBundle]；unit_of(room, qid)
│   ├── submissions.py             # 修改：submit_bundle()（全有或全無、去重、共用 seq/rank）；
│   │                              #       submit() 拒絕題組成員；rank_counts 改以 unitId；三種受眾的題組事件
│   ├── ranking.py                 # 修改：看板每題加 bundleId（排名邏輯不變）
│   └── rooms.py                   # 修改：create_room 收 bundles；snapshot 加 bundles、submissions 加 bundleId
├── api/rooms.py                   # 修改：CreateBody.bundles；回應加 bundles
└── api/ws.py                      # 修改：處理 submit_bundle；joined 加 bundles

backend/tests/
├── test_bundles_create.py         # 新增：題組驗證與建立／下發
├── test_bundle_submit.py          # 新增：全有或全無、去重、單題拒絕、新一輪
├── test_bundle_concurrency.py     # 新增：同組兩視窗、兩組同時（原則 II）
└── test_bundle_privacy.py         # 新增：他組只收匿名提示（原則 III）、看板／結果一致

frontend/src/
├── lib/api.ts                     # 修改：BundleItem 型別；createRoom 帶 bundles
├── lib/questions.ts               # 修改：groupByUnit()（依題組／單題分卡，維持題號順序）
├── pages/Home.tsx                 # 修改：預覽中選取相鄰題目設為／取消題組；重讀時清除
├── components/QuestionFields.tsx  # 修改：題組卡片、單一送出鈕、未填滿不可送、整卡已送出
├── pages/StudentJoin.tsx          # 修改：送 submit_bundle；處理 bundle_submitted、bundle_hint、錯誤
├── components/RankingBoard.tsx    # 修改：題組各題框在一起、只顯示一份名次清單
├── components/ResultBoard.tsx     # 修改：題組各題框在一起；無人送出顯示「本題組無人搶答」
└── pages/TeacherRoom.tsx          # 修改：保存 snapshot.bundles 並傳給看板／結果
```

**Structure Decision**: 沿用前後端分離。圖中「題組設定」對應 `services/bundles.py`；「提交服務」的題組分支為
`submissions.submit_bundle()`；不新增端點，建立房間沿用 `POST /api/rooms`，送出沿用學生 WebSocket。

## Complexity Tracking

無違反項目，不需填寫。
