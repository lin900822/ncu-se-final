# Tasks: 活動階段同步（開始／結束搶答）

**Input**: `/specs/002-answer-phase-sync/` 下的 plan.md、spec.md、research.md、data-model.md、contracts/、quickstart.md
**Prerequisites**: plan.md、spec.md（皆已備齊）；Step 1（`specs/001-room-join`）已實作完成
**Tests**: 依 plan.md 的 Testing 與 Constitution（原則 III、後端鎖定閘門）加入少量 pytest；其餘以 quickstart.md 手動情境驗證
**Format**: `- [ ] T### [P?] [Story?] 描述（含檔案路徑）`；`[P]` = 可平行（不同檔案、無未完成相依）

> 使用者故事對應：US1＝初始等待且鎖定（P1）、US2＝開始搶答全班解鎖（P1）、US3＝結束搶答全班再鎖定（P1）、US4＝斷線重連還原（P2）

## Phase 1: Setup

- [X] T001 於 `backend/pyproject.toml` 加入開發依賴 `pytest` 與 `httpx`（`uv add --dev pytest httpx`），供 Starlette `TestClient` 使用
- [X] T002 [P] 建立 `backend/tests/__init__.py` 與 `backend/tests/conftest.py`：提供 `client` fixture（`TestClient(app)`，每個測試前清空 `app.store.store.rooms` 與 `recovery_index`、`app.realtime.realtime` 的連線登記），以及 helper `create_room(client)`（回傳 code、teacherToken）與 `join_student(client, code, name)`（開啟 `/ws/student`、送 `join`、回傳 websocket 與 `joined` 訊息）

---

## Phase 2: Foundational（阻擋所有故事的共用基礎）

**⚠️ 完成前不得開始任何使用者故事**

- [X] T003 修改 `backend/app/models.py`：新增 `PhaseChange` dataclass（`phase: Literal["Answering","Ended"]`、`round: int`、`changed_at: datetime`（UTC、後端產生）、`by: str = "Teacher"`）；`Room` 新增欄位 `phase: Literal["Waiting","Answering","Ended"] = "Waiting"`、`round: int = 0`、`phase_log: list[PhaseChange]`（僅追加，預設空 list）；`_ERRORS` 新增 `PHASE_LOCKED`（400，「目前不開放作答」）
- [X] T004 [P] 修改 `backend/app/realtime.py`：新增 `async def broadcast_to_students(self, code: str, message: dict)`，對 `students` 中該房間的所有連線送出；以 docstring 註明「僅限不含組別資料的房間層級訊息（如階段），嚴禁傳入任何組別名稱、草稿、答案或送出狀態」（原則 III / FR-011）
- [X] T005 實作 `backend/app/services/phase.py`（依 T003、T004）：`start_answering(room)`、`end_answering(room)`、`ensure_answering(room)`。
  - 兩個變更函式為 `async`，但狀態更新與 `phase_log` 追加須在**無 `await` 的同步區段**完成，之後才 `await` 廣播。
  - `start_answering`：房間 `Closed` → 拋 `ROOM_CLOSED`；已在 `Answering` → 回傳 `changed=False`（不廣播、不追加紀錄）；否則 `phase="Answering"`、`round += 1`、追加 `PhaseChange`、`rooms.touch(room)`，並對老師與學生廣播 `{"type":"phase_changed","phase","round","changedAt"}`（`changedAt` 為 `iso(utcnow())`；訊息**只含**這三個欄位，FR-011）。
  - `end_answering`：房間 `Closed` → 拋 `ROOM_CLOSED`；非 `Answering` → `changed=False`；否則 `phase="Ended"`、追加 `PhaseChange`、touch、廣播同格式事件。
  - `ensure_answering(room)`：當 `room.status != "Open"` 或 `room.phase != "Answering"` 時拋 `PHASE_LOCKED`。
  - 三者回傳 `(phase, round, changed)` 供 API 使用。
