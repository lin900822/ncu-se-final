# Tasks: 組別答案提交與防重複送出

**Input**: `/specs/004-group-answer-submit/` 下的 plan.md、spec.md、research.md、data-model.md、contracts/、quickstart.md
**Prerequisites**: plan.md、spec.md（皆已備齊）；Step 1～3 已實作完成（現有 52 個測試通過）
**Tests**: 依 plan.md 的 Testing 與 Constitution（原則 II 並發、原則 III 不外洩）加入 pytest；真實畫面以 quickstart.md 手動驗證
**Format**: `- [ ] T### [P?] [Story?] 描述（含檔案路徑）`；`[P]` = 可平行（不同檔案、無未完成相依）

> 使用者故事對應：US1＝學生送出某題並看到「已送出」（P1）、US2＝同組其他視窗同步（P1）、US3＝其他組別看不到該組答案（P1）、US4＝老師查看送出狀況（P2）

## Phase 1: Setup

- [X] T001 執行 `cd backend && uv run pytest` 與 `cd frontend && npx tsc -b`（於 `frontend/` 內 `nvm use`），確認 Step 1～3 基準全數通過後才開始；本步驟不新增任何依賴

---

## Phase 2: Foundational（阻擋所有故事的共用基礎）

**⚠️ 完成前不得開始任何使用者故事**

- [X] T002 修改 `backend/app/models.py`：新增 dataclass `Submission`（`group_name: str`、`normalized_name: str`、`question_id: str`、`round: int`、`answer: str` 為「非空白且 ≤ 500 字元」、`submitted_at: datetime` 由後端 UTC 產生）；`Room` 新增 `submissions: list[Submission]`（僅追加，預設空 list）與 `submission_index: dict[tuple[int, str, str], Submission]`（鍵為 `(round, normalized_name, question_id)`，由 `submissions` 推得）；`_ERRORS` 新增 `GROUP_WINDOWS_FULL` 409「該組視窗數已達上限（10）」、`QUESTION_NOT_FOUND` 400「找不到該題」、`ANSWER_EMPTY` 400「請填寫答案」、`ANSWER_TOO_LONG` 400「答案最多 500 字元」，並**移除** `GROUP_ONLINE`
- [X] T003 修改 `backend/app/realtime.py`：`students` 由 `dict[(code, name)] -> WebSocket` 改為 `dict[(code, name)] -> set[WebSocket]`；新增 `add_student(code, name, ws)`、`remove_student(code, name, ws) -> int`（回傳該組剩餘視窗數，為 0 時移除該鍵）、`window_count(code, name) -> int`、`async broadcast_to_group(code, name, message)`（同組所有視窗）、`async broadcast_to_other_groups(code, exclude_name, message)`（同房間除指定組外的所有視窗）；更新 `broadcast_to_students`、`has_connections`、`close_room_connections` 以走訪集合；移除 `set_student` 與 `student_is`。在各方法 docstring 註明：答案內容只能經 `broadcast_to_group` 與 `broadcast_to_teachers` 傳送，`broadcast_to_students` 與 `broadcast_to_other_groups` 嚴禁傳入答案、組名、草稿、組數或時間（原則 III）
- [X] T004 修改 `backend/app/services/groups.py`（依 T002、T003）：`join` 移除 `GROUP_ONLINE` 拒絕；若 `window_count >= 10`（每組視窗「≤ 10」）拋 `GROUP_WINDOWS_FULL`；以 `add_student` 登記；回傳值新增 `was_online`；`announce_join` 僅在「新組別」（`group_joined`）或「由離線轉在線」（`group_status` online=true）時通知老師，同組多出的視窗不重複通知；`disconnect(room, group, ws)` 改為 `remove_student(...)`，**僅當剩餘視窗數為 0** 才設 `group.online = False` 並通知老師離線
- [X] T005 修改 `backend/app/api/ws.py` 的學生加入段落：配合 T004 的新回傳值（`was_online`），其餘行為不變；本任務只調整簽章與呼叫，不加入提交邏輯。確認 `cd backend && uv run pytest` 仍全數通過（既有測試沒有依賴 `GROUP_ONLINE`）

