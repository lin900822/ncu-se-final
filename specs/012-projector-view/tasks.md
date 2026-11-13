# Tasks: 教室大螢幕投影專用視圖

**Input**: `/specs/012-projector-view/` 下的 plan.md、spec.md、research.md、data-model.md、contracts/、quickstart.md
**Prerequisites**: plan.md、spec.md（皆已備齊）；Step 1～11 已實作完成（現有 340 個後端測試通過）
**Tests**: 依 plan.md 的 Testing 與 Constitution（原則 III 搶答中零洩漏、II 不改仲裁與紀錄、即時同步與斷線還原）加入 pytest；真實畫面以 quickstart.md 在瀏覽器驗證
**Format**: `- [ ] T### [P?] [Story?] 描述（含檔案路徑）`；`[P]` = 可平行（不同檔案、無未完成相依）

> 使用者故事對應：US1＝取得專用投影網址、唯讀放大無控制按鈕的畫面（P1）、US2＝倒數動畫與搶答中匿名進度看板（P1）、US3＝結算後各題得主看板與累計得分排行榜（P1）、US4＝斷線重連、房間結束、無題目房間（P2）。
>
> 名詞：**搶答單位 unit_id**＝題組 id 或題目 id（`bundles.unit_of`）；**投影連線**＝`/ws/projector` 的連線（唯讀、不計為組別）；**投影狀態**＝`projector.build_state(room)` 推導出的整份全班公開資料；**已結算輪次**＝階段為 Answering 時 `1..round-1`，其他階段 `1..round`。
>
> 實作要點：投影通道獨立且只推送；保密由後端決定（搶答中只輸出各單位 `submitted` 布林與進度，**不產生**組名與答案）；結算後的得主直接用 `results.build_result()`；得分累計各已結算輪次的 `effective.allocate(room, n).wins`；倒數是 `start_answering` 之後對已連線投影送的一次性 `countdown` 事件，不補播、不延後學生端開放。**不新增依賴、不新增儲存、不修改任何既有紀錄、不修改既有測試。**
>
> 同檔案順序提醒（不可平行）：`backend/app/services/projector.py`：T004 → T014 → T020；`backend/app/api/ws.py`：T008 → T015 → T024；`backend/app/services/rooms.py`：T008 → T024；`frontend/src/pages/Projector.tsx`：T010 → T017 → T022 → T025；`frontend/src/pages/TeacherRoom.tsx`：T011。

## Phase 1: Setup

- [X] T001 執行 `cd backend && uv run pytest` 與 `cd frontend && npx tsc -b`（於 `frontend/` 內 `nvm use`），確認 Step 1～11 基準全數通過（預期後端 340 個測試）後才開始；並記下 `npm run lint` 的警告數作為「不得增加」的基準（目前為 16）

---

## Phase 2: Foundational（阻擋所有故事的共用基礎）

**⚠️ 完成前不得開始任何使用者故事**；完成後既有 340 個測試必須仍全數通過（沒有投影連線時行為與 Step 11 完全相同）

