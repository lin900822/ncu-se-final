# Tasks: 房間建立與學生加入

**Input**: `/specs/001-room-join/` 下的 plan.md、spec.md、research.md、data-model.md、contracts/、quickstart.md
**Prerequisites**: plan.md、spec.md（皆已備齊）
**Tests**: 依使用者指示本階段不撰寫自動化測試；各階段以 quickstart.md 的手動情境驗證。
**Format**: `- [ ] T### [P?] [Story?] 描述（含檔案路徑）`；`[P]` = 可平行（不同檔案、無未完成相依）

## Phase 1: Setup（專案初始化）

- [X] T001 建立 `backend/` 專案：於 `backend/` 執行 `uv init --app --python 3.12`，加入依賴 `fastapi`、`uvicorn[standard]`，產生 `backend/pyproject.toml` 與 `backend/.python-version`，建立空的 `backend/app/__init__.py`、`backend/app/services/__init__.py`、`backend/app/api/__init__.py`
- [X] T002 [P] 建立 `frontend/` 專案：`nvm install 22`，寫入 `frontend/.nvmrc`（內容 `22`），以 Vite 的 react-ts 範本初始化 `frontend/`，安裝 `react-router-dom`、`tailwindcss`、`@tailwindcss/vite`
- [X] T003 [P] 設定 Tailwind v4：於 `frontend/vite.config.ts` 加入 `@tailwindcss/vite` 外掛，並設定開發代理 `/api` → `http://localhost:8000`、`/ws` → `ws://localhost:8000`（`ws: true`）；在 `frontend/src/index.css` 加入 `@import "tailwindcss";` 並於 `frontend/src/main.tsx` 引入
- [X] T004 [P] 新增根目錄 `.gitignore`，忽略 `backend/.venv/`、`__pycache__/`、`frontend/node_modules/`、`frontend/dist/`

---

## Phase 2: Foundational（阻擋所有故事的共用基礎）

**⚠️ 完成前不得開始任何使用者故事**

- [X] T005 [P] 實作 `backend/app/normalize.py`：`normalize_room_code(s)`（去空白、轉大寫）、`clean_group_name(s)`（去前後空白）、`normalize_group_name(s)`（NFKC → 移除所有空白 → casefold）、`validate_group_name(s)`（空白回 `NAME_REQUIRED`；去前後空白後超過 20 字元回 `NAME_TOO_LONG`）
- [X] T006 [P] 實作 `backend/app/models.py`：dataclass `Group`（`name`、`normalized_name`、`online`、`joined_at`）與 `Room`（`code`、`status: Open|Closed`、`created_at`、`last_activity_at`、`teacher_token`、`recovery_code`、`closed_reason: Manual|IdleTimeout|None`、`closed_at`、`groups: dict[normalized_name, Group]`），所有時間為 UTC `datetime`；另定義 `AppError(code, message, http_status)` 與 contracts/rest-api.md 的錯誤碼表（ROOM_NOT_FOUND 404「找不到該房間」、ROOM_CLOSED 409「該房間已結束」、RECOVERY_INVALID 404「恢復碼不正確」、UNAUTHORIZED 401「無權限操作此房間」）
- [X] T007 實作 `backend/app/store.py`：模組層級單例 `Store`，內含 `rooms: dict[str, Room]`、`recovery_index: dict[str, str]`（恢復碼→房間代碼）與 `asyncio.Lock`；提供 `get_room(code)`、`generate_room_code()`（6 碼，字元集為大寫字母與數字並排除 `0 O 1 I L`，碰撞重產）、`generate_recovery_code()`（10 碼，同字元集）、`generate_token()`（`secrets.token_urlsafe(32)`）；資料僅存記憶體，無資料庫（依 T005、T006）
- [X] T008 實作 `backend/app/realtime.py`：連線登記 `Realtime`，維護 `teacher_connections: dict[room_code, set[WebSocket]]` 與 `student_connections: dict[(room_code, normalized_name), WebSocket]`；提供 `broadcast_to_teachers(code, message)`、`send_json_safe(ws, message)`（送出失敗不拋例外）、`close_room_connections(code, reason)`；**不得**提供任何向學生連線廣播他組資料的方法（FR-009）
- [X] T009 實作 `backend/app/main.py` 骨架：建立 `FastAPI` 應用、註冊全域 `AppError` 例外處理器輸出 `{"error": {"code", "message"}}`、預留路由 include 與啟動時背景任務掛載點（依 T006、T007、T008）
- [X] T010 [P] 實作 `frontend/src/lib/api.ts`：`createRoom()`、`recoverRoom(recoveryCode)`、`closeRoom(code, token)` 呼叫 contracts/rest-api.md 的端點，統一解析 `{error:{code,message}}` 為可顯示的錯誤；以 `localStorage` 讀寫老師的 `{code, teacherToken}`（存取皆包 try/catch）
- [X] T011 [P] 實作 `frontend/src/hooks/useReconnectingSocket.ts`：封裝 WebSocket，提供 `onMessage`、`send`、連線狀態（connecting/open/closed）；非預期關閉時以指數退避（1s、2s、4s…上限 10s）自動重連，每次重連成功都呼叫 `onOpen`；支援以回呼指定「不再重連」的關閉碼（如 `4401`、`1008`）
- [X] T012 [P] 實作 `frontend/src/App.tsx` 與 `frontend/src/main.tsx` 路由：`/`（Home）、`/teacher`（TeacherRoom）、`/join`（StudentJoin），以空白頁面佔位；畫面文字一律繁體中文，版面需在手機寬度下可用（Tailwind 響應式）

