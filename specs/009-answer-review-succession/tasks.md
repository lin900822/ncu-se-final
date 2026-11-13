# Tasks: 老師端人工審核與順位遞補

**Input**: `/specs/009-answer-review-succession/` 下的 plan.md、spec.md、research.md、data-model.md、contracts/、quickstart.md
**Prerequisites**: plan.md、spec.md（皆已備齊）；Step 1～8 已實作完成（現有 168 個後端測試通過）
**Tests**: 依 plan.md 的 Testing 與 Constitution（原則 II 原始資料不變與併發重複、III 被駁回者不外洩、IV 審核與稽核、V 匯出核對）加入 pytest；真實畫面以 quickstart.md 手動驗證
**Format**: `- [ ] T### [P?] [Story?] 描述（含檔案路徑）`；`[P]` = 可平行（不同檔案、無未完成相依）

> 使用者故事對應：US1＝老師駁回第一名的錯誤答案、由次順位遞補（P1）、US2＝全班結果看板同步更新（P1）、US3＝老師端清楚看到審核狀態與可操作範圍（P1）、US4＝誤按可恢復、稽核紀錄與匯出（P2）
>
> 名詞：**搶答單位 unit_id**＝題組 id（如 `B1`）或題目 id（如 `1`、`1-2`），即 `bundles.unit_of(room, question_id)`。**不修改 `Submission`**（答案、`submitted_at`、`seq`、`rank` 永不改寫）。**不新增依賴、不新增學生訊息型別**。
>
> 與 plan 的差異：為避免 `results.py` 與 `review.py` 循環匯入，純推導函式放在新檔 `backend/app/services/effective.py`（只匯入 `..models` 與 `bundles`），`review.py` 只放驗證寫入與廣播。

## Phase 1: Setup

- [X] T001 執行 `cd backend && uv run pytest` 與 `cd frontend && npx tsc -b`（於 `frontend/` 內 `nvm use`），確認 Step 1～8 基準全數通過（預期後端 168 個測試）後才開始；記下通過的測試數。本步驟不新增任何依賴

---

## Phase 2: Foundational（阻擋所有故事的共用基礎）

**⚠️ 完成前不得開始任何使用者故事**；完成後既有 168 個測試必須仍全數通過（沒有任何審核時，行為與 Step 8 完全相同）

