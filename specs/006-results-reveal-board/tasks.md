# Tasks: 搶答結果公布看板

**Input**: `/specs/006-results-reveal-board/` 下的 plan.md、spec.md、research.md、data-model.md、contracts/、quickstart.md
**Prerequisites**: plan.md、spec.md（皆已備齊）；Step 1～5 已實作完成（現有 84 個後端測試通過）
**Tests**: 依 plan.md 的 Testing 與 Constitution（原則 III 不外洩）加入 pytest；真實畫面以 quickstart.md 手動驗證
**Format**: `- [ ] T### [P?] [Story?] 描述（含檔案路徑）`；`[P]` = 可平行（不同檔案、無未完成相依）

> 使用者故事對應：US1＝結束搶答後學生自動看到結果頁（P1）、US2＝結果頁在斷線／重整／晚加入時仍正確（P1）、US3＝公布前不外洩且新一輪回到作答（P1）、US4＝老師端確認結果（P2）

## Phase 1: Setup

- [X] T001 執行 `cd backend && uv run pytest` 與 `cd frontend && npx tsc -b`（於 `frontend/` 內 `nvm use`），確認 Step 1～5 基準全數通過後才開始；本步驟不新增任何依賴、不新增任何儲存欄位

---

## Phase 2: Foundational（阻擋所有故事的共用基礎）

**⚠️ 完成前不得開始任何使用者故事**

- [X] T002 新增 `backend/app/services/results.py`：`build_result(room) -> dict | None`。**僅當 `room.phase == "Ended"` 時**回傳 `{"round": room.round, "results": [...]}`，否則回傳 `None`；`results` 依 `room.questions` 順序、**每題一筆** `{"questionId": q.id, "winnerGroup": <str | None>, "answer": <str | None>}`，資料只取 `room.submissions` 中 `round == room.round` 且 `rank == 1` 的紀錄（`winnerGroup` 為該紀錄的 `group_name`、`answer` 為答案原文）；題目本輪無人送出時 `winnerGroup` 與 `answer` 皆為 `None`（`null`）。輸出**不得**包含其他組別的組名／答案、`rank`、`seq`、`submittedAt`、`board`、`leadTally`。不另存任何狀態。模組 docstring 註明：僅在結算後（Ended）可對學生公布，內容僅限各題第 1 名的組名與答案（原則 III）
- [X] T003 修改 `backend/app/realtime.py`：新增 `async broadcast_result(self, code: str, message: dict) -> None`，對該房間**所有學生連線**送出（走訪 `students` 中 `c == code` 的所有視窗，使用 `send_json_safe`）；docstring 明列「僅限結算後公布的結果（`round_result`，每題僅第 1 名組名＋答案）；嚴禁用於其他訊息」。`broadcast_to_students` 的禁令與註解**維持不變**；模組 docstring 補充一行說明結果公布只能經 `broadcast_result`（學生）與 `broadcast_to_teachers`（老師）

**Checkpoint**: 結果推導與專用廣播就緒；既有測試仍通過

---

## Phase 3: User Story 1 - 結束搶答後學生自動看到結果頁 (Priority: P1) 🎯 MVP

**Goal**: 老師結束搶答後，所有在線學生 2 秒內自動切到結果頁，逐題列出第一名組別與答案。

**Independent Test**: 數組在 Q1～Q5 各自送出後老師結束搶答，所有學生畫面自動顯示結果頁，Q1～Q5 各列第一名組別與答案，且與老師端看板一致。

### Tests for User Story 1

- [X] T004 [P] [US1] 新增 `backend/tests/test_results.py`（沿用 `conftest.py` 的 `make_started_room`、`join_student`、`use_sheet`，以及 `test_ranking_board.py` 的老師連線寫法）：(a) 第 1、2、3 組依序送出 Q1，第 3 組送 Q2，老師 `POST /api/rooms/{code}/phase/end` 後，**每個學生視窗**（含同組第二個視窗與他組）在 `phase_changed(Ended)` 之後收到 `{"type":"round_result","round":1,"results":[...]}`，`results` 長度等於題目數（6）且依題目順序；(b) Q1 的 `winnerGroup == "第 1 組"` 且 `answer` 為其答案，Q2 為第 3 組，其餘題目 `winnerGroup`、`answer` 皆為 `None`；(c) 每題結果與 `ranking.build_board(room)` 各題 `leader` 一致（FR-012、SC-002）；(d) 全部題目都無人送出時結束搶答，`results` 全為 `null` 項且不出錯；(e) 單題題組房間（`use_sheet("group.xlsx")` 或既有題組範例，題號如 `1-2`）結果的 `questionId` 沿用題組小題識別碼；(f) 老師重複呼叫 `phase/end`（`changed == False`）→ 學生不再收到第二則 `round_result`，`build_result` 結果不變；(g) 結束搶答瞬間競態：結束後再送出被 `PHASE_LOCKED` 拒絕，`round_result` 只含結束前已被接受的送出