**Checkpoint**: 後端可啟動（`uv run uvicorn app.main:app`）、前端可啟動（`npm run dev`）且三個路由可切換

---

## Phase 3: User Story 1 — 老師建立房間並取得房間代碼 (Priority: P1) 🎯 MVP

**Goal**: 老師建立房間，看到房間代碼、恢復碼與空的組別清單；可結束房間、可用恢復碼回復；閒置自動結束。

**Independent Test**: quickstart 情境 1、9（恢復碼部分）、10、11：按「建立房間」10 秒內見代碼；重新整理仍在房間；恢復碼可於另一瀏覽器回復並使舊 token 失效。

- [X] T013 [US1] 實作 `backend/app/services/rooms.py`：`create_room()`（產生 code、teacherToken、recoveryCode，`status=Open`，`created_at=last_activity_at=now(UTC)`，登記 recovery_index）；`recover(recovery_code)`（忽略大小寫與空白；不存在 → `RECOVERY_INVALID`；房間已結束 → `ROOM_CLOSED`；成功則換發新 teacher_token，並通知 realtime 對舊 token 的老師連線送 `{"type":"token_revoked"}` 後以 `4401` 關閉）；`verify_teacher(code, token)`（不符 → `UNAUTHORIZED`，房間不存在 → `ROOM_NOT_FOUND`）；`close_room(code, reason)`（`Open→Closed` 不可逆，記錄 `closed_reason`、`closed_at`，冪等；對所有連線送 `{"type":"room_closed","reason":...}` 後關閉）；`touch(code)` 更新 `last_activity_at`（依 T007、T008）
- [X] T014 [US1] 實作 `backend/app/api/rooms.py` 並於 `backend/app/main.py` 註冊：`POST /api/rooms`（201，回 `code`、`teacherToken`、`recoveryCode`、`createdAt`）、`POST /api/rooms/recover`（200，回 `code`、`teacherToken`）、`POST /api/rooms/{code}/close`（Bearer 驗證，200 回 `{"status":"Closed","closedReason":"Manual"}`，重複呼叫仍 200）、`GET /api/rooms/{code}/status`（回 `{"open": bool}`，不含任何組別資料），格式遵循 contracts/rest-api.md（依 T013）
- [X] T015 [US1] 於 `backend/app/main.py` 實作閒置逾時背景任務：啟動時以 `asyncio.create_task` 每 30 秒掃描；對 `Open` 房間，若仍有任何開啟中連線則視為活動並更新 `last_activity_at`，否則 `now - last_activity_at >= 2 小時` 時呼叫 `close_room(code, "IdleTimeout")`；已 `Closed` 且 `closed_at` 超過 24 小時的房間自 store 移除；逾時秒數以環境變數 `ROOM_IDLE_SECONDS`（預設 7200）可覆寫以便驗證 FR-013（依 T013）
- [X] T016 [P] [US1] 實作 `frontend/src/pages/Home.tsx`：「我是老師 — 建立房間」按鈕（呼叫 `createRoom`，把 `{code, teacherToken}` 存入 localStorage 後導向 `/teacher`，並將 `recoveryCode` 傳給老師頁顯示）、「我是學生 — 加入房間」連到 `/join`、「用恢復碼回到老師端」輸入框（呼叫 `recoverRoom`，成功後存新 token 並導向 `/teacher`，錯誤顯示「恢復碼不正確」）（依 T010）
- [X] T017 [US1] 實作 `frontend/src/pages/TeacherRoom.tsx` 基本版：讀取 localStorage 的房間資訊（沒有則導回 `/`）；以大字顯示房間代碼（適合投影）、顯示恢復碼並註明「換裝置時需要，請妥善保存」、顯示空的組別清單與「目前 0 組」、「結束房間」按鈕（需二次確認，呼叫 `closeRoom`，成功後顯示「房間已結束」）（依 T010、T016）