- [X] T002 修改 `backend/app/models.py`：(a) 新增 `@dataclass ReviewRecord`：`round: int`、`unit_id: str`、`group_name: str`、`normalized_name: str`、`action: Literal["Invalid", "Valid"]`、`reason: str`（必填，`strip()` 後非空、**≤ 100 字元**，保存原文）、`reviewed_at: datetime`（後端 UTC）、`by: str = "Teacher"`；docstring 註明僅追加、不修改、不刪除；(b) `Room` 新增 `reviews: list[ReviewRecord] = field(default_factory=list)`；(c) `_ERRORS` 新增 `"REVIEW_NOT_ALLOWED": ("目前不開放審核，請於搶答結束後審核最新一輪", 400)`、`"REASON_REQUIRED": ("請填寫理由", 400)`、`"REASON_TOO_LONG": ("理由最多 100 字元", 400)`、`"UNIT_NOT_FOUND": ("找不到該題或題組", 400)`、`"REVIEW_TARGET_NOT_FOUND": ("找不到該組在此題的送出", 400)`。`Submission` **不得修改**
- [X] T003 新增 `backend/app/services/effective.py`（只匯入 `..models` 與 `from . import bundles`；**純函式、唯讀、不得 await**；模組 docstring 註明：有效狀態與遞補後名次由「原始名次＋審核紀錄」推導、不另存）：(a) `review_state(room, round_no) -> dict[tuple[str, str], ReviewRecord]`：走訪 `room.reviews` 中該輪的紀錄，鍵為 `(normalized_name, unit_id)`，值為**最後一筆**紀錄；(b) `invalid_keys(room, round_no) -> set[tuple[str, str]]`：`review_state` 中 `action == "Invalid"` 的鍵；(c) `unit_entries(room, round_no) -> dict[str, list[Submission]]`：本輪送出依搶答單位分組，**每個組別在每個單位只留一筆**（題組取題目順序最前的成員），各單位內依原始 `rank` 由小到大排序；(d) `effective_winners(room, round_no) -> dict[str, Submission | None]`：每個單位取第一個不在 `invalid_keys` 的送出，全部無效為 `None`；(e) `succession_ranks(room, round_no) -> dict[tuple[str, str], int]`：鍵 `(unit_id, normalized_name)`，排除無效者後依原始名次由 1 起連續編號（無效者不在字典中）；(f) `review_public(r: ReviewRecord) -> dict`：`{"round","unitId","group","action","reason","by","reviewedAt"}`（`action` 轉為 `"invalid"`／`"valid"`，`reviewedAt` 用 `models.iso()`）
- [X] T004 修改 `backend/app/services/results.py` 的 `build_result`：改由 `effective.effective_winners(room, room.round)` 取各單位有效第一名；每題（依 `room.questions` 順序）：`winnerGroup` 為該題所屬單位有效第一名的 `group_name`、`answer` 為**該組在這一題**的答案（以 `room.submission_index[(room.round, normalized_name, question_id)]` 取得，題組成員各自的答案）；沒有有效答案則兩者皆為 `None`。輸出格式與 Step 6 完全相同（本任務**不**加 `noValid`，留待 US2 的 T018）；仍只在 `phase == "Ended"` 回傳。更新模組 docstring：結果由「有效第一名」推導
- [X] T005 修改 `backend/app/services/ranking.py` 的 `build_board`：(a) 每題 `ranking[]` 的每筆新增 `"answer"`（該題答案）、`"status"`（`"Valid"`／`"Invalid"`）、`"successionRank"`（有效者為 `effective.succession_ranks` 的值，無效者為 `None`）、`"reason"`（`effective.review_state` 中該 `(組別, 單位)` 最後一筆的理由，沒有為 `None`）；原有 `rank`、`group`、`submittedAt` **不變**；(b) 每題 `leader` 改為有效第一名的組名（沒有有效答案為 `None`）；(c) `leadTally` 依有效第一名計算（仍以題目為單位，N 題題組計 N 題）；(d) `submittedCount`、`bundleId` 不變。更新模組 docstring。沒有任何審核時輸出與 Step 8 相同（除新增欄位外）
- [X] T006 修改 `backend/app/services/rooms.py` 的 `snapshot()`：`room` 新增 `"reviews": [effective.review_public(r) for r in room.reviews]`（所有輪次、依時間先後）；`board`、`result` 已為審核後推導結果
- [X] T007 [P] 修改 `backend/tests/conftest.py`：新增 `post_review(client, code, token, unit_id, group, action, reason, round_no=None)`：`POST /api/rooms/{code}/reviews`（有 `token` 時帶 `Authorization: Bearer`），本文 `{"round": round_no 或 目前房間輪次, "unitId", "group", "action", "reason"}`，回傳 response；新增 `make_ranked_room(client, bundles=(), groups=("第 1 組","第 2 組","第 3 組"), end=True)`：建立含題目的房間、各組加入、**由第 1 組開始依序**對 Q1 送出（答案 `ans-<組序>`）、必要時以 `end=True` 結束搶答，回傳 `(code, token, connections)`（`connections` 為各組 `(context manager, ws)` 清單，呼叫端負責關閉）
- [X] T008 [P] 修改 `frontend/src/lib/api.ts`：新增並 `export` 型別 `ReviewItem = { round: number; unitId: string; group: string; action: 'invalid' | 'valid'; reason: string; by: string; reviewedAt: string }`；新增並 `export` `async function reviewSubmission(code: string, token: string, body: { round: number; unitId: string; group: string; action: 'invalid' | 'valid'; reason: string }): Promise<{ changed: boolean }>`：`POST /api/rooms/${code}/reviews`，標頭 `Authorization: Bearer <token>` 與 `Content-Type: application/json`，沿用既有 `request()` 與 `ApiError`（憑證**只放標頭**）

**Checkpoint**: 有效結果與看板由推導函式產生、`snapshot` 帶 `reviews`、測試輔助與前端 API 就緒；`uv run pytest` 168 個測試仍全數通過、`npx tsc -b` 通過

---

## Phase 3: User Story 1 - 老師駁回第一名的錯誤答案，由次順位遞補 (Priority: P1) 🎯 MVP

**Goal**: 搶答結束後，老師在結果面板駁回 Q1 第一名答案（填理由、按「確認駁回」），Q1 結果自動遞補給原本第二順位。

**Independent Test**: 第 1、2、3 組依序送出 Q1，搶答結束後駁回第 1 組的 Q1：老師端 Q1 結果變成第 2 組，第 1 組的原始名次與答案仍留在紀錄中；再駁回第 2 組則變第 3 組；三組皆駁回則顯示無有效答案。

### Tests for User Story 1