**Checkpoint**: 同組可多視窗加入且在線判定正確；既有測試全數通過

---

## Phase 3: User Story 1 - 學生送出某題答案並看到「已送出」 (Priority: P1) 🎯 MVP

**Goal**: 搶答中學生按某題「送出」，該題變「已送出」並鎖定；重複與無效送出被擋下。

**Independent Test**: 老師開始搶答後，學生在 Q1 輸入並送出，Q1 顯示「已送出」且鎖定，Q2 仍可輸入；連點只留一筆。

### Tests for User Story 1

- [X] T006 [P] [US1] 新增 `backend/tests/test_submissions.py`：沿用 `conftest.py` 與 `test_questions_api.py` 的 `use_sheet` 技巧建立含題目的房間並開始搶答。(a) 成功送出：該組視窗收到 `{"type":"submitted","questionId","answer","round"}`，`room.submissions` 恰一筆，`submitted_at` 有值；(b) 空字串與僅空白 → `ANSWER_EMPTY`，題目不存在 → `QUESTION_NOT_FOUND`，501 字元 → `ANSWER_TOO_LONG`，500 字元成功；錯誤皆附 `questionId` 且連線不關閉；(c) 搶答未開始、已結束 → `PHASE_LOCKED` 且 `submissions` 不增加；(d) 同組同題連續送出 10 次 → 只有 1 筆紀錄，重複的 9 次都只收到既有答案的 `submitted`；(e) 客戶端在訊息中夾帶 `submittedAt` 為 1999 年，紀錄時間仍為伺服器現在時間（原則 II）；(f) 結束搶答後立刻送出被拒絕，再開始新一輪後可重新送出且舊紀錄仍在 `room.submissions`（`round` 不同）；(g) 以 `asyncio.gather` 並發呼叫 `services.submissions.submit` 10 次（同組同題）→ 恰 1 筆 created、其餘為重複

### Implementation for User Story 1

- [X] T007 [US1] 新增 `backend/app/services/submissions.py`：`submit(room, group, question_id, answer) -> tuple[Submission, bool]`（回傳 `(紀錄, 是否新建)`）。**在無 `await` 的同步區段內**依序：房間 `Open` 且 `phase == "Answering"`（否則 `PHASE_LOCKED`）→ 題目存在於 `room.questions`（否則 `QUESTION_NOT_FOUND`）→ 答案去除空白後非空（否則 `ANSWER_EMPTY`）→ 原字串長度 ≤ 500（否則 `ANSWER_TOO_LONG`）→ 查 `submission_index[(room.round, group.normalized_name, question_id)]`，已存在則回傳既有紀錄與 `False` → 否則以 `utcnow()` 建立 `Submission`（答案保存原文）、追加到 `submissions` 並寫入索引後回傳 `True`；並呼叫 `rooms.touch(room)`
- [X] T008 [US1] 修改 `backend/app/api/ws.py` 的學生 `submit` 處理：解析 `{"type":"submit","questionId","answer"}`，呼叫 `submissions.submit`；錯誤以 `{"type":"error","code","message","questionId"}` 只回發送者且不關閉連線；新建成功時 `await` 扇出：`broadcast_to_group` 送 `submitted`（含發送者）、`broadcast_to_teachers` 送 `{"type":"submission","group","questionId","answer","round","submittedAt"}`、`broadcast_to_other_groups` 送 `{"type":"question_submitted","questionId","round"}`（**只含這三個鍵**）；重複送出只對發送者回送既有答案的 `submitted`，不扇出；使 T006 全數通過
- [X] T009 [P] [US1] 修改 `frontend/src/components/QuestionFields.tsx`：新增選填 props `submitted?: Record<string,string>`（已送出的 `{題目識別碼: 答案}`）、`onSubmit?: (id: string) => void`、`errors?: Record<string,string>`；每題在輸入框旁顯示「送出」按鈕（`disabled` 時、答案為空白時停用）；題目已在 `submitted` 中時改顯示「已送出」標記並以唯讀顯示該答案（輸入框鎖定，內容取自 `submitted[id]`）；`errors[id]` 有值時於該題下方顯示錯誤文字
- [X] T010 [US1] 修改 `frontend/src/pages/StudentJoin.tsx`（依 T009）：從 `useReconnectingSocket` 取得 `send`；新增狀態 `submitted: Record<string,string>` 與 `errors: Record<string,string>`；點「送出」時 `send({type:'submit', questionId, answer: values[id]})`，**不做樂觀更新**，只在收到 `submitted` 事件才把該題記入 `submitted` 並把 `values[id]` 設為伺服器回傳的答案、清除該題錯誤；收到 `error` 且帶 `questionId` 時寫入 `errors[questionId]`（`PHASE_LOCKED`、`ANSWER_EMPTY`、`ANSWER_TOO_LONG`、`QUESTION_NOT_FOUND` 的訊息）；`applyPhase` 在 `round` 增加時一併清空 `submitted` 與 `errors`；連線非 open 時送出按鈕停用

