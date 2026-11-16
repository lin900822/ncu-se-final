# Tasks: 題組打包提交機制

**Input**: `/specs/007-bundle-submit/` 下的 plan.md、spec.md、research.md、data-model.md、contracts/、quickstart.md
**Prerequisites**: plan.md、spec.md（皆已備齊）；Step 1～6 已實作完成
**Tests**: 依 plan.md 的 Testing 與 Constitution（原則 II 併發、III 不外洩須有自動化測試）加入 pytest；真實畫面以 quickstart.md 手動驗證
**Format**: `- [ ] T### [P?] [Story?] 描述（含檔案路徑）`；`[P]` = 可平行（不同檔案、無未完成相依）

> 使用者故事對應：US1＝老師建立房間時把多題綁成題組（P1）、US2＝學生在同一張卡片內填完整個題組並一次送出（P1）、US3＝同組多視窗同步與他組保密（P1）、US4＝老師端進度板與結果頁以題組為單位呈現（P2）
>
> 用語：**題組**＝老師綁定、須一起送出的相鄰題目（`QuestionBundle`，id 如 `B1`）；**搶答單位（unitId）**＝題目所屬題組 id，未綁定時為題目 id。與 Step 3 的「題組小題」（`1-2`）不同。

## Phase 1: Setup

- [X] T001 執行 `cd backend && uv run pytest` 與 `cd frontend && npx tsc -b`（於 `frontend/` 內 `nvm use`），確認 Step 1～6 基準全數通過後才開始；記下目前通過的測試數。本步驟不新增任何依賴

---

## Phase 2: Foundational（阻擋所有故事的共用基礎）

**⚠️ 完成前不得開始任何使用者故事**