- [X] T009 [P] [US1] 新增 `backend/tests/test_review.py`（使用 `use_sheet`、`make_ranked_room`、`make_bundle_room`、`post_review`、老師 WebSocket `snapshot`，必要時 `from .test_submission_privacy import flush`）：(a) 第 1、2、3 組依序送 Q1，駁回第 1 組 → `200`、`changed == true`，老師 `snapshot.room.result` 的 Q1 `winnerGroup == "第 2 組"` 且 `answer` 為第 2 組答案；(b) 再駁回第 2 組 → Q1 為第 3 組；再駁回第 3 組 → `winnerGroup`、`answer` 皆為 `null`；(c) 只駁回第 2 名 → 第一名不變；之後駁回第 1 名 → 略過第 2 名由第 3 名遞補；(d) 看板：被駁回筆 `status == "Invalid"`、`successionRank is None`、`reason` 為所填理由，其後各筆 `successionRank` 依序前移（原第 2 名為 1），`leader` 為有效第一名，`leadTally` 隨之更新（N 題題組計 N 題）；(e) 題組：`make_bundle_room`，兩組先後整組送出 Q3+Q4，以題組 id `"B1"` 駁回第 1 組 → Q3、Q4 的結果**同時**改為第 2 組且各自帶該組答案；以成員題 id `"3"` 審核 → `400`、`UNIT_NOT_FOUND`；(f) 理由為 `""`、`"   "` → `REASON_REQUIRED`；101 字元 → `REASON_TOO_LONG`；100 字元可成功；以上失敗時 `room.reviews` 長度不變；(g) **原始資料不變**：審核前後 `room.submissions` 逐筆的 `answer`、`submitted_at`、`seq`、`rank` 完全相同（深度比較）；(h) 成功時追加一筆 `ReviewRecord`：`action == "Invalid"`、`reason`、`group_name`、`unit_id`、`round`、`by == "Teacher"`、`reviewed_at` 為後端 UTC（與送出時間來源相同格式）
- [X] T010 [P] [US1] 新增 `backend/tests/test_review_property.py`（直接以服務層，仿 `test_bundle_concurrency.py` 的 `_room` 寫法建立房間與送出，不經 HTTP）：以固定亂數種子產生**至少 100 組**隨機序列（每組：3～6 個組別對同一單位送出，隨機穿插 `invalid`／`valid` 動作與理由，經 `review.apply_review`），每步之後斷言：(a) `effective_winners` 的第一名等於「原始名次最前且目前未被駁回者」（以獨立的簡單實作重算比對）；(b) `succession_ranks` 為排除無效者後由 1 起連續編號、無效者不在其中；(c) 重複動作回 `changed == False` 且 `len(room.reviews)` 不變；(d) `room.submissions` 的 `rank`、`seq`、`answer` 全程不變（SC-003、SC-006）。含題組單位的情境各至少 20 組

### Implementation for User Story 1