### Implementation for User Story 1

- [X] T005 [US1] 修改 `backend/app/services/phase.py` 的 `end_answering`：在 `await _broadcast(room, change)` 之後，組 `message = {"type": "round_result", **results.build_result(room)}`（`build_result` 此時必非 `None`），依序 `await realtime.broadcast_result(room.code, message)`（全體學生）與 `await realtime.broadcast_to_teachers(room.code, message)`（老師）；僅在階段實際由 Answering 變為 Ended 時執行（既有的 `changed == False` 早退路徑**不得**送出）。使 T004 通過
- [X] T006 [P] [US1] 新增 `frontend/src/components/ResultBoard.tsx`：props 為 `result: { round: number; results: { questionId: string; winnerGroup: string | null; answer: string | null }[] }`、`questions: QuestionItem[]`、`myGroup: string`（型別於檔內宣告並 `export`）；(a) 標題「搶答結果」；(b) 依 `results` 順序每題一張卡片：題號（以 `questions.find(q => q.id === questionId)?.label ?? questionId`，含題組小題）、`winnerGroup` 以醒目樣式顯示、`answer` 以 `whitespace-pre-wrap` 原文顯示（保留換行並安全顯示，不使用 `dangerouslySetInnerHTML`）；(c) `winnerGroup === myGroup` 時該卡片加上「本組搶下」標記與強調底色；(d) `winnerGroup === null` 時顯示「本題無人搶答」；(e) 版面在手機寬度可用，沿用既有 Tailwind 樣式
- [X] T007 [US1] 修改 `frontend/src/pages/StudentJoin.tsx`（依 T006）：新增狀態 `result: ResultData | null`；`onMessage` 新增 `msg.type === 'round_result'` → `setResult({ round: msg.round, results: msg.results })`；`phase === 'joined'` 畫面中，當 `roomPhase === 'Ended' && result` 時改以 `<ResultBoard result={result} questions={questions} myGroup={joinedName} />` 取代 `QuestionFields`（保留上方房間代碼／組名／階段橫幅與「離開房間」）；`npx tsc -b` 通過

**Checkpoint**: US1 可獨立驗證（quickstart 情境 2～7、10）

---

## Phase 4: User Story 2 - 結果頁在斷線、重整與晚加入時仍正確 (Priority: P1)

**Goal**: 離線、重新整理、結束後才加入的學生，以及同組所有視窗，都看到同一份結果。

**Independent Test**: 結束搶答時某視窗離線，重連後立即顯示相同結果頁；重新整理與結束後新加入亦同。

### Tests for User Story 2

- [X] T008 [P] [US2] 新增 `backend/tests/test_results_rejoin.py`：(a) 結束搶答後，新視窗以同代碼同組名加入 → `joined["result"]` 等於先前公布的 `round_result` 內容（`round`、`results` 相同）；(b) 結束搶答時先關閉某學生視窗（離線），結束後重新加入 → `joined["result"]` 相同；(c) 全新組別在結束後才加入 → `joined["result"]` 相同且 `joined["phase"] == "Ended"`；(d) 同組兩個視窗在結束時皆收到相同 `round_result`（FR-009）；(e) 搶答前（Waiting）與搶答中（Answering）加入的 `joined["result"]` 為 `None`；(f) 老師連線的 `snapshot["room"]["result"]` 於 Ended 為相同結構、於其他階段為 `None`；以恢復碼換裝置後的 `snapshot` 亦相同（FR-013）

### Implementation for User Story 2