**Checkpoint**: US1 可獨立驗證（quickstart 情境 1、6、8、9）

---

## Phase 4: User Story 2 - 同組其他視窗同步顯示已送出 (Priority: P1)

**Goal**: 同組多視窗即時同步已送出的狀態與內容；加入與重連時由後端還原。

**Independent Test**: 第 1 組開視窗 A、B，A 送出 Q1，B 在 2 秒內顯示「已送出」與相同內容；B 重新整理後仍顯示。

### Tests for User Story 2

- [X] T011 [P] [US2] 新增 `backend/tests/test_multiwindow.py`：(a) 同組第二個視窗加入成功（`rejoined` 為 true、沒有任何拒絕），老師端只有一筆該組；(b) 第一個視窗送出 Q1，第二個視窗收到 `submitted` 且內容相同；(c) 兩個視窗對 Q2 先後送出不同內容 → 只留第一筆，第二個視窗收到的 `submitted` 內容為第一筆；(d) 第 11 個視窗被拒絕 `GROUP_WINDOWS_FULL`，原有視窗不受影響；(e) 關閉其中一個視窗後組別仍在線（老師端沒有離線事件），關閉最後一個視窗才收到 `group_status` online=false；第二個視窗加入時老師端不重複收到 `group_status`；(f) 重新加入（同組新視窗）的 `joined.mySubmissions` 含本輪已送出的內容；離線期間另一視窗送出，重連後 `mySubmissions` 含該筆；(g) 新一輪開始後 `joined.mySubmissions == {}`

### Implementation for User Story 2

- [X] T012 [US2] 修改 `backend/app/services/submissions.py` 與 `backend/app/api/ws.py`：新增 `my_submissions(room, group) -> dict[str,str]`（該組**本輪**的 `{questionId: answer}`）與 `submitted_by_others(room, group) -> list[str]`（本輪有**其他組**送出的題目識別碼，去重、依題目順序，只含識別碼）；學生 `joined` 新增 `"mySubmissions"` 與 `"submittedByOthers"`。使 T011 全數通過
- [X] T013 [US2] 修改 `frontend/src/pages/StudentJoin.tsx`：`joined` 時以 `msg.mySubmissions` 設定 `submitted`（並把對應題目的 `values` 設為該答案，且優先於草稿）、以 `msg.submittedByOthers` 設定 `othersSubmitted: string[]`（本任務先存狀態，顯示在 US3）；收到 `submitted` 事件時更新同上；`applyPhase` 在 `round` 增加時清空 `submitted`、`othersSubmitted`、`errors`；**刪除** Step 1 針對 `GROUP_ONLINE` 的自動重試邏輯與相關常數（`RETRY_INTERVAL_MS`、`MAX_AUTO_RETRIES`、`retries`），並處理新錯誤碼 `GROUP_WINDOWS_FULL`（顯示於加入表單的錯誤訊息，不自動重試）