- [X] T002 修改 `backend/app/models.py`：`Room` 新增 `projector_key: str = ""`（唯讀投影憑證；建立房間時由 `rooms.create_room` 以 `store.generate_token()` 賦值，房間存續期間固定，**不得**等於 `teacher_token` 或 `recovery_code`）；不修改任何既有欄位與 dataclass
- [X] T003 修改 `backend/app/realtime.py`：`Realtime` 新增 `projectors: dict[str, set[WebSocket]]`、`add_projector(code, ws)`、`remove_projector(code, ws)`、`broadcast_to_projectors(code, message)`、`has_projectors(code)`；**不**加入 `students`／`teachers`，`has_connections()` **不**計入投影連線（不阻止閒置逾時）；模組 docstring 補一條保密約束：投影通道只能傳「全班公開」的 `projector_state` 與 `countdown`，搶答中嚴禁傳入組名（名單除外）、答案、名次、時間、讓位／保留
- [X] T004 新增 `backend/app/services/projector.py`（只匯入 `..models`、`..realtime`、`bundles`、`effective`、`results`）：(a) `build_state(room) -> dict`：先實作骨架——`type="projector_state"`、`code`、`status`、`phase`、`round`、`groups`（依加入順序的組名）、`questions`（`question_public`）、`bundles`（`bundle_public`）、`progress=None`、`submitted=None`、`result=None`、`scoreboard=[]`（後續故事補上）；(b) `async publish(room)`：`realtime.broadcast_to_projectors(room.code, build_state(room))`，無投影連線時直接返回；(c) `async announce_countdown(room)`：對投影送 `{"type":"countdown","round":room.round}`；純讀取、不得修改 `room` 的任何欄位
- [X] T005 [P] 修改 `backend/tests/conftest.py`：新增 `projector_ws(client, code, key)`（以 `client.websocket_connect(f"/ws/projector?code={code}&key={key}")` 回傳 context manager 與第一則訊息）、`drain_projector(ws)`（以必定被忽略的哨兵訊息後再收一則 `projector_state` 的方式取回目前所有已排隊訊息，避免測試卡住；實作時以 `timeout` 保護）、`get_projector_key(client, code, token)`（連老師 `/ws/teacher` 讀 `snapshot.room.projectorKey`）；不修改任何既有 fixture 的行為
- [X] T006 [P] 修改 `frontend/src/lib/api.ts`：`createRoom` 回應型別新增 `projectorKey: string`；新增並 `export` 型別 `ProjectorState`（`type`、`code`、`status`、`phase`、`round`、`groups`、`questions`、`bundles`、`progress: {answered:number,total:number} | null`、`submitted: Record<string, boolean> | null`、`result: {round:number,results:{questionId:string,winnerGroup:string|null,answer:string|null,noValid?:boolean}[]} | null`、`scoreboard: {group:string,score:number,rank:number}[]`）與 `projectorUrl(code, key)`（回傳 `/projector?code=…&key=…`，兩值皆 `encodeURIComponent`）

**Checkpoint**: 投影憑證欄位、連線登記、狀態骨架、測試輔助與前端型別就緒；既有 340 個測試仍全數通過、`npx tsc -b` 通過

---

## Phase 3: User Story 1 - 取得專用投影網址，在大螢幕開啟唯讀、放大、無控制按鈕的畫面 (Priority: P1) 🎯 MVP

**Goal**: 老師端取得只含唯讀憑證的投影網址；投影畫面放大、無任何控制項，等待搶答階段顯示房間代碼與組別；投影連線不計為組別；錯誤憑證一致回「無法顯示」。

**Independent Test**: 老師建立房間後取得投影網址並在另一視窗開啟；畫面顯示房間代碼與已加入組別、找不到任何控制按鈕；用投影憑證打任何老師端點皆 401；錯誤 key 顯示「無法顯示」。

### Tests for User Story 1

- [X] T007 [P] [US1] 新增 `backend/tests/test_projector_access.py`（使用 `client`、`use_sheet`、`projector_ws`、`get_projector_key`、`join_student`）：(a) **憑證**：建立回應含 `projectorKey`；與 `teacherToken`、`recoveryCode` 皆不同；老師 `snapshot.room.projectorKey` 相同；以恢復碼換裝置後取得**同一把**；學生 `joined` 與學生收到的任何訊息序列化後不含該 key；(b) **連線成功**：正確 `code`＋`key` 立即收到 `projector_state`（`phase=="Waiting"`、`code`、空 `groups`、`progress`／`submitted`／`result` 皆 `None`、`scoreboard==[]`）；(c) **錯誤一致**：錯誤 key、以老師 token 當 key、以恢復碼當 key、不存在的房間代碼、空 key 一律先收到**完全相同**的 `{"type":"projector_unavailable"}` 並被關閉（`1008`）；(d) **唯讀**：投影連線送 `{"type":"submit",...}`、`{"type":"join",...}`、`{"type":"start"}` 與任意 JSON 後，房間的 `submissions`、`groups`、`phase`、`phase_log`、`reviews` 逐欄不變；(e) **REST 401**：以投影 key 當 Bearer 呼叫 `phase/start`、`phase/end`、`reviews`、`backfill`、`backfill/preview`、`close`、`records.csv` 全部 401 且狀態不變；(f) **不計為組別**：開 3 個投影連線後，老師 `snapshot.groups`／`count` 不變、學生仍可加入同名組別、`group_joined`／`group_status` 不因投影連線而出現；投影連線與其送來的訊息不更新 `room.last_activity_at`；(g) **即時名單**：學生新加入組別後，投影連線收到的 `projector_state.groups` 含該組名（同組多視窗、重連不重複推送新名單以外的內容）；(h) 多個投影連線同時收到相同狀態、互不影響