**Checkpoint**: 老師能建房、看到代碼與恢復碼、結束房間；恢復碼可回復。US1 可獨立展示。

---

## Phase 4: User Story 2 — 學生輸入代碼與組名加入房間 (Priority: P1)

**Goal**: 學生輸入代碼與組名後進入等待畫面；錯誤情況有清楚訊息。

**Independent Test**: quickstart 情境 2（學生側）、8：輸入正確代碼與「第 1 組」進入等待畫面；錯誤代碼顯示「找不到該房間」；空白組名顯示「請填寫組名」；房間已結束顯示「該房間已結束」。

- [X] T018 [US2] 實作 `backend/app/services/groups.py` 的 `join(code, name, ws)`：於無 `await` 的臨界區內依序 (1) `normalize_room_code` 後查房間，不存在 → `ROOM_NOT_FOUND`；(2) 房間 `Closed` → `ROOM_CLOSED`；(3) `validate_group_name`（空白 → `NAME_REQUIRED`、超過 20 字元 → `NAME_TOO_LONG`）；(4) 以 `normalize_group_name` 為鍵：不存在則建立 `Group`（`name` 為去前後空白原文、`joined_at=now(UTC)`），存在則為重新連線；(5) 標記 `online=True`、登記 student 連線、`touch(room)`；回傳 `{room.code, group.name, rejoined}`（在線時拒絕的分支於 US4 補齊；依 T005、T006、T007、T008、T013）
- [X] T019 [US2] 實作 `backend/app/api/ws.py` 的 `/ws/student` 並於 `backend/app/main.py` 註冊：`accept` 後等待首則訊息，5 秒內未收到 `join` → 回 `{"type":"error","code":"JOIN_TIMEOUT","message":"加入逾時，請重試"}` 並以 `1008` 關閉；成功回 `{"type":"joined","room":{"code"},"group":{"name"},"rejoined":bool}`；`AppError` 轉為 `{"type":"error","code","message"}` 後以 `1008` 關閉；此連線**不得**收到任何 `snapshot`／`group_*` 事件（依 T018，格式見 contracts/websocket.md）
- [X] T020 [US2] 實作 `frontend/src/pages/StudentJoin.tsx`：表單含「房間代碼」「組名」（`maxLength=20`），送出前前端先擋空白組名並顯示「請填寫組名」；送出後連 `/ws/student` 並送 `join`；收到 `joined` 顯示等待畫面（房間代碼與自己的組名、「已加入，等待老師開始」）；收到 `error` 顯示 `message` 並留在表單；收到 `room_closed` 顯示「該房間已結束」；畫面不顯示任何其他組別資料（依 T011、T019）

**Checkpoint**: 學生可加入並看到等待畫面；錯誤訊息正確。US1+US2 可展示「建房 → 加入」。

---

## Phase 5: User Story 3 — 老師端即時看到已加入的組別 (Priority: P1)

**Goal**: 老師端無需重新整理即顯示所有已加入組別與數量；重新整理或斷線重連後還原。