- [X] T011 [US1] 新增 `backend/app/services/review.py`（匯入 `..models`、`from . import bundles, effective, rooms`、`..normalize`）：`apply_review(room, *, round_no, unit_id, group, action, reason) -> tuple[ReviewRecord | None, bool]`，**整段同步、不得 await**，依 research D4 順序驗證且**任一失敗都在寫入前丟出、不留下任何紀錄**：(1) `room.status != "Open"` → `ROOM_CLOSED`；(2) `room.phase != "Ended"` 或 `round_no != room.round` → `REVIEW_NOT_ALLOWED`；(3) `action` 不是 `"invalid"`／`"valid"` → `BAD_REQUEST`；(4) `unit_id` 既不是 `room.bundles` 的 id 也不是 `room.questions` 中**未綁定題組**的題目 id（題組成員題 id 視為不存在）→ `UNIT_NOT_FOUND`；(5) 以 `normalize.normalize_group_name(group)` 在 `effective.unit_entries(room, room.round)[unit_id]` 找該組，找不到 → `REVIEW_TARGET_NOT_FOUND`；(6) `reason` 非字串或 `strip()` 為空 → `REASON_REQUIRED`、長度（以 `strip()` 後計）> **100** → `REASON_TOO_LONG`；(7) 重複判斷：目前狀態（該鍵最後一筆動作，無紀錄視為 Valid）已等於目標 → 回傳 `(該鍵最近一筆紀錄 或 None, False)`，**不新增**、不呼叫 `rooms.touch`；(8) 否則追加 `ReviewRecord(round=room.round, unit_id, group_name=該組顯示名稱, normalized_name, action="Invalid"/"Valid", reason=reason.strip(), reviewed_at=models.utcnow())` 到 `room.reviews`，呼叫 `rooms.touch(room)`，回傳 `(record, True)`。使 T009、T010 通過
- [X] T012 [US1] 修改 `backend/app/api/rooms.py`：新增 `class ReviewBody(BaseModel)`（`round: int`、`unitId: str`、`group: str`、`action: str`、`reason: str`）與 `@router.post("/{code}/reviews")`（參數 `authorization: str | None = Header(default=None)`）：`room = rooms.verify_teacher(code, _bearer(authorization))`（**憑證只讀標頭**）→ `record, changed = review.apply_review(room, round_no=body.round, unit_id=body.unitId, group=body.group, action=body.action, reason=body.reason)` → 回傳 `{"changed", "round", "unitId", "group", "action", "reviewedAt"}`（`changed == False` 且沒有紀錄時省略 `reviewedAt`，`action` 回傳目前狀態對應的 `invalid`／`valid`）→ `changed == True` 時 `await review.publish_review(room)`。並在 `backend/app/services/review.py` 新增 `async def publish_review(room)`：對老師廣播 `{"type": "review_updated", "round": room.round, "board": ranking.build_board(room), "reviews": [effective.review_public(r) for r in room.reviews], "result": {"round", "results"}（取 `results.build_result(room)`）}`，**只經 `realtime.broadcast_to_teachers`**（學生廣播留待 US2 的 T017）。契約見 `contracts/rest-api.md`、`contracts/websocket.md`
- [X] T013 [P] [US1] 新增 `frontend/src/components/ReviewForm.tsx`：props `{ action: 'invalid' | 'valid'; onSubmit: (reason: string) => Promise<void> | void; onCancel: () => void; busy?: boolean }`；顯示常用理由快速選取按鈕（`答案錯誤`、`亂填`、`錯字`，點擊把文字填入理由欄）與一個文字輸入（`maxLength={100}`，顯示剩餘字數）；理由 `trim()` 為空時「確認駁回」（`action === 'valid'` 時為「確認恢復」）按鈕停用；`busy` 時按鈕停用並顯示「處理中…」（防連點）；理由輸入即為確認步驟，**不再另跳二次確認**；另有「取消」按鈕。React 預設跳脫輸出，不使用 `dangerouslySetInnerHTML`
- [X] T014 [US1] 修改 `frontend/src/components/RankingBoard.tsx`：(a) 擴充型別：`BoardRank` 新增 `answer: string`、`status: 'Valid' | 'Invalid'`、`successionRank: number | null`、`reason: string | null`；(b) 每筆名次列顯示答案、狀態（`已駁回` 以刪除線與淡色）、遞補後名次（有效者顯示「遞補後第 N」，與原始名次不同時才顯示）、已駁回者顯示理由；題組卡片的每筆列出各成員題的答案（以 `board.questions` 中同 `bundleId` 的成員 `ranking` 依組別對應）；(c) 新增選填 props `canReview?: boolean`、`round?: number`、`onReview?: (b: { round: number; unitId: string; group: string; action: 'invalid' | 'valid'; reason: string }) => Promise<void>`；`canReview` 為真時，有效筆旁顯示「駁回/無效」、已駁回筆旁顯示「恢復有效」，點擊後在該筆下方展開 `ReviewForm`，送出呼叫 `onReview`（`unitId` 為題組卡片的 `bundleId` 或單題的 `questionId`）並在失敗時於該筆下方顯示錯誤訊息；(d) 目前的有效第一名以醒目樣式標示。`npx tsc -b` 通過
- [X] T015 [US1] 修改 `frontend/src/pages/TeacherRoom.tsx`：(a) 新增狀態 `reviews: ReviewItem[]`；`snapshot` 事件設定 `reviews = room.reviews ?? []`（型別補 `reviews?: ReviewItem[]`）；(b) 新增 `case 'review_updated'`：以訊息整份覆蓋 `board`、`reviews`、`result`；(c) 新增 `onReview(b)`：呼叫 `reviewSubmission(session.code, session.teacherToken, b)`，捕捉 `ApiError` 且 `code === 'UNAUTHORIZED'` 時 `clearTeacherSession()` 並 `setRevoked(true)`（與 Step 8 匯出一致），其他錯誤**拋回**給 `RankingBoard` 顯示於該筆下方；(d) 把 `canReview={roomPhase === 'Ended' && !closed}`、`round={round}`、`onReview` 傳給 `RankingBoard`。`npx tsc -b` 通過

**Checkpoint**: US1 可獨立驗證——老師結束搶答後能駁回、遞補，老師端結果面板即時更新

---

## Phase 4: User Story 2 - 全班結果看板同步更新 (Priority: P1)

**Goal**: 駁回後 2 秒內全班學生結果頁與老師面板一致更新；被駁回者的組名、答案、理由不外洩；重連與晚加入看到審核後結果。

**Independent Test**: 3 個學生視窗停在結果頁，老師駁回 Q1 第一名後，所有視窗 2 秒內顯示 Q1 改由第 2 組取得，遞補組顯示「本組搶下」；重新整理仍相同。

### Tests for User Story 2