- [X] T006 [P] 修改 `backend/app/services/rooms.py` 的 `snapshot(room)`：`room` 欄位新增 `"phase": room.phase, "round": room.round`
- [X] T007 修改 `backend/app/api/ws.py`（依 T005）：學生 `joined` 回應新增 `"phase": room.phase, "round": room.round`；學生連線迴圈由 `receive_text()` 改為解析 JSON——若 `type == "submit"`：呼叫 `phase.ensure_answering(room)`，失敗時以 `send_json_safe` 回 `{"type":"error","code":"PHASE_LOCKED","message":"目前不開放作答"}` 且**不關閉連線**；`Answering` 時本步驟不儲存、不回應（保留給 Step 3）；其他訊息（含非 JSON）仍只做 `rooms.touch(room)`
- [X] T008 [P] 修改 `frontend/src/lib/api.ts`：新增 `export type RoomPhase = 'Waiting' | 'Answering' | 'Ended'`、`startAnswering(code, token)`、`endAnswering(code, token)`（分別 POST `/api/rooms/{code}/phase/start`、`/phase/end`，帶 `Authorization: Bearer`，回傳 `{ phase: RoomPhase; round: number; changed: boolean }`）

**Checkpoint**: 後端可啟動且既有 Step 1 行為不變；`joined` 與 `snapshot` 已帶階段欄位

---

## Phase 3: User Story 1 - 學生端初始為「等待搶答」且輸入鎖定 (Priority: P1) 🎯 MVP

**Goal**: 學生加入後看到「等待搶答」，輸入框鎖定；後端拒絕鎖定中的送出。

**Independent Test**: 建房、學生加入，不做其他操作：學生畫面顯示「等待搶答」、輸入框無法輸入；以 WebSocket 送 `submit` 得到 `PHASE_LOCKED`。

### Tests for User Story 1

- [X] T009 [P] [US1] 於 `backend/tests/test_phase.py` 新增測試：新房間學生加入後 `joined` 的 `phase == "Waiting"` 且 `round == 0`；學生送 `{"type":"submit"}` 收到 `error` 且 `code == "PHASE_LOCKED"`，並且連線仍開啟（再送一則訊息不會被斷線）

### Implementation for User Story 1

- [X] T010 [US1] 修改 `frontend/src/pages/StudentJoin.tsx`：
  - 將既有頁面狀態型別 `type Phase = 'form' | 'joining' | 'joined' | 'closed'` 改名為 `View`（避免與房間階段混淆）。
  - 新增狀態 `roomPhase: RoomPhase`（預設 `'Waiting'`）與 `round: number`；`joined` 訊息時以 `msg.phase`、`msg.round` 設定。
  - `joined` 畫面新增一個作答輸入框（`<textarea>`，`disabled={roomPhase !== 'Answering'}`）與狀態文字：`Waiting` 顯示「等待搶答」；`Ended` 顯示「搶答已結束」；`Answering` 顯示「搶答中」。
  - 取代原有靜態文字「已加入，等待老師開始」。畫面文字繁體中文，手機寬度可用。

**Checkpoint**: US1 可獨立驗證（quickstart 情境 1、2）

---

## Phase 4: User Story 2 - 老師開始搶答，全班即時解鎖 (Priority: P1)

**Goal**: 老師點「開始搶答」，所有在線學生端即時解鎖；老師端同步顯示搶答中。

**Independent Test**: 學生在等待畫面，老師點「開始搶答」，2 秒內所有學生輸入框解鎖，老師端顯示「搶答中」。

### Tests for User Story 2

- [X] T011 [P] [US2] 於 `backend/tests/test_phase.py` 新增測試：(a) 老師憑證呼叫 `POST /api/rooms/{code}/phase/start` 回 200、`phase == "Answering"`、`round == 1`、`changed == true`；(b) 兩位學生與老師的 WebSocket 皆收到 `phase_changed`，且訊息的鍵集合**恰為** `{"type","phase","round","changedAt"}`（斷言不含任何組別名稱，原則 III）；(c) 重複呼叫 `start` 回 `changed == false`，且沒有新的 `phase_changed`；(d) 無憑證與錯誤憑證回 401；(e) 無任何組別在線時呼叫 `start` 成功，其後才加入的學生 `joined.phase == "Answering"`（Clarification Q1）