- [X] T002 修改 `backend/app/models.py`：(a) 新增 `@dataclass QuestionBundle`：`id: str`（如 `"B1"`）、`question_ids: list[str]`（依題目順序，≥ 2 題）；(b) 新增 `bundle_public(b) -> dict` 回傳 `{"id": b.id, "questionIds": list(b.question_ids)}`（不含任何作答內容）；(c) `Room` 新增 `bundles: list[QuestionBundle] = field(default_factory=list)` 與 `bundle_of: dict[str, str] = field(default_factory=dict)`（questionId → bundleId，由 `bundles` 推得）；(d) `Submission` 新增欄位 `bundle_id: str | None = None`（放在既有欄位之後以保持既有建構呼叫相容），docstring 補充「題組送出時，每個成員各一筆，共用 seq／submitted_at／rank」；(e) `Room.rank_counts` 註解改為「鍵為 (round, unitId)；unitId＝題目所屬題組 id，未綁定為題目 id」；(f) `_ERRORS` 新增 `"BUNDLES_INVALID": ("題組設定有誤", 400)`、`"BUNDLE_NOT_FOUND": ("找不到該題組", 400)`、`"BUNDLE_INCOMPLETE": ("請填完題組內所有題目", 400)`、`"QUESTION_IN_BUNDLE": ("此題屬於題組，請整組一起送出", 400)`。`Question` **不得修改**（原則 I，research D1）
- [X] T003 新增 `backend/app/services/bundles.py`（只匯入 `..models`，避免循環匯入）：(a) `validate_bundles(questions: list[Question], raw: list[list[str]] | None) -> list[QuestionBundle]`：`raw` 為 `None` 或 `[]` 回傳 `[]`；`questions` 為空而 `raw` 非空 → `err("BUNDLES_INVALID", {"reason": "NO_QUESTIONS", "questionIds": []})`；以 `questions` 的清單順序（Step 3 已依題號、小題編號排序）建立 `index = {q.id: i}`；逐組檢查並在第一個錯誤時丟出 `BUNDLES_INVALID`，`details = {"reason": ..., "questionIds": [...]}`：成員不在 `index` → `UNKNOWN_QUESTION`；同組內重複或與先前題組重疊 → `OVERLAP`；去重後少於 2 題 → `TOO_FEW`；成員索引排序後不連續（`max - min + 1 != len`）→ `NOT_ADJACENT`；(b) 通過後每組依題目順序排序成員，再依第一個成員的索引排序所有題組，依序命名 `B1`、`B2`…，回傳 `QuestionBundle` 清單；(c) `index_bundles(bundles) -> dict[str, str]` 產生 `bundle_of`；(d) `unit_of(room, question_id) -> str` 回傳 `room.bundle_of.get(question_id, question_id)`；(e) `get_bundle(room, bundle_id) -> QuestionBundle | None`
- [X] T004 修改 `backend/app/services/rooms.py` 的 `create_room(sheet=None, bundles=None)`：有 `sheet` 時在設定 `room.questions` 之後設定 `room.bundles = bundles or []`、`room.bundle_of = bundles_service.index_bundles(room.bundles)`；`snapshot()` 的 `room` 新增 `"bundles": [bundle_public(b) for b in room.bundles]`，`submissions` 每筆新增 `"bundleId": s.bundle_id`
- [X] T005 修改 `backend/app/api/rooms.py`：`CreateBody` 新增 `bundles: list[list[str]] | None = None`；`create_room` 中**在指紋比對通過之後、建立房間之前**呼叫 `bundles.validate_bundles(sheet.questions, body.bundles)`；沒有 `sheetUrl` 卻帶非空 `bundles` → `err("BUNDLES_INVALID", {"reason": "NO_QUESTIONS", "questionIds": []})`；任何錯誤都不建立房間；回應新增 `"bundles": [bundle_public(b) for b in room.bundles]`（契約見 `contracts/rest-api.md`）
- [X] T006 修改 `backend/app/api/ws.py` 的學生 `joined` 訊息：新增 `"bundles": [bundle_public(b) for b in room.bundles]`（無題組為 `[]`）
- [X] T007 修改 `backend/app/services/submissions.py` 的 `submit()`：名次計數鍵改為 `rank_key = (room.round, bundles.unit_of(room, question_id))`（未綁定題目的行為與 Step 5 完全相同）。既有測試須仍全數通過
- [X] T008 [P] 修改 `backend/tests/conftest.py`：新增 `make_bundle_room(client, bundles=[["3", "4"]], start=True)`，與 `make_started_room` 相同流程但 `POST /api/rooms` 多帶 `"bundles": bundles`，斷言 201，回傳 `(code, token, body)`（`body` 為建立回應，含 `bundles`）
- [X] T009 [P] 修改 `frontend/src/lib/api.ts`：新增並 `export` 型別 `BundleItem = { id: string; questionIds: string[] }`；`createRoom` 的參數新增選填 `bundles?: string[][]` 並放進請求本文；建立回應型別新增 `bundles: BundleItem[]`
- [X] T010 [P] 修改 `frontend/src/lib/questions.ts`：新增 `export type AnswerUnit = { kind: 'bundle'; bundle: BundleItem; items: QuestionItem[] } | { kind: 'single'; number: number; items: QuestionItem[] }` 與 `groupByUnit(questions, bundles): AnswerUnit[]`：依題號、小題編號排序後走訪，屬於題組的題目合成一個 `bundle` 單位（放在第一個成員的位置，成員依題目順序），其餘題目沿用 `groupByNumber` 的「同題號合為一框」產生 `single` 單位；同時新增 `isAdjacent(questions, ids): boolean`（依排序後索引判斷是否連續），供預覽頁即時檢查。`groupByNumber` 保持不變

**Checkpoint**: 題組可隨房間建立、經 `joined`／`snapshot` 下發；既有測試仍通過；前端型別就緒

---

## Phase 3: User Story 1 - 老師建立房間時把多題綁成題組 (Priority: P1) 🎯 MVP

**Goal**: 老師在預覽中把相鄰題目綁成題組，確認建立後題組固定，老師端與學生端取得相同設定。

**Independent Test**: 老師預覽單題範例（Q1～Q6），把 Q3、Q4 設為題組後確認建立；老師端題目清單顯示「題組：Q3、Q4」，重新整理後不變。

### Tests for User Story 1