**Independent Test**: quickstart 情境 2、3、9（清單還原）：老師端開著，學生加入後 2 秒內出現組名與數量；多組各只出現一次；老師重新整理後清單完整。

- [X] T021 [US3] 實作 `backend/app/api/ws.py` 的 `/ws/teacher?token=`：以 `verify_teacher` 驗證，失敗以 `4401` 關閉；房間已結束則送 `room_closed` 後關閉；成功則登記到 `Realtime.teacher_connections`、`touch(room)`，並立即送出完整快照 `{"type":"snapshot","room":{"code","status"},"groups":[{"name","online","joinedAt"}],"count":N}`（`groups` 依 `joined_at` 排序；重連時同樣送快照）；可選接收 `{"type":"ping"}` 僅更新活動時間；斷線時自登記中移除並 `touch`（依 T008、T013）
- [X] T022 [US3] 於 `backend/app/services/groups.py` 的 `join` 成功後，對該房間老師連線廣播：新組別 → `{"type":"group_joined","group":{"name","online":true,"joinedAt"},"count":N}`；既有組別重新連線 → `{"type":"group_status","name","online":true}`（依 T018、T021）
- [X] T023 [US3] 實作 `frontend/src/pages/TeacherRoom.tsx` 的即時清單：以 `useReconnectingSocket` 連 `/ws/teacher?token=...`；收到 `snapshot` 直接以後端資料覆蓋整份清單與數量（不依賴本地狀態），收到 `group_joined` 新增、`group_status` 更新狀態；顯示「目前 N 組」與組名清單（組名以文字節點渲染，避免特殊字元破版，長名稱換行/截斷）；收到 `4401` 或 `token_revoked` 時清除 localStorage 並顯示「身分已失效，請以恢復碼回復」並導回 `/`；收到 `room_closed` 顯示「房間已結束」（依 T011、T017、T021）

**Checkpoint**: 本步驟指定的核心驗證效果達成：老師建房、學生加入、老師端即時列出組名。

---

## Phase 6: User Story 4 — 組別離線與重新加入 (Priority: P2)

**Goal**: 組別離線仍保留並標示；離線後可用同組名回到同一組；在線時拒絕重複加入。

**Independent Test**: quickstart 情境 4、5、6、7：全形組名在線時被拒；關閉分頁後老師端標示離線；再次加入回到同一組且無重複；重新整理學生頁可自動回來。

- [X] T024 [US4] 於 `backend/app/services/groups.py` 的 `join` 補齊在線檢查：同房間同 `normalized_name` 的組別 `online=True` 時 MUST 拒絕並丟出 `GROUP_ONLINE`（訊息「該組目前在線」），不得踢除或取代在線連線、不得更動任何狀態；判定與標記在線須位於同一個無 `await` 的臨界區以確保同時加入只有一方成功（依 T018）
- [X] T025 [US4] 於 `backend/app/services/groups.py` 新增 `disconnect(code, normalized_name, ws)`：僅當該連線仍為登記中的連線時才將 `online=False` 並移除登記（避免舊連線的延遲關閉誤把新連線標成離線）、`touch(room)`，並對老師廣播 `{"type":"group_status","name","online":false}`；組別本身保留於房間中；在 `backend/app/api/ws.py` 的 `/ws/student` 結束（含 `WebSocketDisconnect`、ping 逾時）時呼叫（依 T019、T022）
- [X] T026 [US4] 設定後端 WebSocket ping：於 README 或 `backend/app/main.py` 中固定啟動參數 `--ws-ping-interval 10 --ws-ping-timeout 10`（寫於 README.md 與 quickstart.md，不建立 run.sh），讓異常斷線能在約 20 秒內被判定為離線（依 T025）
- [X] T027 [US4] 於 `frontend/src/pages/StudentJoin.tsx` 補齊重新加入：加入成功後把 `{code, name}` 存入 `sessionStorage`（try/catch）；頁面載入時若存在則自動送出 `join`；若回 `GROUP_ONLINE` 且是自動重新加入，顯示「正在重新連線…」並每 2 秒重試、最多 12 次（約 24 秒，涵蓋心跳偵測異常斷線的時間），仍失敗才顯示「該組目前在線」；WebSocket 非預期斷線時以 `useReconnectingSocket` 自動重連並重送 `join`（依 T020、T024、T011）
- [X] T028 [US4] 於 `frontend/src/pages/TeacherRoom.tsx` 清單項目顯示在線/離線標記（例如綠點「在線」/灰點「離線」，並附文字不僅靠顏色），離線組別仍保留在清單中，數量統計包含離線組別（依 T023）