### Implementation for User Story 1

- [X] T008 [US1] 修改 `backend/app/services/rooms.py`、`backend/app/api/rooms.py`、`backend/app/api/ws.py`：(a) `rooms.create_room` 產生 `room.projector_key = store.generate_token()`；`snapshot()["room"]` 新增 `"projectorKey": room.projector_key`（僅老師 snapshot）；(b) `POST /api/rooms` 回應新增 `"projectorKey"`；(c) `ws.py` 新增 `@router.websocket("/ws/projector")`：先 `accept`，以 `hmac.compare_digest` 驗證 `code`＋`key`（房間不存在、key 錯誤、空值皆走同一條路徑）；失敗送 `{"type":"projector_unavailable"}` 並 `close_safe(ws, 1008)`；成功 `realtime.add_projector`、送 `projector.build_state(room)`，之後迴圈 `receive_text()` **丟棄**所有訊息（不呼叫 `rooms.touch`），`finally` 移除連線；房間已 `Closed` 的處理留給 T023；使 T007(a)(b)(c)(d)(e)(f) 通過
- [X] T009 [US1] 修改 `backend/app/services/groups.py`：`announce_join` 在 `is_new` 時於通知老師之後 `await projector.publish(room)`（只有新組別才推送名單；既有組別重連不推）；`projector` 只匯入 `..realtime`／`..models` 的服務，確認無循環匯入；使 T007(g)(h) 通過
- [X] T010 [US1] 新增 `frontend/src/pages/Projector.tsx` 並修改 `frontend/src/App.tsx`：新增路由 `/projector`；頁面從 `location.search` 取 `code`、`key`，以 `useReconnectingSocket({ path: '/ws/projector?code=…&key=…', noReconnectCodes: [1008] })` 連線，狀態 `state: ProjectorState | null`、`unavailable: boolean`；收到 `projector_state` 覆蓋狀態、收到 `projector_unavailable` 顯示全螢幕「無法顯示」（不透露原因、不重連）；**整頁不含任何 `<button>`、`<input>`、`<a>` 連結或可聚焦控制項**；等待搶答階段以大字顯示房間代碼（`clamp()` 字級、高對比深色底）與已加入組別（格線自動分欄）；先建立此骨架，進度／得主／排行榜由後續故事補上
- [X] T011 [US1] 修改 `frontend/src/pages/TeacherRoom.tsx`：從 `snapshot.room.projectorKey` 保存狀態；在房間代碼區塊加入「開啟投影視圖」（`window.open(projectorUrl(code, key), '_blank', 'noopener')`）與「複製投影網址」（複製完整絕對網址，成功時短暫顯示「已複製」）兩個控制項，旁註「投影網址只能檢視、不能操作」；沒有 `projectorKey` 時兩者停用；`npx tsc -b` 通過

**Checkpoint**: 老師可開啟唯讀投影視圖，等待搶答階段顯示代碼與組別；錯誤憑證顯示無法顯示；US1 可獨立展示

---

## Phase 4: User Story 2 - 搶答倒數動畫與搶答中的進度看板（不洩漏答案） (Priority: P1)

**Goal**: 老師開始搶答時投影播放約 3 秒「3、2、1、開始！」，之後顯示只含匿名進度的看板；晚連線不補播；學生端時序不變。

**Independent Test**: 老師開始搶答，投影播放倒數後切到進度看板；學生送出時對應題目即時變成「已有組別送出」，但整個畫面與所有傳到投影的資料找不到任何組名或答案；重新整理不重播。

### Tests for User Story 2