- [X] T016 [P] [US2] 新增 `backend/tests/test_review_sync.py`（使用 `make_ranked_room`、`flush`、`post_review`，三組各一視窗、第 3 組另開第二視窗、老師 WebSocket）：(a) 駁回第 1 組的 Q1 後，**每個學生視窗**（含被駁回組、遞補組、他組、同組第二視窗）收到 `{"type":"round_result","round":1,"reviewed":true,"results":[…]}`，Q1 為 `winnerGroup == "第 2 組"` 與其答案，且各視窗內容完全相同；(b) 老師收到 `review_updated`（含 `board`、`reviews`、`result`），其 `result` 與學生收到的 `results` 逐題相同（FR-016）；老師**不**另收 `round_result`；(c) **保密（SC-004）**：被駁回的第 1 組的組名、其答案字串、駁回理由字串，在更新後**所有學生視窗收到的所有訊息**序列化文字中出現 0 次；學生訊息中不含 `review_updated`、`reviews`、`status`、`successionRank`、`reason`、`rank`、`board`；(d) 重複駁回（`changed == false`）→ 學生與老師都**不再收到**任何新廣播；(e) 恢復後學生視窗收到 `round_result`（`reviewed:true`）且 Q1 回到第 1 組；(f) 全部被駁回：該題項目為 `winnerGroup:null`、`answer:null` 且帶 `noValid:true`；從沒有人送出的題目**不帶** `noValid`；(g) 還原：審核後新加入的學生與重新加入的學生，`joined.result` 與廣播的 `results` 完全相同、**沒有** `reviewed` 欄位且不含任何審核資訊；老師以恢復碼回復後 `snapshot.room.reviews` 含完整紀錄、`result`／`board` 為審核後狀態；(h) 學生用 WebSocket 傳 `{"type":"review", ...}`、`{"type":"reviews"}` 被忽略（不寫入、不回傳紀錄）
- [X] T017 [US2] 修改 `backend/app/services/review.py` 的 `publish_review`：在老師廣播之後，對全體學生廣播 `{"type": "round_result", "reviewed": True, **results.build_result(room)}`，**只經 `realtime.broadcast_result`**（內容只有各題有效第一名的組名＋答案，不含被駁回者、理由、名次）；更新 `backend/app/realtime.py` 的 `broadcast_result` docstring：僅限 `round_result`（結算首次公布與老師審核後的更新），每題僅有效第 1 名組名＋答案
- [X] T018 [US2] 修改 `backend/app/services/results.py` 的 `build_result`：當某題所屬單位**本輪有送出但全部被駁回**（`effective_winners` 該單位為 `None` 且 `unit_entries` 該單位非空）時，該題項目另附 `"noValid": True`；沒有任何送出的題目與有有效答案的題目**不帶**此鍵（維持 Step 6 的項目格式）。使 T016(f) 通過
- [X] T019 [P] [US2] 修改 `backend/tests/test_results_privacy.py`：把靜態審核 `test_static_scan_result_channels` 中 `assert users == ["phase.py"]` 改為 `assert sorted(users) == ["phase.py", "review.py"]`，並更新該測試的說明文字：`broadcast_result` 只允許階段服務（首次公布）與審核服務（老師審核後更新）呼叫；同檔 `LEAK` 掃描對「審核後的學生訊息」另加一個測試：駁回後學生收到的訊息不含 `LEAK` 清單中的任何詞（`rank`、`seq`、`board`、`leader`、`leadTally`、`ranking`、`submittedCount`、`submittedAt`）
- [X] T020 [US2] 修改 `frontend/src/components/ResultBoard.tsx`：(a) `ResultItem` 型別新增 `noValid?: boolean`；(b) 單題項目 `winnerGroup === null` 時：`noValid` 為真顯示「本題無有效答案」，否則維持「本題無人搶答」；(c) 題組卡片：成員皆無有效答案時，若任一成員 `noValid` 為真顯示「本題組無有效答案」，否則維持「本題組無人搶答」；(d) 「本組搶下」標示維持依 `winnerGroup === myGroup` 判斷（審核更新後自然隨結果切換）。`npx tsc -b` 通過
- [X] T021 [US2] 修改 `frontend/src/pages/StudentJoin.tsx`：(a) 新增狀態 `resultUpdated: boolean`；`round_result` 事件若 `msg.reviewed === true` 設為 `true`，否則 `false`；`phase_changed` 為 `Answering`（新一輪）、`room_closed`、`resetLocal` 時清為 `false`；`joined` 時設為 `false`（重連不顯示）；(b) 結果頁（`ResultBoard` 上方）在 `resultUpdated` 為真時顯示簡短提示「老師已更新結果」（`role="status"`）；(c) 把 `bundles` 已傳給 `ResultBoard` 的現況維持；(d) **規則公開（FR-022）**：`roomPhase === 'Waiting'`（等待搶答）時，在狀態列下方顯示固定說明「老師可審核答案；答案被判定無效時，名次由次順位組別遞補」；搶答中與結束後不顯示此說明。學生端**不得**顯示被駁回者、理由或任何審核紀錄。`npx tsc -b` 通過