### Implementation for User Story 2

- [X] T012 [US2] 修改 `backend/app/api/rooms.py`：新增 `POST /{code}/phase/start`（`rooms.verify_teacher` 驗證憑證後呼叫 `phase.start_answering`，回 `{"phase","round","changed"}`，狀態碼 200；錯誤沿用既有 `AppError` 處理）
- [X] T013 [US2] 修改 `frontend/src/pages/StudentJoin.tsx`：處理 `phase_changed` 訊息，更新 `roomPhase` 與 `round`；`Answering` 時輸入框解鎖（`disabled` 為 false）
- [X] T014 [P] [US2] 修改 `frontend/src/pages/TeacherRoom.tsx`：新增狀態 `roomPhase`（預設 `'Waiting'`）；處理 `snapshot`（讀 `msg.room.phase`）與 `phase_changed`；畫面顯示目前階段文字（「等待搶答」／「搶答中」／「已結束搶答」）；`roomPhase !== 'Answering'` 時顯示「開始搶答」按鈕，點擊呼叫 `startAnswering`（失敗時以既有 `error` 狀態顯示訊息）；房間 `closed` 時按鈕不顯示

**Checkpoint**: US1 + US2 可獨立運作（quickstart 情境 3、8、9、10 的開始部分）

---

## Phase 5: User Story 3 - 老師結束搶答，全班再度鎖定 (Priority: P1)

**Goal**: 老師點「結束搶答」，全班即時鎖定；再次開始時輸入框清空。

**Independent Test**: 搶答中老師點「結束搶答」，所有學生輸入框於 2 秒內鎖定且保留未送出文字；再次開始後輸入框為空白。

### Tests for User Story 3

- [X] T015 [P] [US3] 於 `backend/tests/test_phase.py` 新增測試：(a) `Answering` 時 `POST /phase/end` 回 `phase == "Ended"`、`changed == true`，學生與老師皆收到 `phase_changed`（鍵集合同 T011）；(b) 結束後學生送 `submit` 得 `PHASE_LOCKED`；(c) 重複 `end`、在 `Waiting` 時 `end` 皆為 `changed == false` 且不廣播；(d) 再次 `start` 後 `round == 2`；(e) `room.phase_log` 依序為 Answering(round 1)、Ended(round 1)、Answering(round 2)，每筆 `changed_at` 有值（FR-012）

### Implementation for User Story 3

- [X] T016 [US3] 修改 `backend/app/api/rooms.py`：新增 `POST /{code}/phase/end`（驗證老師憑證後呼叫 `phase.end_answering`，回傳格式同 start）
- [X] T017 [US3] 修改 `frontend/src/pages/StudentJoin.tsx`：`phase_changed` 為 `Ended` 時輸入框鎖定並顯示「搶答已結束」，**保留**輸入框既有文字（FR-010）；僅當收到的 `round` **大於**目前記錄的 `round` 時才清空輸入框（用 `useRef` 記錄 `lastRound`），同輪重連不得清空
- [X] T018 [US3] 修改 `frontend/src/pages/TeacherRoom.tsx`：`roomPhase === 'Answering'` 時顯示「結束搶答」按鈕（點擊呼叫 `endAnswering`，無確認對話框，SC-005），`Waiting`／`Ended` 時顯示「開始搶答」；需與 T014 的按鈕邏輯整合為單一條件判斷

**Checkpoint**: US1–US3 完整循環可運作（quickstart 情境 3–5、10）

---

## Phase 6: User Story 4 - 斷線重連後階段狀態正確還原 (Priority: P2)

**Goal**: 重新整理與斷線重連後，畫面階段一律以後端目前階段為準。

**Independent Test**: 搶答中學生重新整理後仍解鎖；結束時斷線的學生重連後為鎖定；老師重整後階段與按鈕正確。

### Tests for User Story 4

- [X] T019 [P] [US4] 於 `backend/tests/test_phase.py` 新增測試：(a) 搶答中學生關閉連線後重新 `join` 同組名，`joined.phase == "Answering"` 且 `rejoined == true`；(b) 學生離線期間老師呼叫 `end`，該學生重連後 `joined.phase == "Ended"`；(c) 老師 WebSocket 連線取得的 `snapshot.room.phase` 與 `round` 等於目前值；(d) 房間 `close` 後，學生收到 `room_closed`，老師階段 API 回 409 `ROOM_CLOSED`（FR-013）