**Checkpoint**: US1 + US2 可獨立運作（quickstart 情境 2、7、10、12）

---

## Phase 5: User Story 3 - 其他組別看不到該組的答案 (Priority: P1)

**Goal**: 他組在畫面與收到的所有資料中都看不到該組答案；只看到匿名提示。

**Independent Test**: 第 1 組送出 Q1「CPU」，第 2 組視窗的畫面與所有 WebSocket 訊息都找不到「CPU」與「第 1 組」，只出現「本題已有組別送出」。

### Tests for User Story 3

- [X] T014 [P] [US3] 新增 `backend/tests/test_submission_privacy.py`（原則 III）：第 1 組送出含獨特字串的答案（如「獨特答案ZZ」），第 2 組有一個視窗。(a) 收集第 2 組視窗從加入到送出前後收到的**所有**訊息，序列化後不含該答案、不含「第 1 組」；(b) 第 2 組收到的提示訊息鍵集合**恰為** `{"type","questionId","round"}`（不含時間、組數、答案、組名）；(c) 第 2 組重新加入時 `joined` 的 `mySubmissions == {}`，`submittedByOthers` 為只含題目識別碼的清單，序列化後不含答案與組名；(d) 第 1 組尚未送出、只在輸入時，第 2 組收到的訊息為 0 則新增（草稿不外送）；(e) 第 1 組的同組視窗與老師**有**收到答案（對照組，確認不是整體都沒送）；(f) 掃描 `backend/app` 中所有呼叫 `broadcast_to_students` 與 `broadcast_to_other_groups` 的位置，確認只傳入階段、題目文字或匿名提示（以讀取原始碼字串的測試或審查清單方式驗證）

### Implementation for User Story 3

- [X] T015 [US3] 修改 `frontend/src/components/QuestionFields.tsx` 與 `frontend/src/pages/StudentJoin.tsx`：`QuestionFields` 新增選填 props `othersSubmitted?: string[]`，題目在其中且自己組尚未送出時，於該題顯示「本題已有組別送出」提示（不影響輸入與送出）；`StudentJoin` 處理 `question_submitted` 事件時，把 `questionId` 加入 `othersSubmitted`（忽略 `round` 小於目前輪次的事件），並傳入 `QuestionFields`
- [X] T016 [US3] 審查 `backend/app/services/submissions.py` 與 `backend/app/api/ws.py` 的所有廣播呼叫：答案內容只經 `broadcast_to_group` 與 `broadcast_to_teachers`，他組只經 `broadcast_to_other_groups` 送 `{type, questionId, round}`；補上註解說明此保密約束（原則 III）。使 T014 全數通過

**Checkpoint**: US1～US3 可獨立運作（quickstart 情境 3、4、13）

---

## Phase 6: User Story 4 - 老師查看各組送出狀況與內容 (Priority: P2)

**Goal**: 老師端即時看到各組各題的送出、內容與伺服器時間；重新整理後還原。

**Independent Test**: 學生送出 Q1 後，老師端 2 秒內出現「第 1 組：Q1＝內容＋時間」；重新整理仍在。

### Tests for User Story 4

- [X] T017 [P] [US4] 於 `backend/tests/test_submissions.py` 新增測試：(a) 老師 WebSocket 在學生送出後收到 `submission`，鍵集合為 `{"type","group","questionId","answer","round","submittedAt"}`，`submittedAt` 為伺服器 UTC（`...Z` 格式）；(b) 老師 `snapshot.room.submissions` 含所有輪次、依接受順序，每筆含 `group`、`questionId`、`answer`、`round`、`submittedAt`；(c) 以恢復碼 `recover` 後連線，`snapshot.room.submissions` 與先前相同；(d) 新一輪開始後，舊輪次的紀錄仍在 `snapshot.room.submissions` 且 `round` 不同

### Implementation for User Story 4