- [X] T011 [P] [US1] 新增 `backend/tests/test_bundles_create.py`（使用 `use_sheet`、`make_bundle_room`、`join_student`）：(a) `bundles=[["4","3"]]` 建立成功，回應 `bundles == [{"id":"B1","questionIds":["3","4"]}]`；(b) 兩個題組 `[["5","6"],["1","2"]]` 依第一題位置編號為 `B1=["1","2"]`、`B2=["5","6"]`；(c) 下列各情況回 400、`code == "BUNDLES_INVALID"`、`details.reason` 正確，且 `store.rooms` 數量不變：`[["3"]]`→`TOO_FEW`、`[["3","3"]]`→`OVERLAP`（或 `TOO_FEW`，以實作的檢查順序為準並固定於測試）、`[["2","5"]]`→`NOT_ADJACENT`、`[["3","4"],["4","5"]]`→`OVERLAP`、`[["3","99"]]`→`UNKNOWN_QUESTION`、不帶 `sheetUrl` 但帶 `[["1","2"]]`→`NO_QUESTIONS`；(d) 題組小題範例（`use_sheet` 切到 `group.xlsx`）中相鄰的 `["1-2","2-1"]` 可建立；(e) 學生 `joined.bundles` 與老師 `snapshot.room.bundles` 都等於建立回應的 `bundles`；不帶 `bundles` 時皆為 `[]`；(f) 老師以恢復碼回復後 `snapshot.room.bundles` 不變

### Implementation for User Story 1

- [X] T012 [US1] 修改 `frontend/src/pages/Home.tsx` 的預覽區塊：(a) 新增狀態 `bundles: string[][]` 與 `selected: string[]`；(b) 預覽題號清單改為可勾選（每個作答格一個勾選框，依題目順序；已屬於題組的題目以框線群組顯示並停用勾選）；(c) 「設為題組」按鈕：`selected.length < 2` 提示「題組至少需要 2 題」、`!isAdjacent(preview.questions, selected)` 提示「題組只能包含相鄰的題目」、與既有題組重疊提示「一題只能屬於一個題組」，通過則加入 `bundles` 並清空勾選；(d) 每個已設定題組旁有「取消」按鈕；(e) 重新讀取或改連結時（設定新 `preview` 時）清空 `bundles` 與 `selected`；(f) 「確認建立」呼叫 `createRoom({ sheetUrl, fingerprint, bundles })`；伺服器回 `BUNDLES_INVALID` 時顯示其訊息、不離開預覽。`npx tsc -b` 通過
- [X] T013 [US1] 修改 `frontend/src/pages/TeacherRoom.tsx` 與 `frontend/src/components/QuestionFields.tsx` 的 `QuestionList`：老師端從 `snapshot.room.bundles` 保存 `bundles` 狀態；`QuestionList` 新增選填 prop `bundles?: BundleItem[]`，有題組時以 `groupByUnit` 呈現，題組顯示為一個框並標示「題組：Q3、Q4」（有題目文字時，題組成員仍逐題顯示文字但框在一起）

**Checkpoint**: US1 可獨立驗證——建立房間時能設定題組並在老師端看到

---

## Phase 4: User Story 2 - 學生在同一張卡片內填完整個題組並一次送出 (Priority: P1)

**Goal**: 題組成員在學生端同一張卡片、一顆送出鈕；只有全部填寫才可送出；送出全有或全無，整組共用時間與名次。

**Independent Test**: 房間設定 Q3、Q4 為題組並開始搶答；只填 Q3 時無法送出；兩格都填後按一次送出，兩題同時「已送出」。

### Tests for User Story 2