### Implementation for User Story 4

- [X] T020 [US4] 修改 `frontend/src/pages/StudentJoin.tsx`：WebSocket 非預期中斷（重連中）時將輸入框視為鎖定（以連線狀態 `status !== 'open'` 與 `roomPhase` 共同決定 `disabled`），重新收到 `joined` 後才依後端階段解鎖；`room_closed` 時輸入維持鎖定（既有 `closed` 畫面不顯示輸入框）
- [X] T021 [US4] 修改 `frontend/src/pages/TeacherRoom.tsx`：重連後以 `snapshot.room.phase` 覆蓋 `roomPhase`（不得沿用本地舊值）；房間結束或憑證失效時隱藏階段按鈕

**Checkpoint**: 全部使用者故事可獨立運作

---

## Phase 7: Polish & Cross-Cutting

- [X] T022 執行 `cd backend && uv run pytest`，確認 T009、T011、T015、T019 全數通過
- [X] T023 依 `specs/002-answer-phase-sync/quickstart.md` 手動執行情境 1–12，逐項確認
- [X] T024 [P] 圖表一致性檢查（Constitution VI）：比對 `diagrams/class.puml`、`component.puml`、`sequence.puml` 與程式（`Room.phase`／`round`、`PhaseChange`、`services/phase.py`、開始/結束時序）；不一致時修正程式或更新圖表，並執行 `cd diagrams && plantuml -tpng *.puml`
- [X] T025 [P] 更新 `README.md`：補充階段控制的使用方式（老師開始/結束搶答）與 `uv run pytest` 指令

---

## Dependencies & Execution Order

- Phase 1 → Phase 2 → 使用者故事 → Polish。
- Phase 2 內：T003 → T005；T004 → T005；T005 → T007；T006、T008 與其他任務無檔案衝突可平行。
- US1、US2、US3、US4 在後端上互相獨立（共用 Phase 2）。**前端同檔案任務須循序**：`StudentJoin.tsx`：T010 → T013 → T017 → T020；`TeacherRoom.tsx`：T014 → T018 → T021；`api/rooms.py`：T012 → T016；`tests/test_phase.py`：T009 → T011 → T015 → T019（同檔案，依序追加）。
- 建議故事順序：US1 → US2 → US3 → US4（US3 的清空與 US4 的鎖定行為建立在 US1/US2 的畫面上）。

## Parallel Examples

- Phase 2：T004（realtime.py）與 T006（rooms.py）與 T008（api.ts）可同時進行。
- US2：T012（後端路由）與 T014（老師端畫面）可平行；T013 需等 T010。
- Polish：T024 與 T025 可平行。

## Implementation Strategy

- **MVP**：Phase 1–3（US1）即可驗證「初始等待且鎖定」，但完整價值需 US1–US3（開始/結束循環）。
- **增量交付**：Phase 2 完成後依 US1 → US2 → US3 → US4 逐一完成並以各自 Independent Test 驗證；每個故事結束時跑 `uv run pytest`。
- 圖表一致性（T024）與 Step 1 相同，於實作完成後執行。

---

## Phase 8: Convergence

- [X] T026 修改 `frontend/src/pages/StudentJoin.tsx`：在 `onLeave()` 與 `onSubmit()`（重新送出加入表單）中重設 `lastRound.current = 0` 並呼叫 `setAnswer('')`，確保加入另一個房間時不殘留上一個房間的輸入文字，且新房間的第一輪會觸發清空 per FR-010 (partial)
- [X] T027 於 `backend/tests/test_phase.py` 新增測試：同一房間開 40 條學生 WebSocket 加入後，老師呼叫 `phase/start` 與 `phase/end`，斷言 40 條連線皆收到對應的 `phase_changed`，且從 REST 回應到最後一條收到的耗時 < 2 秒 per SC-002 / SC-003 (partial)