- [X] T012 [P] [US2] 新增 `backend/tests/test_projector_privacy.py`（使用 `make_fair_room`／`make_started_room`、`claim`、`claim_bundle`、`projector_ws`）：(a) **逐則零洩漏**：多組、多題（含題組）送出，搶答中投影收到的**每一則**訊息序列化後，不含任何送出組別的組名與答案（組別名單中的組名只能出現在 `groups` 與 `scoreboard` 欄位，且內容與送出無關——以「組別尚未送出任何答案時與送出後 `groups`、`scoreboard` 完全相同」斷言）、不含 `rank`、`seq`、`submittedAt`、`outcome`、`Yielded`、`Kept`、`Behind`、`leader`、`reason`、`answer`；(b) **匿名進度**：某組送出 Q1 後，`submitted["1"]` 由 `false` 變 `true`、`progress.answered` 由 0 變 1、`total` 為單位數（題組算 1 個單位）；同單位再送（他組）不改變進度；題組整組送出只算 1；(c) **重複送出**：同組重複送出不新增紀錄時，投影**不**收到新狀態；(d) **欄位白名單**：搶答中的 `projector_state` 鍵集合固定為契約列出的鍵；(e) **Step 11 規則不洩漏**：設有上限／冷卻的房間搶答中，狀態不含任何讓位／保留／達上限資訊；(f) 結算前學生訊息與老師訊息不受影響（既有保密測試不修改）
- [X] T013 [P] [US2] 新增 `backend/tests/test_projector_countdown.py`（使用 `fake_clock`、`client`、`projector_ws`）：(a) 老師開始搶答時，已連線投影依序收到 Answering 的 `projector_state`（`phase=="Answering"`、`round` 加一、進度全 0）與 `{"type":"countdown","round":n}`，且 `countdown` **在後**；(b) 重複按開始（冪等，`changed:false`）**不**再送 `countdown`；(c) 開始之後才連線的投影、重新連線的投影**只**收到 `projector_state`，不收到 `countdown`；(d) 第二輪開始時再送一次 `countdown`（`round==2`）且進度被清空；(e) **不影響階段時序**：學生與老師收到的 `phase_changed`、`question_texts` 訊息內容與順序與 Step 11 完全相同（比對訊息序列），學生在 `countdown` 後立即可送出且名次、`seq` 不受影響；(f) 學生連線與老師連線**不會**收到 `countdown`、`projector_state`

### Implementation for User Story 2

- [X] T014 [US2] 修改 `backend/app/services/projector.py`：`build_state` 在 `phase=="Answering"` 時填入 `submitted`（`{unitId: bool}`，單位＝`bundles.unit_of`，只看本輪是否存在任何送出）與 `progress={"answered","total"}`；其他階段兩者為 `None`；**不得**讀取或輸出送出的組名、答案、名次、時間；使 T012(b)(d) 通過
- [X] T015 [US2] 修改 `backend/app/api/ws.py` 與 `backend/app/services/phase.py`：(a) `ws.py` 兩個 submit 路徑（單題、題組）在「新建紀錄」且 `broadcast_to_other_groups` 之後 `await projector.publish(room)`（重複送出的早退路徑**不**呼叫）；(b) `phase.start_answering` 在 `_reveal_texts` 與老師看板重設之後，`await projector.publish(room)` 再 `await projector.announce_countdown(room)`（僅在真正切換階段時；冪等早退路徑不呼叫）；`end_answering` 在結算廣播之後 `await projector.publish(room)`；使 T012(b)(c)、T013 通過，且既有的階段與保密測試仍通過
- [X] T016 [P] [US2] 新增 `frontend/src/components/projector/Countdown.tsx` 並修改 `frontend/src/index.css`：`Countdown({ onDone })` 全螢幕覆蓋顯示 3、2、1、開始！各約 0.75 秒（共約 3 秒），以 CSS keyframes 做放大淡出；`@media (prefers-reduced-motion: reduce)` 時改為無動畫的逐秒靜態數字；結束後呼叫 `onDone`；元件內不含任何可聚焦控制項
- [X] T017 [US2] 新增 `frontend/src/components/projector/ProgressBoard.tsx` 並修改 `frontend/src/pages/Projector.tsx`：`ProgressBoard` 依 `questions`／`bundles` 顯示每個單位（題組整組一格，標題如「題組：Q3、Q4」）的「尚無組別送出」／「已有組別送出」（已送出者醒目樣式）與頂部總進度「已有答案的題目 3／6」，格線依單位數自動分欄、縮小字級以免捲動；`Projector.tsx` 收到 `countdown` 事件時顯示 `Countdown` 覆蓋，結束後回到進度看板；**僅在連線期間收到的 `countdown` 才播放**（重新整理、晚連線不播）；`npx tsc -b` 通過