- [X] T009 [US2] 修改 `backend/app/api/ws.py` 學生加入段落的 `joined` 訊息：新增 `"result": results.build_result(room) if room.status == "Open" else None`（`build_result` 僅 Ended 階段回非 `None`）；於檔案頂端匯入 `results`（`from ..services import groups, ranking, results, rooms, submissions`）。修改 `backend/app/services/rooms.py` 的 `snapshot()`：`room` 區塊新增 `"result": results.build_result(room)`（並匯入 `results`，注意避免循環匯入：`results.py` 只可匯入 `..models`）。使 T008 通過
- [X] T010 [US2] 修改 `frontend/src/pages/StudentJoin.tsx`：`joined` 處理中新增 `setResult((msg.result as ResultData | null) ?? null)`（須在 `applyPhase` 之後設定，避免被輪次邏輯覆蓋）；`resetLocal()` 一併 `setResult(null)`；重新整理或重連後 `joined.result` 即還原結果頁；`room_closed` 時清除結果。`npx tsc -b` 通過

**Checkpoint**: US1 + US2 可獨立驗證（quickstart 情境 8、9）

---

## Phase 5: User Story 3 - 公布前不外洩、新一輪回到作答 (Priority: P1)

**Goal**: 結算前學生協定完全沒有結果；公布後只含各題第 1 名；新一輪開始後離開結果頁。

**Independent Test**: 搶答中檢視學生端所有資料找不到結果；結束後只出現第 1 名；再次開始搶答後結果頁消失。

### Tests for User Story 3

- [X] T011 [P] [US3] 新增 `backend/tests/test_results_privacy.py`（沿用 `test_submission_privacy.py` 的 `flush`、`dumps` 技巧）：甲組（兩視窗）、乙組、丙組，甲先送 Q1、乙再送 Q1、丙送 Q2：(a) **公布前**（Answering）蒐集各學生連線全部訊息，序列化後不含 `round_result`、`winnerGroup`；`joined["result"]` 為 `None`；(b) **公布後**蒐集 `round_result`：乙組（Q1 非第一名）的組名「乙組」與其答案**不得**出現在丙組收到的內容中，甲組收到的內容亦不含乙組的答案與組名；Q1 只含「甲組」與甲的答案；(c) 公布後所有學生訊息仍不含 `"rank"`、`"seq"`、`"board"`、`"leader"`、`"leadTally"`、`"ranking"`、`"submittedCount"`、`"submittedAt"`；(d) `round_result` 的鍵集合為 `type, round, results`，每筆 `results` 鍵集合為 `questionId, winnerGroup, answer`；(e) 新一輪開始（再按 `phase/start`）後：學生收到 `phase_changed(Answering)`，新加入視窗 `joined["result"]` 為 `None`，且 `room.submissions` 保留舊輪紀錄；(f) 靜態掃描：讀取 `backend/app/` 原始碼，`broadcast_result(` 只出現在 `services/phase.py`，且 `results`／`round_result` 不出現在 `broadcast_to_students(`、`broadcast_to_group(`、`broadcast_to_other_groups(` 的呼叫附近（比照 Step 4、5 的作法）

### Implementation for User Story 3

- [X] T012 [US3] 修改 `frontend/src/pages/StudentJoin.tsx`：`phase_changed` 處理中，當 `msg.phase === 'Answering'` 時 `setResult(null)`（新一輪開始離開結果頁、回到作答畫面，FR-010）；確認畫面切換條件為 `roomPhase === 'Ended' && result`，使新一輪或等待階段不會顯示殘留結果；`npx tsc -b` 通過。後端無需新增邏輯（`build_result` 於非 Ended 回 `None`），本任務同時檢視 `backend/app/` 確認沒有任何學生路徑在公布前取用 `results`，若有洩漏則修正並使 T011 通過

**Checkpoint**: 三個 P1 故事皆可獨立驗證（quickstart 情境 1、11）

---

## Phase 6: User Story 4 - 老師端確認結果公布 (Priority: P2)

**Goal**: 老師端看到與學生端一致的最終結果，重整後仍可見。

**Independent Test**: 結束搶答後老師端顯示最終結果，與學生端結果頁逐題一致；重整後仍顯示。

### Tests for User Story 4

- [X] T013 [P] [US4] 於 `backend/tests/test_results.py` 追加：老師 WebSocket 在結束搶答後收到 `round_result`，內容與學生收到的**完全相同**（`==`）；其 `results` 各題與老師 `board` 的 `leader`／第 1 名答案一致；老師重新連線的 `snapshot.room.result` 與該 `round_result` 相同（FR-013）。此任務與 T004 同檔，須在 T004 之後進行

### Implementation for User Story 4