- [X] T014 [P] [US2] 新增 `backend/tests/test_bundle_submit.py`（使用 `make_bundle_room`、`join_student`）：(a) 送 `{"type":"submit_bundle","bundleId":"B1","answers":{"3":"CPU","4":"記憶體"}}` → 發送者收到 `{"type":"bundle_submitted","bundleId":"B1","answers":{"3":"CPU","4":"記憶體"},"round":1}`；`room.submissions` 新增恰好 2 筆，`question_id` 分別為 `"3"`、`"4"`，`bundle_id == "B1"`，`seq`、`submitted_at`、`rank` 兩筆相同；(b) 全有或全無：Q4 為 `""`、`"   "`、缺少 Q4、多帶 `"5"` → `error.code == "BUNDLE_INCOMPLETE"`、`error.bundleId == "B1"`、`details.questionIds` 指出問題題目；Q4 長度 501 → `ANSWER_TOO_LONG` 且 `details.questionIds == ["4"]`；以上每種情況 `len(room.submissions)` 與 `room.next_seq` 皆不變；(c) `bundleId:"B9"` → `BUNDLE_NOT_FOUND`；(d) 非搶答中（`start=False` 或結束後）→ `PHASE_LOCKED` 且不寫入；(e) 單題 `{"type":"submit","questionId":"3","answer":"x"}` → `QUESTION_IN_BUNDLE`（附 `questionId`），不寫入；未綁定的 Q1 單題送出照常成功，名次不受題組影響；(f) 同組連點兩次 → 第二次只回發送者既有的 `bundle_submitted`，紀錄仍為 2 筆；(g) 所有錯誤都不關閉連線，之後仍可正常送出；(h) 新一輪開始後可再送出同一題組（名次重新從 1 起算），舊輪紀錄保留

### Implementation for User Story 2

- [X] T015 [US2] 修改 `backend/app/services/submissions.py`：(a) `submit()` 在驗證題目存在之後，若 `question_id in room.bundle_of` → `raise err("QUESTION_IN_BUNDLE")`；(b) 新增 `submit_bundle(room, group, bundle_id, answers) -> tuple[list[Submission], bool]`，**整段同步、不得 await**（research D4），依序：房間 Open 且 `phase == "Answering"` 否則 `PHASE_LOCKED` → `bundles.get_bundle` 為 `None` 則 `BUNDLE_NOT_FOUND` → `answers` 非 dict 或 key 集合不等於成員、或任一成員答案非字串或 `strip()` 為空 → `BUNDLE_INCOMPLETE`（`details={"questionIds": [缺少／空白／多帶的題目，依題目順序]}`）→ 任一 `len(answer) > MAX_ANSWER_LENGTH`（500）→ `ANSWER_TOO_LONG`（`details={"questionIds": [...]}`）→ 去重：`room.submission_index.get((room.round, group.normalized_name, 第一個成員))` 存在則回傳所有成員的既有紀錄與 `False` → 取一次 `seq = room.next_seq`（遞增一次）、`rank_key = (room.round, bundle.id)` 計算名次、`now = utcnow()` → 為每個成員依題目順序建立 `Submission(..., answer=answers[qid], submitted_at=now, seq=seq, rank=rank, bundle_id=bundle.id)`、追加到 `room.submissions` 並寫入 `submission_index` → `rooms.touch(room)` → 回傳 `(紀錄清單, True)`；(c) 新增 `to_bundle_group_event(subs)` 回傳 `{"type":"bundle_submitted","bundleId":...,"answers":{qid: answer},"round":...}`；(d) `to_teacher_event` 新增 `"bundleId": sub.bundle_id`。`AppError` 需能帶 `details`（沿用 `err(code, details)`）
- [X] T016 [US2] 修改 `backend/app/api/ws.py` 學生迴圈：新增處理 `data.get("type") == "submit_bundle"`：取 `bundleId`（字串）與 `answers`，呼叫 `submissions.submit_bundle`；`AppError` 時只回發送者 `{"type":"error","code","message","bundleId", "details": e.details}`（`details` 為 `None` 時省略）且不關閉連線；`created == False` 時只回發送者 `to_bundle_group_event(既有紀錄)`；成功時的廣播留給 T022（本任務先只回發送者 `bundle_submitted` 使 T014 通過，T022 再改為全組與各受眾廣播）。單題 `submit` 的 `QUESTION_IN_BUNDLE` 錯誤沿用既有附 `questionId` 的錯誤路徑
- [X] T017 [US2] 修改 `frontend/src/components/QuestionFields.tsx`：新增 props `bundles?: BundleItem[]`、`bundleErrors?: Record<string, string>`、`onSubmitBundle?: (bundleId: string) => void`、`othersSubmittedBundles?: string[]`；以 `groupByUnit(questions, bundles ?? [])` 產生卡片：(a) `single` 單位維持現有逐題輸入與送出鈕；(b) `bundle` 單位為一個 `fieldset`，標題「題組：Q3、Q4」，每題顯示題號、題目文字（若有）與輸入框，**題組成員不顯示各自的送出鈕**；卡片底部一顆「送出」：任一成員 `trim()` 為空時停用並顯示「請填完題組內所有題目」；全部成員都在 `submitted` 中時整卡顯示「已送出」、所有輸入框唯讀並顯示已送出內容；(c) 每題仍顯示「已達 500 字上限」提示；(d) `bundleErrors[bundle.id]` 顯示於卡片底部（`role="alert"`）
- [X] T018 [US2] 修改 `frontend/src/pages/StudentJoin.tsx`：(a) 新增狀態 `bundles: BundleItem[]`（由 `joined.bundles` 設定）與 `bundleErrors`；(b) `onSubmitBundle(bundleId)`：清除該題組錯誤，送 `{type:'submit_bundle', bundleId, answers}`（`answers` 只含該題組成員的 `values`），不做樂觀更新；(c) 新增 `case 'bundle_submitted'`：把 `answers` 合併進 `submitted` 與 `values`，並清除該題組與成員的錯誤；(d) **錯誤處理**：在既有 `msg.questionId !== undefined` 判斷之前加上 `msg.bundleId !== undefined` 分支，把訊息存入 `bundleErrors[bundleId]` 並 `return`（否則題組錯誤會被當成致命錯誤而離開房間）；(e) 新一輪清空時一併清空 `bundleErrors`；(f) 把 `bundles`、`bundleErrors`、`onSubmitBundle` 傳給 `QuestionFields`。`npx tsc -b` 通過