**Checkpoint**: 倒數動畫與匿名進度看板可用且零洩漏；學生端時序不變；US1＋US2 可獨立展示

---

## Phase 5: User Story 3 - 結算後的各題得主看板與組別得分排行榜 (Priority: P1)

**Goal**: 結算後投影顯示各題得主（組名＋答案，與學生結果一致）與累計得分排行榜（同分並列）；審核與公平規則連動即時更新；多輪累計、進行中輪次不計入。

**Independent Test**: 兩組各搶得數題後結束搶答，投影顯示每題得主與排行榜；駁回某答案後 3 秒內更新，並與老師端、學生端逐題一致。

### Tests for User Story 3

- [X] T018 [P] [US3] 新增 `backend/tests/test_projector_score.py`（使用 `make_fair_room`、`claim`、`claim_bundle`、`post_review`、`projector_ws`、`store`）：(a) **累計**：第 1 輪第 1 組取得 3 題、第 2 輪第 1 組取得 1 題 → 第 1 組 4 分；各輪各自以該輪的審核與公平規則計算（第 1 輪駁回後分數改變、第 2 輪不受影響）；(b) **進行中輪次不計入**：第 2 輪 Answering 時 `scoreboard` 仍為第 1 輪累計；結算後才加入；(c) **題組計 N 題**、Step 11「保留」計入、讓位後的得分與 `effective.allocate().wins` 逐組相等；(d) **並列**：得分 3、3、1 → `rank` 為 1、1、3，同分以組名排序，順序穩定；0 分組別列出且排在最後；(e) **確定性**：相同紀錄重複 `build_state` 100 次結果完全相等；(f) **唯讀**：呼叫前後逐欄比對 `Room`（submissions、reviews、phase_log、groups、round、phase）完全不變；(g) **規模**：30 題 × 20 組 × 3 輪下單次 `build_state` < 200 ms；20 個投影連線一次廣播 < 1 秒
- [X] T019 [P] [US3] 新增 `backend/tests/test_projector_state.py`（使用 `make_fair_room`／`make_ranked_room`、`post_review`、`projector_ws`、老師與學生 ws）：(a) **Ended 內容**：`result` 與學生 `round_result`（`{round, results}`）**逐題完全相等**，也等於老師 `snapshot.room.result`（SC-002）；題組一格、無人搶答、全被駁回 `noValid` 皆與學生端一致；結算後狀態不含 `rank`、`seq`、`submittedAt`、`outcome`、審核理由、被駁回者資訊；(b) **審核即時更新**：駁回／恢復後投影收到更新的 `projector_state`，`result` 與 `scoreboard` 隨之改變，且仍與學生／老師結果相等；(c) **Step 11 連動**：上限讓位造成的得主改變反映在 `result` 與 `scoreboard`；(d) **階段切換**：結算後再開始下一輪，狀態回到 Answering 的匿名進度（`result` 為 `None`），`scoreboard` 維持累計；(e) **無題目房間**：`questions==[]`、`progress` 的 `total` 為 0（或 `None`）、`result` 為 `None` 或空、排行榜全 0，不拋例外；(f) 重新連線取得與先前相同的整份狀態（還原）

### Implementation for User Story 3