- [X] T014 [US4] 修改 `frontend/src/pages/TeacherRoom.tsx`：新增狀態 `result`；`snapshot` 事件由 `room.result` 設定（型別補 `result?: ResultData | null`）；新增 `case 'round_result'` 設定 `result`；`phase_changed` 為 `Answering` 時清除；將「即時進度板」區塊標題改為：`roomPhase === 'Ended' ? '最終結果' : '即時進度板'`，且已結束階段於進度板上方以簡短清單顯示 `result`（每題：題號、第一名組別、答案，無人搶答顯示「本題無人搶答」）。沿用既有 `RankingBoard`，不新增獨立頁面；`ResultData` 型別自 `ResultBoard.tsx` 匯入。`npx tsc -b` 通過

**Checkpoint**: 四個故事皆可驗證

---

## Phase 7: Polish & Cross-Cutting Concerns

- [X] T015 [P] 修改 `diagrams/sequence.puml`、`diagrams/component.puml`、`diagrams/class.puml`（僅在實作與圖不一致時才改）：確認「結算於 end_answering 之後以 `round_result` 公布給全體學生與老師」「結果由 rank=1 推導、僅 Ended 階段」「`joined.result` 還原」「新一輪離開結果頁」皆與程式一致；執行 `plantuml -tpng diagrams/*.puml` 重新產圖（Constitution VI 實作後驗證）
- [X] T016 [P] 更新 `README.md`（若有功能清單）與 `specs/006-results-reveal-board/quickstart.md`：補上結果公布的說明並確認與實作一致
- [X] T017 執行完整驗證：`cd backend && uv run pytest`（全數通過，含 Step 1～5 既有測試）、`cd frontend && npx tsc -b`；依 `quickstart.md` 手動驗證情境 1～11 逐項走一遍，特別是「老師按結束搶答後所有學生畫面自動切換至結果頁並列出各題第一名與答案」、「公布前學生資料找不到結果」、「結果頁看不到非第一名組別的答案」

---

## Dependencies & Execution Order

### Phase Dependencies

- **Setup (P1)** → **Foundational (P2)** → 使用者故事 → **Polish (P7)**
- US1 為 MVP；US2、US3、US4 皆建立在 T002、T003、T005 之上
- 前端同檔任務須依序：`StudentJoin.tsx`（T007 → T010 → T012）；`TeacherRoom.tsx`（T014）
- 後端同檔任務須依序：`phase.py`（T005）；`ws.py` 與 `rooms.py`（T009）；`test_results.py`（T004 → T013）

### Within Each Story

- 測試任務（T004、T008、T011、T013）可先寫、先看到失敗
- T002、T003 → T005 → T009；T006 → T007 → T010 → T012；T014 依 T006（匯入 `ResultData` 型別）

### Parallel Opportunities

- T002 與 T003 可平行（不同檔案）
- US1 內：T004（測試）與 T006（前端元件）可平行
- T008、T011 可與 T006 平行（不同檔案）；T015、T016 可平行

## Parallel Example: User Story 1

```bash
# 可同時進行（不同檔案）：
Task: "T004 新增 backend/tests/test_results.py"
Task: "T006 新增 frontend/src/components/ResultBoard.tsx"
# 之後依序：T005（後端，依 T002、T003）；T007（前端，依 T006）
```

## Implementation Strategy

### MVP First（User Story 1）

1. 完成 Phase 1、2（結果推導與專用廣播）
2. 完成 Phase 3（US1）：結束搶答→全體學生自動切換結果頁
3. **停下驗證**：quickstart 情境 2～7，結果頁與老師看板一致即達成本步驟指定的驗證效果

### Incremental Delivery

1. Setup + Foundational → 結果推導就緒
2. US1 → 即時公布（MVP）
3. US2 → 斷線／重整／晚加入還原
4. US3 → 保密驗證與新一輪離開結果頁
5. US4 → 老師端最終結果
6. Polish → 圖表一致性與完整驗證

---

## Notes

- 本步驟**不**做防壟斷遞補、老師仲裁、計分或回填試算表（FR-014）；結果由單一函式 `build_result` 從名次 1 推導，後續步驟只需改此函式
- 結果只公布各題第 1 名的組名與答案；名次、看板、領先題數仍僅老師可見（Step 5 不變）
- 新依賴：無；新儲存欄位：無
- Commit 建議：每完成一個使用者故事 phase 提交一次