**Checkpoint**: US2 可獨立驗證——題組卡片、填滿才可送、全有或全無

---

## Phase 5: User Story 3 - 同組多視窗同步與他組保密 (Priority: P1)

**Goal**: 同組其他視窗整張卡片同步；他組只看到匿名「本題組已有組別送出」；重連還原。

**Independent Test**: 同組兩視窗，A 送出題組，B 在 2 秒內整卡「已送出」並顯示兩題答案；另一組只看到「本題組已有組別送出」。

### Tests for User Story 3

- [X] T019 [P] [US3] 新增 `backend/tests/test_bundle_privacy.py`：第 1 組兩個視窗、第 2 組一個視窗、老師 WebSocket；第 1 組視窗 A 送出題組後：(a) 視窗 B 收到與 A 相同的 `bundle_submitted`；(b) 第 2 組**只**收到 `{"type":"bundle_hint","bundleId":"B1","round":1}`（逐一斷言 key 集合恰為 `{"type","bundleId","round"}`），且第 2 組收到的所有訊息序列化後不含第 1 組組名與任何答案文字、不含 `bundle_submitted`／`submission`／`board`；(c) 老師收到兩則 `submission`（`bundleId == "B1"`、`submittedAt`／`rank` 相同）與一則 `board`；(d) 第 1 組新視窗加入時 `joined.mySubmissions` 含 `"3"`、`"4"`，第 2 組重連時 `joined.submittedByOthers` 含 `"3"`、`"4"`、`mySubmissions` 不含；(e) 新一輪開始後 `mySubmissions` 為空、`bundles` 不變
- [X] T020 [P] [US3] 新增 `backend/tests/test_bundle_concurrency.py`（參考 `test_ranking_concurrency.py` 的併發寫法）：(a) 同組兩個視窗幾乎同時送出同一題組（答案不同）重複 50 次（每次新房間）→ 每次該組在 B1 只有 2 筆紀錄且兩筆 `seq` 相同（不會一題來自 A、一題來自 B）；(b) 兩組同時送出同一題組重複 50 次 → 名次為 {1, 2} 不重複不並列，同組兩筆名次相同；(c) 直接在同一事件迴圈內連續呼叫 `submissions.submit_bundle` 驗證 `next_seq` 每次被接受的題組只遞增 1（原則 II）

### Implementation for User Story 3