**Checkpoint**: US1＋US2 可獨立驗證——駁回後全班結果同步更新，被駁回者不外洩

---

## Phase 5: User Story 3 - 老師端清楚看到審核狀態與可操作範圍 (Priority: P1)

**Goal**: 只能在搶答結束後審核最新一輪；搶答中、新一輪、房間結束、無權限一律被拒絕且不改變資料；老師畫面清楚呈現可否審核。

**Independent Test**: 搶答中結果面板沒有可用的駁回；結束後每筆出現「駁回/無效」；以學生連線、無憑證、錯誤憑證審核都被拒。

### Tests for User Story 3

- [X] T022 [P] [US3] 新增 `backend/tests/test_review_rules.py`：(a) 時機：`make_ranked_room(end=False)`（搶答中）審核 → `400`、`REVIEW_NOT_ALLOWED`；尚未開始搶答（`Waiting`）同樣被拒；結束後可審核；老師再開始新一輪後以舊 `round`（如 1）審核 → `REVIEW_NOT_ALLOWED`，且 `room.reviews` 長度不變、舊輪既有審核紀錄仍在；新一輪結束後以 `round: 2` 審核成功，只影響第 2 輪的結果；房間結束（`POST /close`）後審核 → `409`、`ROOM_CLOSED`；(b) 權限：無標頭、`Bearer wrong`、`Basic xxx`、只帶房間代碼 → `401`、`UNAUTHORIZED`，結果不變且回應本文不含答案與組名；憑證放網址參數（`?token=`、`?authorization=`）且無標頭 → `401`；老師以恢復碼換裝置後，**舊憑證** → `401`、**新憑證** → `200`；(c) 目標驗證：不存在的 `unitId`、該組在該單位沒有送出（例如第 4 組未送出）、不存在的組名 → `UNIT_NOT_FOUND`／`REVIEW_TARGET_NOT_FOUND`；`action` 為 `"delete"` → `BAD_REQUEST`；以上皆不寫入；(d) 冪等（SC-009）：同一筆連續駁回 2 次 → 第二次 `changed == false`、`room.reviews` 只有 1 筆、遞補只發生一次；對有效筆「恢復」→ `changed == false`；重複 100 次（每次新房間）以「兩個執行緒／`asyncio.gather` 同時呼叫 `review.apply_review`」同一筆駁回 → 紀錄恰 1 筆；(e) 靜態審核：`review` 服務模組只被 `backend/app/api/rooms.py` 匯入（仿 `test_export_auth.py` 的逐行正規表示式掃描，讀檔一律 `read_text(encoding="utf-8")`），`api/ws.py`、`realtime.py`、`services/groups.py`、`services/submissions.py` 不引用 `review`；`ranking.build_board` 仍不出現在任何 `broadcast_to_students|group|other_groups|result` 呼叫附近（沿用既有靜態掃描並確認仍通過）

### Implementation for User Story 3

- [X] T023 [US3] 修改 `frontend/src/components/RankingBoard.tsx` 與 `frontend/src/pages/TeacherRoom.tsx`：(a) `RankingBoard` 新增選填 prop `reviewHint?: string`，在看板上方顯示（`text-sm text-slate-500`）；(b) `TeacherRoom` 依狀態傳入：`closed` 為真 → 「房間已結束，無法再審核（仍可查看與匯出）」；`roomPhase === 'Ended'` → 不顯示提示（可審核）；`roomPhase === 'Answering'` → 「搶答結束後才能審核答案」；`roomPhase === 'Waiting'` 且 `round > 0` → 「請先結束搶答再審核」；(c) `canReview` 為假時 `RankingBoard` **不渲染**「駁回/無效」與「恢復有效」按鈕；(d) 審核請求失敗的錯誤訊息（`REVIEW_NOT_ALLOWED`、`UNIT_NOT_FOUND`、`REVIEW_TARGET_NOT_FOUND`、`REASON_*`）以伺服器訊息顯示於該筆下方，不使整頁進入失效狀態。`npx tsc -b` 通過

**Checkpoint**: US1～US3 可獨立驗證——審核只在正確時機、由正確的人進行

---

## Phase 6: User Story 4 - 誤按可恢復，且每次審核都有完整稽核紀錄與匯出 (Priority: P2)

**Goal**: 可恢復誤按的駁回；每次駁回／恢復都有稽核紀錄且老師端可查看；Step 8 的 CSV 追加審核欄位。

**Independent Test**: 駁回第 1 組後再恢復，Q1 結果回到第 1 組；審核紀錄清單有兩筆；匯出 CSV 中第 1 組那一列狀態為「有效」並帶恢復理由。

### Tests for User Story 4