- [X] T020 [US3] 修改 `backend/app/services/projector.py`：(a) 新增 `scoreboard(room) -> list[dict]`：依資料模型的「已結算輪次」定義，對每輪 `effective.allocate(room, n).wins` 以正規化組名累加；組別名單中缺項補 0；顯示名取 `room.groups[normalized].name`；排序（分數降冪、組名升冪）並以競賽排名賦 `rank`；(b) `build_state` 在 `phase=="Ended"` 時填入 `result=results.build_result(room)`，`scoreboard` 於所有階段填入；使 T018、T019(a)(c)(d)(e) 通過
- [X] T021 [US3] 修改 `backend/app/services/review.py`：`publish_review` 在既有廣播之後 `await projector.publish(room)`；使 T019(b) 通過；`apply_review` 簽章與行為不變
- [X] T022 [US3] 新增 `frontend/src/components/projector/WinnersBoard.tsx`、`frontend/src/components/projector/Scoreboard.tsx` 並修改 `frontend/src/pages/Projector.tsx`：`WinnersBoard` 依 `questions`／`bundles`／`result` 顯示每個單位的得主組名（大字）與答案（題組一格並列各小題標籤與答案）、無人搶答標示「無人搶答」、`noValid` 標示「無有效答案」；`Scoreboard` 顯示名次、組名、得分（同分並列顯示相同名次，前三名醒目）；`Projector.tsx` 在 `phase==="Ended"` 並排顯示兩者（寬螢幕左右分欄，窄螢幕上下），其他階段於進度看板旁顯示「目前累計得分」（`scoreboard` 非空時）；字級以 `clamp()` 隨視窗放大，30 題／20 組在 1920×1080 單一畫面不捲動（超出時縮小字級與分欄）；`npx tsc -b` 通過

**Checkpoint**: 結算後得主看板與排行榜可用，與老師／學生結果一致，審核與公平規則連動；US1～US3 可獨立展示

---

## Phase 6: User Story 4 - 斷線重連、房間結束與沒有題目的房間 (Priority: P2)

**Goal**: 斷線時顯示連線狀態並在恢復後還原；房間結束顯示「房間已結束」並保留最後內容；無題目房間只顯示代碼與組別。

**Independent Test**: 搶答中斷開投影電腦網路再恢復，畫面顯示斷線提示後自動還原；老師結束房間後投影顯示「房間已結束」與最後排行榜。

### Tests for User Story 4

- [X] T023 [P] [US4] 新增 `backend/tests/test_projector_closed.py`（使用 `client`、`use_sheet`、`projector_ws`）：(a) 老師結束房間（`/close`）時，已連線投影收到 `status:"Closed"` 的最終 `projector_state`（保留最後的 `phase`、`result`、`scoreboard`）後連線被關閉（`1000`）；(b) 閒置逾時結束同樣送出最終狀態；(c) 房間 `Closed` 但仍在保留期內，新連線收到 `status:"Closed"` 狀態後被關閉，內容與關閉前相同；(d) 超過保留期（房間已被清除）等同不存在，回 `projector_unavailable`；(e) **無題目房間**：開投影得到代碼與組別、`questions==[]`；搶答流程不拋例外；(f) 重新連線（模擬斷線）在任何階段都取得當下整份正確狀態，不依賴先前連線

### Implementation for User Story 4

- [X] T024 [US4] 修改 `backend/app/services/rooms.py`、`backend/app/realtime.py`、`backend/app/api/ws.py`：(a) `rooms.close_room` 在設定 `Closed` 後、關閉連線之前先 `await projector.publish(room)`（`status:"Closed"`）；(b) `Realtime.close_room_connections` 同時關閉該房間的投影連線（`1000`）；(c) `/ws/projector` 對已 `Closed` 的房間：送出 `Closed` 狀態後 `close_safe(ws, 1000)` 並不登記；使 T023 通過
- [X] T025 [US4] 修改 `frontend/src/pages/Projector.tsx`（並視需要調整 `frontend/src/index.css`）：(a) 以 `useReconnectingSocket` 的狀態在非 `open` 時於畫面頂端顯示醒目的「連線中斷，重新連線中」橫幅，恢復後移除並以收到的整份狀態覆蓋（不保留過期內容為「最新」）；(b) `state.status==="Closed"` 時顯示「房間已結束」橫幅並保留最後的得主看板與排行榜，且不再重連（關閉碼 `1000` 加入 `noReconnectCodes`）；(c) 無題目房間（`questions` 為空）只顯示房間代碼與組別、不顯示看板；(d) 載入中顯示「連線中…」；`npx tsc -b` 通過