- [X] T021 [US3] 修改 `backend/app/services/submissions.py`：新增 `to_bundle_hint_event(subs)` 回傳 `{"type":"bundle_hint","bundleId":...,"round":...}`（只含這三個 key，不含組名、答案、數量、時間；模組 docstring 補充題組的三種受眾）
- [X] T022 [US3] 修改 `backend/app/api/ws.py` 的 `submit_bundle` 成功路徑（接續 T016）：依序 `await realtime.broadcast_to_group(room.code, group.normalized_name, to_bundle_group_event(subs))`、對每筆 `await realtime.broadcast_to_teachers(room.code, to_teacher_event(sub))`、`await realtime.broadcast_to_teachers(room.code, ranking.build_board(room))`、`await realtime.broadcast_to_other_groups(room.code, group.normalized_name, to_bundle_hint_event(subs))`；**全部寫入完成後才開始 await**（寫入在 `submit_bundle` 內已完成）。使 T019、T020 通過
- [X] T023 [US3] 修改 `frontend/src/pages/StudentJoin.tsx` 與 `frontend/src/components/QuestionFields.tsx`：(a) 新增狀態 `othersSubmittedBundles: string[]`；`case 'bundle_hint'`（`round >= lastRound.current`）時加入 bundleId；`joined` 時由 `submittedByOthers` 與 `bundles` 推出（任一成員在 `submittedByOthers` 中即視為該題組已有他組送出）；新一輪清空；(b) 題組卡片在本組尚未送出且 `othersSubmittedBundles` 含該題組時顯示「本題組已有組別送出」（不顯示組名或數量）；(c) 重連時 `mySubmissions` 含全部成員即整卡顯示已送出。`npx tsc -b` 通過

**Checkpoint**: US1～US3 皆可驗證

---

## Phase 6: User Story 4 - 老師端進度板與結果頁以題組為單位呈現 (Priority: P2)

**Goal**: 進度板一個題組一份名次清單；結果頁題組各題框在一起、同一個搶下組別；領先題數以題數計。

**Independent Test**: 兩組先後送出 Q3+Q4 題組，進度板題組只顯示一份名次清單；結束搶答後結果頁題組由第 1 名組別搶下並列出兩題答案。

### Tests for User Story 4

- [X] T024 [P] [US4] 新增 `backend/tests/test_bundle_board.py`：(a) 第 1 組先、第 2 組後送出題組後，`ranking.build_board(room)` 中 Q3、Q4 的 `leader` 皆為第 1 名組別、`ranking` 完全相同，且每題項目帶 `bundleId == "B1"`，未綁定題目為 `None`；(b) `leadTally` 中第 1 組 `leadCount == 2`（Clarification Q1）；另送一題單題後再加 1；(c) 結束搶答後 `round_result` 的 Q3、Q4 `winnerGroup` 相同、`answer` 為各自答案；無人送出的另一題組（以 `make_bundle_room(bundles=[["3","4"],["5","6"]])`）Q5、Q6 皆為 `None`；(d) 老師 `snapshot.room.board` 與 `submissions[].bundleId` 正確

### Implementation for User Story 4

- [X] T025 [US4] 修改 `backend/app/services/ranking.py` 的 `build_board`：每題項目新增 `"bundleId": room.bundle_of.get(q.id)`；排名與 `leadTally` 邏輯**不變**（同題組各題 rank 相同，故以題數計自然成立）
- [X] T026 [P] [US4] 修改 `frontend/src/components/RankingBoard.tsx`：新增 prop `bundles?: BundleItem[]`；以 `groupByUnit` 分卡，題組顯示為一張卡片、標題「題組：Q3、Q4」，只顯示**一份**名次清單（取第一個成員的 `ranking`）與最快送出組別；尚無人送出顯示「尚無組別送出」；領先題數區塊不變
- [X] T027 [P] [US4] 修改 `frontend/src/components/ResultBoard.tsx`：新增 prop `bundles?: BundleItem[]`；題組成員合成一張卡片：標題「題組：Q3、Q4」、一個搶下組別（`winnerGroup` 取第一個成員）、逐題列出題號與答案（`whitespace-pre-wrap`）；`winnerGroup === myGroup` 標示「本組搶下」；成員皆無人送出時顯示「本題組無人搶答」；單題維持原樣
- [X] T028 [US4] 修改 `frontend/src/pages/TeacherRoom.tsx` 與 `frontend/src/pages/StudentJoin.tsx`：把 `bundles` 傳給 `RankingBoard`（老師）與 `ResultBoard`（老師、學生）；老師端處理 `submission` 事件時保存 `bundleId`。`npx tsc -b` 通過