- [X] T024 [P] [US4] 新增 `backend/tests/test_review_audit.py`：(a) 駁回第 1 組後以 `"valid"` 恢復（理由必填）→ Q1 結果回到第 1 組（依原始名次）、遞補後名次回到原始名次；(b) 駁回→恢復→再駁回：`room.reviews` 依序 3 筆（`Invalid`、`Valid`、`Invalid`），皆含 `round`、`unit_id`、`group_name`、`action`、`reason`、`by == "Teacher"`、遞增的 UTC `reviewed_at`，且**只增不減**（每次操作後長度單調遞增、既有紀錄內容不變）；(c) 恢復不填理由 → `REASON_REQUIRED`；(d) 老師 `snapshot.room.reviews` 與 `review_updated.reviews` 欄位為 `{"round","unitId","group","action","reason","by","reviewedAt"}`，`action` 為小寫 `"invalid"`／`"valid"`；(e) 老師以恢復碼換裝置回復後 `snapshot.room.reviews` 仍是完整歷程（含舊輪）；(f) 新一輪開始後舊輪審核紀錄仍保留且不影響新一輪的結果
- [X] T025 [P] [US4] 新增 `backend/tests/test_review_export.py`（使用 `get_export`、`parse_csv`、`post_review`）：(a) 標題列為 `["輪次","題號","題組","組別","答案","接收時間","排名","審核狀態","遞補後名次","審核理由","審核時間"]`，每列 11 欄；(b) 第 1、2、3 組依序送 Q1，駁回第 1 組（理由 `答案錯誤`）：第 1 組列為 `審核狀態=無效`、`遞補後名次=""`、`審核理由=答案錯誤`、`審核時間` 為 `YYYY-MM-DDTHH:MM:SSZ`，**原始「排名」欄仍為 `1`**；第 2 組為 `有效`、遞補後名次 `1`，第 3 組為 `有效`、遞補後名次 `2`，兩者理由與時間為空；(c) 從未審核的列：`有效`、遞補後名次等於原始排名、理由與時間為空；(d) 駁回後恢復（理由 `誤判`）：第 1 組列為 `有效`、遞補後名次 `1`、理由 `誤判`、時間為該次恢復的時間，其他列遞補後名次回到原始名次；(e) 題組：同一題組各成員列的四個審核欄位彼此相同；(f) 理由以 `=` 開頭（如 `=1+1`）時儲存格以 `'` 開頭（公式防護）；(g) 前七欄內容、排序、列數與審核前完全相同（審核只影響後四欄）

### Implementation for User Story 4

- [X] T026 [US4] 修改 `backend/app/services/export.py`：(a) `COLUMNS` 追加 `"審核狀態", "遞補後名次", "審核理由", "審核時間"`（共 11 欄，前七欄**不變**）；(b) `build_rows` 以 `effective.invalid_keys`／`effective.succession_ranks`／`effective.review_state` 為每個送出（依其所屬單位與組別、輪次）計算：`審核狀態` ＝ `"無效"`（在無效鍵中）或 `"有效"`；`遞補後名次` ＝ 有效者為 `succession_ranks` 的值、無效者為 `""`；`審核理由` ＝ 該鍵最後一筆紀錄的 `reason` 經 `safe_cell`，沒有紀錄為 `""`；`審核時間` ＝ 該紀錄 `reviewed_at` 的 `models.iso()`，沒有為 `""`；注意舊輪（`round` 不等於最新一輪）也要依該輪的審核紀錄計算；(c) 更新模組 docstring（匯出含審核欄位、仍唯讀）。使 T025 通過
- [X] T027 [US4] 更新既有測試以符合十一欄：`backend/tests/test_export.py`（`HEADER` 改為十一欄；原本以 `row[6:]` 取「排名」的斷言改為只取 `row[6:7]`，並確認前七欄內容不變）、`backend/tests/test_export_format.py`（`all(len(r) == 7 ...)` 與 `all(len(row) == 7 ...)` 改為 `== 11`；標題列相等斷言改為十一欄；`test_formula_guard_only_on_group_and_answer_columns` 增加：審核欄位為系統產生的狀態文字，只有「審核理由」套用 `safe_cell`）、`backend/tests/test_export_history.py`（若有逐欄比對只比前七欄）。確認 Step 8 的其餘斷言語意不變
- [X] T028 [US4] 修改 `frontend/src/pages/TeacherRoom.tsx`：新增「審核紀錄」`<section>`（標題「審核紀錄」；放在「本輪送出」之後、「匯出紀錄」之前，**不放在 `closed` 條件內**，房間結束後仍可查看）：`reviews` 為空顯示「尚無審核紀錄」；否則依時間先後列出每筆：本地時間、組別、題目（單位 id 對應 `questions` 的 `label`，題組顯示「題組：Q3、Q4」）、動作（`駁回`／`恢復有效`）、理由（`whitespace-pre-wrap`，安全顯示，不使用 `dangerouslySetInnerHTML`）。`npx tsc -b` 通過