- [X] T018 [US4] 修改 `backend/app/services/rooms.py` 的 `snapshot(room)`：`room` 欄位新增 `"submissions"`，為 `room.submissions` 依序轉成 `{"group","questionId","answer","round","submittedAt": iso(submitted_at)}`。使 T017 全數通過
- [X] T019 [US4] 修改 `frontend/src/pages/TeacherRoom.tsx`：新增狀態 `submissions`（`snapshot.room.submissions` 還原、收到 `submission` 事件時追加）；新增「本輪送出」區塊，只顯示 `round === 目前輪次` 的紀錄，列出組別、題號（以 `questions` 對照 `id → label`）、答案內容與送出時間（本地時間格式）；無紀錄時顯示「尚無組別送出」；舊輪次紀錄不顯示於此區塊（仍保留於後端）

**Checkpoint**: 全部使用者故事可獨立運作

---

## Phase 7: Polish & Cross-Cutting

- [X] T020 執行 `cd backend && uv run pytest`，確認新舊測試全數通過；執行 `cd frontend && npx tsc -b && npm run build`（需 Node 22）
- [X] T021 [P] 更新文件：`README.md` 補充「同組可多視窗」與答案送出說明；在 `specs/001-room-join/quickstart.md` 的「以相同組名加入被拒絕」情境加註「Step 4 起改為允許同組多視窗」
- [X] T022 [P] 圖表一致性檢查（Constitution VI）：比對 `diagrams/class.puml`、`component.puml`、`sequence.puml` 與程式（`Submission`、提交服務、防重複、三種扇出、同組多視窗）；不一致時修正程式或更新圖表，並執行 `cd diagrams && plantuml -tpng *.puml`
- [X] T023 [P] 保密與日誌檢查：`grep -rn "answer" backend/app` 確認答案內容沒有被寫入任何 `print`、`logging` 或例外訊息；確認 `broadcast_to_students`、`broadcast_to_other_groups` 的所有呼叫點符合 T016 的約束
- [ ] T024 依 `specs/004-group-answer-submit/quickstart.md` 以真實試算表與多個瀏覽器視窗手動執行情境 1～13

---

## Dependencies & Execution Order

- Phase 1 → Phase 2 → 使用者故事 → Polish。
- Phase 2 內：T002 → T003 → T004 → T005（`groups.py` 與 `ws.py` 依賴 `realtime.py` 的新介面，須循序）。
- US1：測試 T006 先寫；T007 → T008（服務 → 路由）；前端 T009 可與 T007 平行，T010 依 T009。
- US2 依賴 US1 的提交流程：T011 → T012 → T013；T013 與 US1 的 T010 同檔須循序。
- US3 依賴 US1、US2（需有提示事件與還原）：T014 → T015／T016（T015 前端、T016 後端審查可平行）。
- US4 依賴 US1：T017 → T018 → T019。
- **同檔案須循序**：`backend/app/api/ws.py`：T005 → T008 → T012；`backend/app/services/submissions.py`：T007 → T012；`frontend/src/pages/StudentJoin.tsx`：T010 → T013 → T015；`frontend/src/components/QuestionFields.tsx`：T009 → T015；`frontend/src/pages/TeacherRoom.tsx`：T019；`backend/tests/test_submissions.py`：T006 → T017。

## Parallel Examples

- US1：T006（測試）與 T009（前端元件）可同時進行。
- US2：T011（測試）可與 T009 之外的前端工作並行。
- US3：T015（前端）與 T016（後端審查）。
- Polish：T021、T022、T023 可平行。

## Implementation Strategy

- **MVP**：Phase 1–3（US1）即可驗證「送出後該題變為已送出、連點不重複」，但完整驗證效果（同組同步、他組不外洩）需 US1～US3。
- **增量交付**：Phase 2 完成後依 US1 → US2 → US3 → US4 逐一完成並以各自 Independent Test 驗證；每個故事結束跑 `uv run pytest`。
- **風險最高的兩處**：Phase 2 的連線登記重構（影響 Step 1 的加入邏輯，先確保既有 52 個測試仍通過）與 T007 的同步區段原子性（並發測試 T006(g)）。
- 實作過程中不得把答案內容寫入日誌或任何他組可見的訊息。