**Checkpoint**: 四個故事皆可驗證

---

## Phase 7: Polish & Cross-Cutting Concerns

- [X] T029 [P] 比對 `diagrams/class.puml`、`diagrams/component.puml`、`diagrams/sequence.puml` 與實作（QuestionBundle、`services/bundles.py`、`submit_bundle` 全有或全無與共用 seq／rank、`bundle_submitted`／`bundle_hint`／`submission` 受眾、`joined`／`snapshot` 的 `bundles`）；不一致時修正程式或更新圖表，並執行 `java -jar plantuml.jar -charset UTF-8 -tpng diagrams/*.puml`（無 Graphviz 時加 `-Playout=smetana`）重新產圖（Constitution VI 實作後驗證）
- [X] T030 [P] 更新 `README.md`（若有功能清單）：補上「建立房間時可把相鄰題目綁成題組，學生整組一次送出」；確認 `specs/007-bundle-submit/quickstart.md` 與實作一致
- [X] T031 執行完整驗證：`cd backend && uv run pytest`（全數通過，含 Step 1～6 既有測試）、`cd frontend && npx tsc -b`、`npm run lint`；依 `quickstart.md` 手動驗證情境 1～15 逐項走一遍，特別是「Q3、Q4 在同一張卡片且只有一顆送出鈕」「只填一格不能送出」「兩格填完一次送出、兩題同時已送出」「他組只看到本題組已有組別送出」

---

## Dependencies & Execution Order

### Phase Dependencies

- **Setup (P1)** → **Foundational (P2)** → 使用者故事 → **Polish (P7)**
- US1 為 MVP（題組設定）；US2 依 Foundational（題組資料已可透過 API 建立，測試不需 US1 的前端）；US3 依 US2 的 `submit_bundle`（T015、T016）；US4 依 US2（需要題組送出紀錄）
- 後端同檔任務須依序：`submissions.py`（T007 → T015 → T021）；`ws.py`（T006 → T016 → T022）；`rooms.py`（T004）；`api/rooms.py`（T005）；`ranking.py`（T025）
- 前端同檔任務須依序：`QuestionFields.tsx`（T013 → T017 → T023）；`StudentJoin.tsx`（T018 → T023 → T028）；`TeacherRoom.tsx`（T013 → T028）

### Within Each Story

- 測試任務（T011、T014、T019、T020、T024）可先寫、先看到失敗
- T002 → T003 → T004、T005、T006、T007；T009 → T010 → 所有前端故事任務

### Parallel Opportunities

- Foundational：T008、T009、T010 與後端 T003～T007 可平行（不同檔案）
- US1：T011（測試）與 T012（Home.tsx）可平行
- US2：T014 與 T017 可平行
- US3：T019、T020 可平行
- US4：T024、T026、T027 可平行
- Polish：T029、T030 可平行

## Parallel Example: User Story 2

```bash
# 可同時進行（不同檔案）：
Task: "T014 新增 backend/tests/test_bundle_submit.py"
Task: "T017 修改 frontend/src/components/QuestionFields.tsx 題組卡片"
# 之後依序：T015 → T016（後端）；T018（前端，依 T017）
```

## Parallel Example: User Story 3

```bash
Task: "T019 新增 backend/tests/test_bundle_privacy.py"
Task: "T020 新增 backend/tests/test_bundle_concurrency.py"
# 之後：T021 → T022（後端）；T023（前端）
```

## Implementation Strategy

### MVP First

1. 完成 Phase 1、2（題組資料能隨房間建立與下發）
2. 完成 US1（老師能設定題組）→ 以 quickstart 情境 1～4 驗證
3. 緊接 US2（學生能整組送出），因為驗證效果需要 US1＋US2 才完整

### Incremental Delivery

1. Setup + Foundational → 基礎就緒
2. US1 → 題組設定可用
3. US2 → 題組卡片與整組送出（達成本步驟主要驗證效果）
4. US3 → 多視窗同步、他組保密、併發（Constitution II、III 測試）
5. US4 → 進度板與結果頁題組呈現
6. Polish → 圖表一致性、文件、完整驗證