**Checkpoint**: 四個故事皆可驗證

---

## Phase 7: Polish & Cross-Cutting Concerns

- [X] T029 [P] 比對 `diagrams/class.puml`、`diagrams/component.puml`、`diagrams/sequence.puml` 與實作（`ReviewRecord` 欄位、`EffectiveResult` 推導、審核服務的驗證順序與重複判斷、`review_updated`／`round_result.reviewed`／`noValid` 的受眾與內容、`ExportRow` 的四個審核欄位、推導函式放在 `effective.py`）；不一致時修正程式或更新圖表，並執行 `java -jar plantuml.jar -charset UTF-8 -tpng diagrams/*.puml`（無 Graphviz 時加 `-Playout=smetana`）重新產圖（Constitution VI 實作後驗證）
- [X] T030 [P] 更新 `README.md`（使用方式）：補上「搶答結束後，老師在結果面板可對任一筆答案按『駁回/無效』（需填理由），名次由次順位遞補，全班結果即時更新；誤按可『恢復有效』；審核紀錄可在老師端查看，匯出 CSV 含審核欄位；原始答案與名次不會被改動」，並註明「防壟斷上限、重開題目、指定獲勝組別尚未提供」；確認 `specs/009-answer-review-succession/quickstart.md` 與實作一致
- [X] T031 執行完整驗證：`cd backend && uv run pytest`（全數通過，含 Step 1～8 既有測試與更新後的斷言）、`cd frontend && npx tsc -b`、`npm run build`、`npm run lint`（警告數不得多於修改前）；依 `quickstart.md` 手動驗證情境 1～19 逐項走一遍，特別是「搶答中沒有駁回按鈕」「駁回後 3 個學生視窗 2 秒內同步、遞補組顯示本組搶下」「學生開發者工具找不到被駁回組名／答案／理由」「連點或雙視窗駁回只遞補一名」「匯出十一欄」「等待搶答階段顯示規則說明」

---

## Dependencies & Execution Order

### Phase Dependencies

- **Setup (P1)** → **Foundational (P2)** → 使用者故事 → **Polish (P7)**
- US1 為 MVP；US2 依 T011、T012（審核與老師廣播）；US3 的測試與前端提示可在 US1 後進行；US4 依 T003（推導）與 US1 的審核端點
- 後端同檔任務須依序：`results.py`（T004 → T018）；`review.py`（T011 → T012〔`publish_review`〕→ T017）；`api/rooms.py`（T012）；`export.py`（T026）
- 前端同檔任務須依序：`RankingBoard.tsx`（T014 → T023）；`TeacherRoom.tsx`（T015 → T023 → T028）；`StudentJoin.tsx`（T021）；`ResultBoard.tsx`（T020）；`api.ts`（T008）
- 測試同檔：T019 修改既有 `test_results_privacy.py`；T027 修改既有 `test_export*.py`；其餘測試各用新檔，互不衝突

### Within Each Story

- 測試任務（T009、T010、T016、T022、T024、T025）可先寫、先看到失敗
- T002 → T003 → T004、T005、T006；T007、T008 與 T003～T006 可平行（不同檔案）；T013 與 T011、T012 可平行

### Parallel Opportunities

- Foundational：T007、T008 可與 T003～T006 平行
- US1：T009、T010、T013 可平行（不同檔案）
- US2：T016、T019 可平行；T020 與 T017、T018 可平行
- US4：T024、T025 可平行
- Polish：T029、T030 可平行

## Parallel Example: User Story 1

```bash
# 可同時進行（不同檔案）：
Task: "T009 新增 backend/tests/test_review.py"
Task: "T010 新增 backend/tests/test_review_property.py"
Task: "T013 新增 frontend/src/components/ReviewForm.tsx"
# 之後依序：T011 → T012（後端）；T014 → T015（前端）
```

## Implementation Strategy

### MVP First

1. 完成 Phase 1、2（推導、看板／結果改取有效第一名、snapshot 帶審核紀錄、測試輔助、前端 API）
2. 完成 US1（審核端點＋老師端按鈕與理由輸入）→ 老師可駁回並看到遞補
3. 緊接 US2，因為驗證效果要求「全班結果看板同步更新」，需 US1＋US2 才完整

### Incremental Delivery

1. Setup + Foundational → 既有行為不變
2. US1 → 可駁回與遞補（老師端）
3. US2 → 全班同步、保密（Constitution III 測試）、規則公開
4. US3 → 時機與權限邊界、老師端提示
5. US4 → 恢復、稽核紀錄、匯出追加欄位
6. Polish → 圖表一致性、文件、完整驗證