**Checkpoint**: 全部 4 個故事功能完成。

---

## Phase 7: Polish & Cross-Cutting

- [ ] T029 依 quickstart.md 11 個情境逐一手動驗證，將不符項目回頭修正（含 SC-001~SC-006 的時間與重複組別檢查）
- [X] T030 Constitution VI 一致性檢查：比對 `diagrams/component.puml`、`class.puml`、`sequence.puml` 與程式碼（組件、欄位、流程分支），不一致則修正程式或更新 `.puml`，並執行 `plantuml -tpng diagrams/*.puml` 重新產圖
- [X] T031 [P] 撰寫根目錄 `README.md`：前置需求（nvm、uv）、後端與前端啟動指令、單一 worker 限制與「重啟後房間消失」說明
- [X] T032 [P] 隱私與保密自檢：確認後端不記錄任何學生個資（僅組名）、學生連線無法收到他組資料（檢視 `backend/app/realtime.py` 與 `backend/app/api/ws.py`）

---

## Dependencies & Execution Order

- **Phase 1 → Phase 2 → 使用者故事 → Polish**。Phase 2 完成前不得開始任何故事。
- **US1 (P1)**：僅依賴 Phase 2，為 MVP。
- **US2 (P1)**：依賴 Phase 2 與 T013（`touch`、房間查詢）；可在 US1 後端完成後開始，前端可與 US1 前端平行。
- **US3 (P1)**：依賴 US2 的 `join`（T018）與 US1 的 `TeacherRoom` 基本版（T017）。
- **US4 (P2)**：依賴 US2、US3（擴充同一批檔案）。
- 同檔案任務（`groups.py`、`ws.py`、`TeacherRoom.tsx`、`StudentJoin.tsx`）須依任務編號順序執行，不可平行。

### 故事內順序
models/normalize → store/realtime → services → API/WS → 前端頁面。

## Parallel Opportunities

- Phase 1：T002、T003、T004 可平行（T001 後端與之獨立，亦可平行）。
- Phase 2：T005、T006、T010、T011、T012 可平行；T007 依 T005/T006。
- US1：T016（Home）可與 T013–T015（後端）平行。
- 前後端分工：每個故事的後端任務與前端任務可由不同人同時進行（契約已固定於 `contracts/`）。

```text
# Phase 2 平行範例
T005 normalize.py  |  T006 models.py  |  T010 api.ts  |  T011 useReconnectingSocket.ts  |  T012 路由佔位
```

## Implementation Strategy

1. **MVP（本步驟最小驗證）**：Phase 1 → Phase 2 → US1 → US2 → US3，即可完成「老師建房、學生加入、老師端即時列出組名」的指定驗證效果；到 US3 Checkpoint 即可展示。
2. **增量交付**：US4 補強課堂實務（離線/重新加入/在線衝突），完成後再做 Polish。
3. 每個 Checkpoint 都以 quickstart.md 對應情境手動驗證後再進入下一階段。

---

## Phase 8: Convergence

- [X] T033 在 `frontend/src/pages/Home.tsx` 載入時讀取 `loadTeacherSession()`，若有老師身分則自動導向 `/teacher`（或顯示「回到原房間」按鈕與「建立新房間」並列），使老師關閉後重新開啟同一瀏覽器可自動回到原房間；若房間已結束或憑證失效，`TeacherRoom` 的既有處理（`room_closed`／`4401`）仍須正常運作 per FR-012 (partial)
- [X] T034 讓文件對齊實作：於 `specs/001-room-join/contracts/rest-api.md` 的 `POST /api/rooms/recover` 回應補上 `recoveryCode`；於 `tasks.md` 的 T027 說明改為「自動重試 12 次、間隔 2 秒」，並於 T026 說明改為「啟動參數寫於 README.md 與 quickstart.md，不建立 run.sh」 per plan: contracts (partial)