**Checkpoint**: 投影視圖在斷線、房間結束、無題目情境下行為正確；US1～US4 全部可獨立展示

---

## Phase 7: Polish & Cross-Cutting

- [X] T026 [P] 比對 `diagrams/class.puml`、`diagrams/component.puml`、`diagrams/sequence.puml` 與實作（`Room.projectorKey`、`ProjectorView`／`GroupScore` 欄位與計算、投影服務為唯讀通道與觸發事件、搶答中不含組名與答案、`countdown` 為一次性且不補播、房間結束送最終狀態）；不一致時修正程式或更新圖表，並執行 `java -jar plantuml.jar -charset UTF-8 -tpng diagrams/*.puml`（無 Graphviz 時加 `-Playout=smetana`）重新產圖（Constitution VI 實作後驗證）
- [X] T027 [P] 更新 `README.md`（使用方式）：補上「老師端房間代碼區的『開啟投影視圖』與『複製投影網址』；投影網址只含唯讀憑證、不含老師憑證；投影畫面放大且沒有任何控制按鈕；開始搶答時播放倒數動畫（純視覺，不延後學生端開放）；搶答中只顯示匿名進度，結算後顯示各題得主與累計得分排行榜（與學生結果一致、含審核與讓位後的結果）；斷線自動重連、房間結束顯示『房間已結束』；尚未提供：音效、輪播、主題、憑證作廢、排行榜圖片匯出』」；確認 `specs/012-projector-view/quickstart.md` 與實作一致
- [X] T028 執行完整驗證：`cd backend && uv run pytest`（全數通過，既有 340 個測試**不需修改**）、`cd frontend && npx tsc -b`、`npm run build`、`npm run lint`（警告數不得多於修改前的基準 16）；**畫面流程**以示範後端驗證（仿 Step 10／11：本機測試伺服器使用記憶體假試算表並提供已建置的前端），在瀏覽器逐項走 `quickstart.md` 情境 1～16（開啟投影視圖與無控制項檢查、倒數動畫與匿名進度、重新整理不重播、結算看板與排行榜、審核更新、第二輪累計、斷線還原、房間結束、無法顯示、無題目房間、減少動態效果、30 題 20 組排版）；以 DevTools 或腳本確認搶答中投影收到的訊息不含組名與答案

---

## Dependencies & Execution Order

- **Phase 1** → **Phase 2**（T002、T003 → T004；T005、T006 可與 T004 平行）→ **US1（T007～T011）** → **US2（T012～T017）** → **US3（T018～T022）** → **US4（T023～T025）** → **Polish（T026～T028）**。
- 使用者故事之間在程式碼上依序疊加（同檔案：`projector.py`、`ws.py`、`Projector.tsx`），建議依 P1→P2 順序實作；每個故事完成後都是可獨立展示的增量。
- 測試先於對應實作：T007 先於 T008～T009；T012、T013 先於 T014～T015；T018、T019 先於 T020～T021；T023 先於 T024。
- 後端與前端任務可平行：T006 與 T004／T005；T016 與 T014／T015；T022 與 T020／T021（前端只依契約）。

### Parallel Example（Phase 2）
```text
T002 → T003 → T004（models → realtime → projector 骨架）
T005（conftest 輔助）、T006（前端型別）可與 T004 同時進行
```

## Implementation Strategy

- **MVP**＝Phase 1～3（US1）：老師可開啟唯讀、放大、無控制項的投影視圖並顯示代碼與組別，錯誤憑證被一致拒絕——已能在大螢幕展示並驗證安全邊界。
- **增量 1**＝US2：倒數動畫與匿名進度（保密風險最高，測試先行）。
- **增量 2**＝US3：得主看板與累計得分排行榜（驗證效果的核心展示，重用既有有效結果）。
- **增量 3**＝US4：斷線、房間結束、無題目的穩健性。
- 每個階段結束時既有 340 個測試必須仍全數通過；不修改任何既有測試。
