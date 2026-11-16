# Tasks: 公平機制：獲勝上限與冷卻限制

**Input**: `/specs/011-win-cap-cooldown/` 下的 plan.md、spec.md、research.md、data-model.md、contracts/、quickstart.md
**Prerequisites**: plan.md、spec.md（皆已備齊）；Step 1～10 已實作完成（現有 289 個後端測試通過）
**Tests**: 依 plan.md 的 Testing 與 Constitution（原則 II 確定性與原始資料不變、III 結算前無分配資訊、IV 上限與規則公開）加入 pytest；真實畫面以 quickstart.md 手動驗證
**Format**: `- [ ] T### [P?] [Story?] 描述（含檔案路徑）`；`[P]` = 可平行（不同檔案、無未完成相依）

> 使用者故事對應：US1＝建立房間時設定公平規則、學生活動前就看到（P1）、US2＝達上限後後續題目的首選資格自動讓給下一順位未達標的組別（P1）、US3＝老師端清楚看到讓位狀況、所有畫面與輸出一致（P1）、US4＝冷卻限制（P2）
>
> 名詞：**搶答單位 unit_id**＝題組 id 或題目 id（`bundles.unit_of`）；**單位題數**＝題組成員數（單題為 1）；**申請**＝本輪未被駁回、每組每單位一筆的有效送出（`unit_entries`）；**Outcome**＝`Won`／`Kept`／`Behind`／`Invalid`／`YieldedCap`／`YieldedCooldown`。**不修改** `Submission`、`ReviewRecord`；**不新增依賴、不新增儲存**；除 `joined.fairness`（唯讀規則）外**學生協定不變**。
>
> 實作要點：分配集中在 `backend/app/services/effective.py` 的 `allocate()`，`effective_winners()` 改回傳 `allocate().winners`，所以結果、看板、領先題數、回填、匯出自動一致。

## Phase 1: Setup

- [X] T001 執行 `cd backend && uv run pytest` 與 `cd frontend && npx tsc -b`（於 `frontend/` 內 `nvm use`），確認 Step 1～10 基準全數通過（預期後端 289 個測試）後才開始；記下通過的測試數。本步驟不新增任何依賴

---

## Phase 2: Foundational（阻擋所有故事的共用基礎）

**⚠️ 完成前不得開始任何使用者故事**；完成後既有 289 個測試必須仍全數通過（沒有設定規則時行為與 Step 10 完全相同）

- [X] T002 修改 `backend/app/models.py`：(a) 新增 `@dataclass FairnessRule`：`win_cap: int | None = None`（每組一輪最多搶得幾題，`None`＝不限制）、`cooldown_seconds: int = 0`（`0`＝不套用）；docstring 註明建立房間時確定、之後不可修改、無題目的房間只能是預設值；(b) `Room` 新增 `fairness: FairnessRule = field(default_factory=FairnessRule)`；(c) 新增 `fairness_public(f) -> dict | None`：預設（`win_cap is None and cooldown_seconds == 0`）回傳 `None`，否則回傳 `{"winCap": f.win_cap, "cooldownSeconds": f.cooldown_seconds}`（**不含任何作答內容**）；(d) `_ERRORS` 新增 `"FAIRNESS_INVALID": ("公平規則設定有誤", 400)`
- [X] T003 新增 `backend/app/services/fairness.py`（只匯入 `..models`）：`validate_fairness(questions: list[Question], raw: dict | None) -> FairnessRule`：`raw` 為 `None`、空物件，或 `winCap is None and cooldownSeconds in (None, 0)` → 回傳預設 `FairnessRule()`；取 `winCap`（鍵省略視為 `None`）與 `cooldownSeconds`（省略視為 `0`）；**型別檢查**：兩者若存在必須是 `int` 且**不是 `bool`**，否則 `err("FAIRNESS_INVALID", {"reason": "TYPE"})`；`questions` 為空而規則非預設 → `{"reason": "NO_QUESTIONS"}`；`winCap` 非 `None` 且不在 `1 <= winCap <= len(questions)` → `{"reason": "WIN_CAP_RANGE"}`；`cooldownSeconds` 不在 `0 <= x <= 600` → `{"reason": "COOLDOWN_RANGE"}`；通過回傳 `FairnessRule(win_cap, cooldown_seconds)`
- [X] T004 修改 `backend/app/services/effective.py`（保持純函式、只匯入 `..models` 與 `bundles`）：(a) 新增 `@dataclass Allocation`：`winners: dict[str, Submission | None]`、`status: dict[tuple[str, str], str]`（鍵 `(unit_id, normalized_name)`，值為 Outcome 字串）、`wins: dict[str, int]`（各組取得題數，含 `Kept`）；(b) 新增 `unit_size(room, unit_id) -> int`：題組 id → 成員數（`room.bundles`），否則 `1`；(c) 新增 `allocate(room, round_no) -> Allocation`，依 `data-model.md` 的演算法：以 `unit_entries` 取申請，被駁回者（`invalid_keys`）`status = "Invalid"`；其餘申請依 `Submission.seq` 由小到大排序逐筆判定：單位已有獲勝者 → `"Behind"`；否則呼叫內部函式 `_ineligible(room.fairness, wins, last_win, s) -> str | None`（**本任務先回傳 `None`**，上限與冷卻規則分別於 T014、T023 加入；回傳 `"YieldedCap"` 或 `"YieldedCooldown"` 表示讓位並把該筆 `status` 設為該值、單位保持開放）；符合資格 → `winners[unit] = s`、`status = "Won"`、`wins[組] += unit_size`、`last_win[組] = s.submitted_at`；主判定後，**仍沒有獲勝者**的單位：若有未被駁回的申請，由**原始名次最前者** `status = "Kept"` 並成為獲勝者（`wins[組] += unit_size`）；若全部被駁回，`winners[unit] = None`；(d) `effective_winners(room, round_no)` 改為回傳 `allocate(room, round_no).winners`（簽章與回傳型別不變）；`succession_ranks`、`review_state`、`invalid_keys`、`unit_entries`、`review_public` **不變**。沒有規則時結果與 Step 10 完全相同，既有測試須全數通過
- [X] T005 [P] 修改 `backend/tests/conftest.py`：(a) 新增 `fake_clock` fixture：回傳 `Clock` 物件（欄位 `now`，初始為固定 UTC 時間；方法 `set(seconds)` 把 `now` 設為「基準時間＋seconds 秒」），並以 `monkeypatch.setattr(submissions, "utcnow", lambda: clock.now)` 取代 `app.services.submissions.utcnow`（讓測試控制 `submitted_at` 以驗證冷卻與時間來源）；(b) 新增 `make_fair_room(client, win_cap=None, cooldown=0, bundles=(), groups=("第 1 組", "第 2 組", "第 3 組"), start=True)`：以 `POST /api/rooms` 帶 `sheetUrl`、`fingerprint`、`bundles`、`fairness: {"winCap": win_cap, "cooldownSeconds": cooldown}` 建立房間（斷言 201），讓各組加入（`join_student`），需要時開始搶答，回傳 `(code, token, conns)`，`conns` 為 `{組名: (context manager, ws)}` 字典；(c) 新增 `claim(conns, group, qid, answer)`：以該組 ws 送出單題答案並 `flush`（自 `tests/test_submission_privacy.py`），讓測試可**精確控制送出先後**；`claim_bundle(conns, group, bundle_id, answers)` 同理；(d) 新增 `close_all(conns)` 關閉所有連線
- [X] T006 [P] 修改 `frontend/src/lib/api.ts`：新增並 `export` 型別 `FairnessRule = { winCap: number | null; cooldownSeconds: number }`；`createRoom` 的選項新增 `fairness?: { winCap?: number | null; cooldownSeconds?: number }` 並放進請求本文；建立回應型別新增 `fairness?: FairnessRule | null`；`describeError` 補 `FAIRNESS_INVALID`：依 `details.reason` 顯示（`WIN_CAP_RANGE`＝「每組上限須為 1 到題目數的整數」、`COOLDOWN_RANGE`＝「冷卻秒數須為 0 到 600 的整數」、`TYPE`＝「公平規則欄位格式錯誤」、`NO_QUESTIONS`＝「沒有題目時不能設定公平規則」）

**Checkpoint**: 規則模型、驗證、分配骨架（無規則時行為不變）、測試輔助與前端型別就緒；既有 289 個測試仍全數通過、`npx tsc -b` 通過

---

## Phase 3: User Story 1 - 建立房間時設定公平規則，學生在活動前就看到 (Priority: P1) 🎯 MVP

**Goal**: 老師在預覽頁選填「每組最多搶得 N 題」與「冷卻秒數」；規則隨房間固定；老師端顯示規則；學生在「等待搶答」階段看到規則說明。

**Independent Test**: 老師在預覽頁把上限設為 2 並確認建立房間；老師端顯示「每組最多搶得 2 題」，學生加入後在等待搶答畫面看到同一條規則；房間建立後沒有任何地方能修改。

### Tests for User Story 1

- [X] T007 [P] [US1] 新增 `backend/tests/test_fairness_create.py`（使用 `use_sheet`、`make_fair_room`、`join_student`、老師 WebSocket）：(a) `winCap: 2, cooldownSeconds: 30` 建立成功，建立回應 `fairness == {"winCap": 2, "cooldownSeconds": 30}`；學生 `joined.fairness` 與老師 `snapshot.room.fairness` 完全相同；老師以恢復碼回復後仍相同；(b) 省略 `fairness`、`fairness: null`、`{}`、`{"winCap": null, "cooldownSeconds": 0}` 皆建立成功且回應與 `joined`、`snapshot` 的 `fairness` 皆為 `null`；(c) `winCap` 等於題目數（6）可建立；(d) 無效值回 `400`、`error.code == "FAIRNESS_INVALID"`、`details.reason` 正確，且 `store.rooms` 數量不變：`winCap: 0`、`-1`、`7`（>題目數）→ `WIN_CAP_RANGE`；`cooldownSeconds: -1`、`601` → `COOLDOWN_RANGE`；`winCap: "2"`、`2.5`、`true`、`cooldownSeconds: "30"`、`1.5`、`false` → `TYPE`；(e) 不帶 `sheetUrl`（沒有題目）卻帶 `{"winCap": 1}` 或 `{"cooldownSeconds": 5}` → `NO_QUESTIONS`；不帶規則的無試算表房間仍可建立；(f) 驗證順序：指紋不符（`SHEET_CHANGED`）與題組不合法（`BUNDLES_INVALID`）優先於公平規則錯誤；(g) 房間存續期間規則固定：搶答開始、結束、新一輪後 `joined.fairness` 與 `snapshot.room.fairness` 不變；伺服器沒有任何修改規則的路由（以 `app.routes` 掃描不存在含 `fairness` 的路徑）

### Implementation for User Story 1

- [X] T008 [US1] 修改 `backend/app/services/rooms.py`、`backend/app/api/rooms.py`、`backend/app/api/ws.py`：(a) `rooms.create_room(sheet=None, bundles=None, fairness=None)`：有 `sheet` 時設定 `room.fairness = fairness or FairnessRule()`；`snapshot()` 的 `room` 新增 `"fairness": fairness_public(room.fairness)`；(b) `api/rooms.py`：`CreateBody` 新增 `fairness: dict | None = None`；在**題組驗證之後、建立房間之前**呼叫 `fairness_service.validate_fairness(sheet.questions, body.fairness)`；沒有 `sheetUrl` 卻帶非預設規則時，`validate_fairness([], body.fairness)` 會丟 `NO_QUESTIONS`；建立回應新增 `"fairness": fairness_public(room.fairness)`；(c) `api/ws.py` 學生 `joined` 新增 `"fairness": fairness_public(room.fairness)`（**只含規則兩個數字**）。使 T007 通過
- [X] T009 [P] [US1] 新增 `frontend/src/components/FairnessEditor.tsx`：props `{ questionCount: number; value: { winCap: string; cooldown: string }; onChange: (v) => void; disabled?: boolean }`（字串狀態，空字串＝未設定）；顯示兩個數字輸入：「每組最多搶得 [ ] 題（留空＝不限制）」與「搶得題目後冷卻 [ ] 秒（留空或 0＝不套用）」；即時檢查：上限須為 `1..questionCount` 的整數、冷卻須為 `0..600` 的整數，無效時顯示行內錯誤（`role="alert"`）；匯出純函式 `parseFairness(value, questionCount) -> { ok: true; rule: { winCap: number | null; cooldownSeconds: number } } | { ok: false }` 供預覽頁使用。`npx tsc -b` 通過
- [X] T010 [US1] 修改 `frontend/src/pages/Home.tsx`：新增狀態 `fairness: { winCap: string; cooldown: string }`（預設皆空字串）；在 `BundleEditor` 之後渲染 `FairnessEditor`（`questionCount = preview.questions.length`）；重新讀取或改連結時清空；`parseFairness` 結果 `ok === false` 時**禁用**「確認建立房間」；確認建立時 `createRoom({ sheetUrl, fingerprint, bundles, fairness: parsed.rule })`；伺服器回 `FAIRNESS_INVALID` 時顯示 `describeError` 的訊息並**保留預覽**（不離開預覽頁）。`npx tsc -b` 通過
- [X] T011 [US1] 修改 `frontend/src/pages/StudentJoin.tsx`：`joined` 事件保存 `fairness`（`FairnessRule | null`，狀態 `fairness`；`room_closed`／離開時清除）；在 `roomPhase === 'Waiting'` 且 `fairness !== null` 時，於狀態列下方（既有的 Step 9 審核說明旁）顯示規則說明：有上限 →「每組最多搶得 {winCap} 題；達上限後，其後的題目會讓位給其他組別」；有冷卻（`cooldownSeconds > 0`）→「搶得一題後，{cooldownSeconds} 秒內送出的答案不能再搶得題目」；兩者皆有則兩行並列；搶答中與結束後不顯示。**學生端不得顯示任何分配、名次、獲勝題數或是否達上限**。`npx tsc -b` 通過
- [X] T012 [US1] 修改 `frontend/src/pages/TeacherRoom.tsx`：`snapshot` 事件保存 `fairness`（`room.fairness ?? null`，狀態 `fairness`）；在「房間代碼」區塊下方（題目區塊之前）新增一行規則顯示：`fairness === null` → 不顯示；否則「公平規則：每組最多搶得 {winCap} 題」與（`cooldownSeconds > 0` 時）「・搶得後冷卻 {cooldownSeconds} 秒」；**不提供任何修改入口**。`npx tsc -b` 通過

**Checkpoint**: US1 可獨立驗證——規則可設定、固定、對學生與老師公開（此時規則尚未影響結果）

---

## Phase 4: User Story 2 - 達上限後，後續題目的首選資格自動讓給下一順位未達標的組別 (Priority: P1)

**Goal**: 組別達上限後的送出不能再取得首選資格，該題由原始名次下一順位且尚未達上限的組別取得；全員不符時由名次最前者保留；題組計 N 題；審核會連動重算。

**Independent Test**: 上限 2：第 1 組對 Q1～Q5 都最快送出、第 2 組對 Q3 送出；結算後 Q1、Q2 為第 1 組、Q3 為第 2 組。

### Tests for User Story 2

- [X] T013 [P] [US2] 新增 `backend/tests/test_fairness_allocation.py`（使用 `use_sheet`、`make_fair_room`、`claim`、`claim_bundle`、`post_review`、`close_all`；以 `results.build_result(store.rooms[code])` 與 `effective.allocate` 驗證）：(a) **驗證效果情境**：`win_cap=2`，第 1 組依序最快送出 Q1、Q2、Q3、Q4、Q5，第 2 組送出 Q3，第 3 組送出 Q4，結束搶答 → 獲勝者 Q1＝第 1 組、Q2＝第 1 組、Q3＝第 2 組、Q4＝第 3 組、Q5＝第 1 組（無其他送出者，`Kept`）；Q3 的第 1 組 `status == "YieldedCap"`、第 2 組 `"Won"`；Q5 的第 1 組 `"Kept"`；(b) **讓位順序**：一題原始名次為第 1 組（已達上限）、第 2 組（已達上限）、第 3 組（未達上限）→ 第 3 組取得，前兩組皆 `YieldedCap`；(c) **處理序語意**：同樣三題 Q1～Q3，第 1 組先送 Q3、再送 Q1、最後送 Q2（上限 2），第 2 組各題皆稍後 → 第 1 組取得的是**先送出的兩題**（Q3、Q1），Q2 讓位給第 2 組；(d) **全員不符資格時保留**：上限 1、兩組各取一題後，某題只有這兩組的送出 → 由原始名次最前者 `Kept`，題目不懸空；(e) **審核連動**：`win_cap=1` 時第 1 組最快送出 Q1、Q2，第 2 組送出 Q2；駁回第 1 組的 Q1 → 第 1 組空出名額，Q2 改回第 1 組（原本是第 2 組）；恢復 Q1 → 回到原狀；(f) **被駁回不計入題數**：被駁回的送出不佔用該組的上限名額；(g) **題組**：`bundles=(("3","4"),)`、上限 2：第 1 組先取得 Q1（1 題）再取得題組（取得前 1 < 2，取得後共 3 題，略超過）→ 題組由第 1 組取得且計 2 題，其後任何單位都讓位；題組大於上限（上限 1、題組 2 題）仍可被取得；題組成員 `Q3`、`Q4` 獲勝者永遠相同；(h) **每輪重算**：新一輪開始後各組題數歸零（第二輪第 1 組又可取得兩題）；(i) **向下相容**：不設規則時，`effective.effective_winners`、`results.build_result`、`ranking.build_board` 與 Step 10 的輸出相同，且 `allocate().status` 不含 `YieldedCap`／`YieldedCooldown`／`Kept`；(j) **原始資料不變**：分配前後 `room.submissions` 逐筆（答案、`submitted_at`、`seq`、`rank`）完全相同；(k) **確定性**：同一房間連續呼叫 `allocate` 100 次，`winners` 與 `status` 完全相同
- [X] T014 [US2] 修改 `backend/app/services/effective.py`：實作 `_ineligible()` 的**上限規則**：`rule.win_cap is not None and wins.get(組, 0) >= rule.win_cap` → 回傳 `"YieldedCap"`（取得前題數檢查；取得後才加 `unit_size`，因此題組可略超過上限一次）；其餘情況回傳 `None`（冷卻規則於 T023 加入）。確認 `Kept` 判定在主判定之後、不影響其他單位；確認 `allocate` 對題組以 `unit_size` 累計。使 T013 全部通過、既有 289 個測試仍通過
- [X] T015 [P] [US2] 新增 `backend/tests/test_fairness_property.py`（直接以服務層，仿 `test_review_property.py` 的 `_room`／`_submit_all`，另建可設定 `fairness` 的房間）：(a) 以固定亂數種子產生**至少 100 組**隨機情境（3～6 個組、4～8 個單位含 0～1 個題組、`win_cap` 在 1～題目數間隨機、每組對隨機單位子集以隨機順序送出、隨機穿插 0～3 次 `apply_review` 駁回／恢復），每組情境以**獨立的簡單參考實作**（測試內自行撰寫：依 `seq` 逐筆、單位已有獲勝者則跳過、`wins >= cap` 則跳過、最後保留名次最前者）重算，斷言 `effective.allocate` 的獲勝者與每筆 `status`（`Won`／`Kept`／`Behind`／`YieldedCap`／`Invalid`）與參考實作完全相同；(b) 不變式：每個有未被駁回申請的單位**恰有一個**獲勝者；全部被駁回的單位為 `None`；沒有規則時獲勝者等於舊邏輯（名次最前的未被駁回者）；有其他符合資格者可遞補時，任一組的 `Won` 單位在取得前題數都 `< win_cap`；(c) `Submission` 的答案、`submitted_at`、`seq`、`rank` 全程不變；(d) 規模：40 組 × 50 題 × 3 輪（6000 筆）`allocate` 單輪耗時 < 1 秒

**Checkpoint**: US1＋US2 可獨立驗證——上限生效、讓位、保留、題組、審核連動、確定性

---

## Phase 5: User Story 3 - 老師端清楚看到讓位狀況，所有畫面與輸出一致 (Priority: P1)

**Goal**: 看板顯示各組「x/上限」與每筆送出的狀態；審核連動的題目可見；結果頁、回填、匯出 CSV 全部一致；結算前學生看不到分配資訊。

**Independent Test**: 上限 2 的情境中，進度板顯示第 1 組 2/2、Q3 的第 1 組標示「讓位（已達上限）」、第 2 組「取得」；結果頁、回填後的試算表、匯出 CSV 對 Q3 都是第 2 組。

### Tests for User Story 3

- [X] T016 [P] [US3] 新增 `backend/tests/test_fairness_sync.py`（使用 `make_fair_room`、`claim`、`fake_sheet`〔回填〕、`post_backfill`、`post_review`、老師 WebSocket、學生 ws）：(a) **一致性**：驗證效果情境結算後，老師 `snapshot.room.result`、學生 `round_result`／`joined.result`、`board.questions[].leader`、`board.leadTally`、回填寫入 `fake_sheet` 的內容、匯出 CSV 的「獲勝狀態」，對每一題的獲勝組別與答案**逐題完全一致**（SC-006）；(b) **看板**：`board.fairness == {"winCap": 2, "cooldownSeconds": 0}`；每筆 `ranking[]` 含 `outcome`（`Won`／`Kept`／`Behind`／`Invalid`／`YieldedCap`／`YieldedCooldown`），原有欄位（`rank`、`status`、`successionRank`、`reason`）不變；`leadTally` 的 `leadCount` 為讓位後的題數（題組 N 題計 N）；無規則房間 `board.fairness is None`；(c) **搶答中即時更新**：搶答進行中每次送出後老師收到的 `board` 已反映讓位（第 1 組第三題送出後，該題 `outcome == "YieldedCap"`）；(d) **保密**：搶答進行中所有學生連線收到的訊息序列化後**不含** `outcome`、`YieldedCap`、`YieldedCooldown`、`Kept`、`Behind`、`changedUnits`、`board`、`leadTally`、`winCounts`；學生唯一的公平資訊是 `joined.fairness`（只含 `winCap`、`cooldownSeconds` 兩個鍵）；結算後 `round_result` 的格式與 Step 6 相同（不含上述任何詞）；(e) **`changedUnits`**：`win_cap=1` 的連動情境（第 1 組最快送 Q1、Q2，第 2 組送 Q2）駁回第 1 組 Q1 後，老師收到的 `review_updated.changedUnits == ["2"]`（被審核的 Q1 本身不列入）；沒有連動時為 `[]`；(f) **匯出**：標題列為十三欄（見 T018）；獲勝者「獲勝」且原因空白；被讓位者「未獲勝／已達上限」；被駁回者「未獲勝／被駁回」；名次落後者「未獲勝／名次落後」；`Kept` 獲勝者為「獲勝」且原因空白；舊輪依該輪的規則與審核各自重算；無規則房間的第一名為「獲勝」、其餘有效者為「名次落後」；(g) **回填連動**：審核造成獲勝者改變後再次回填，試算表更新為重新分配後的結果
- [X] T017 [US3] 修改 `backend/app/services/ranking.py`：(a) `build_board` 呼叫 `effective.allocate(room, round_no)`（取代單獨的 `effective_winners`），每筆 `ranking[]` 新增 `"outcome": allocation.status.get((unit, s.normalized_name), "Won")`；(b) 看板頂層新增 `"fairness": fairness_public(room.fairness)`；(c) `leader` 與 `leadTally` 維持由獲勝者推導（因此自動為讓位後結果，題組 N 題計 N）；原有欄位與順序**不變**。更新模組 docstring。使 T016(b)(c) 通過
- [X] T018 [US3] 修改 `backend/app/services/export.py`：(a) `COLUMNS` 在 Step 9 的十一欄之後追加 `"獲勝狀態"`、`"未獲勝原因"`（共 13 欄，前十一欄**不變**）；(b) `build_rows` 對每個出現的輪次各呼叫一次 `effective.allocate(room, round)`，每筆送出依 `(單位, normalized_name)` 取 `status`：`Won`／`Kept` → `獲勝狀態="獲勝"`、`未獲勝原因=""`；其餘 → `"未獲勝"` 並依 `Invalid→"被駁回"`、`YieldedCap→"已達上限"`、`YieldedCooldown→"冷卻中"`、`Behind→"名次落後"`；(c) 更新模組 docstring。使 T016(f) 通過
- [X] T019 [US3] 更新既有測試以符合十三欄：`backend/tests/test_export.py`（`HEADER` 追加兩欄並確認前十一欄內容不變）、`backend/tests/test_export_format.py`（所有 `== 11` 改為 `== 13`、標題列相等斷言改為十三欄；`test_review_columns_only_reason_gets_formula_guard` 確認新增兩欄為系統固定值不需公式防護）、`backend/tests/test_review_export.py`（`HEADER` 與 `all(len(r) == 11 ...)` 改為十三欄，前十一欄的既有斷言不變）、`backend/tests/test_export_history.py`（若有逐欄長度斷言一併更新）。確認 Step 8、9 其餘斷言語意不變
- [X] T020 [US3] 修改 `backend/app/api/rooms.py` 與 `backend/app/services/review.py`：(a) 審核端點在呼叫 `review.apply_review` **之前**以 `{unit: (w.normalized_name if w else None) for unit, w in effective.effective_winners(room, room.round).items()}` 取得 `before`（僅在 `room.phase == "Ended"` 時；否則略過），`changed` 為真後再取 `after`，`changed_units = sorted(unit for unit in after if unit != body.unitId and after[unit] != before.get(unit))`，並以題目順序排序（單位 id 對應 `room.questions` 首次出現的位置）；(b) `review.publish_review(room, changed_units=None)` 新增參數，`review_updated` 訊息新增 `"changedUnits": list(changed_units or [])`；(c) 保持 `apply_review` 簽章**不變**（Step 9 測試直接呼叫）；學生廣播的 `round_result` **不含** `changedUnits`。使 T016(e) 通過
- [X] T021 [US3] 修改 `frontend/src/components/RankingBoard.tsx` 與 `frontend/src/pages/TeacherRoom.tsx`：(a) `RankingBoard` 的 `BoardRank` 新增 `outcome?: 'Won' | 'Kept' | 'Behind' | 'Invalid' | 'YieldedCap' | 'YieldedCooldown'`，`Board` 新增 `fairness?: { winCap: number | null; cooldownSeconds: number } | null`；每筆名次列在既有標籤旁依 `outcome` 顯示：`Won`＝「取得」、`Kept`＝「保留」（醒目樣式並加註「無其他符合資格者」）、`YieldedCap`＝「讓位（已達上限）」、`YieldedCooldown`＝「讓位（冷卻中）」、`Behind`＝「名次落後」、`Invalid`＝沿用既有「已駁回」；(b) 「各組領先題數」區塊在 `board.fairness?.winCap` 非空時改顯示「{組} {leadCount}/{winCap}」，達上限（`leadCount >= winCap`）以醒目樣式標示；看板上方顯示規則一行（`fairness` 非空時）；(c) `TeacherRoom` 新增狀態 `changedUnits: string[]`，`review_updated` 事件設定 `msg.changedUnits ?? []`，`phase_changed` 為 `Answering` 時清空；非空時在看板上方顯示提示「此次審核連動影響：{題號清單}」（單位 id 對應 `questions` 的 `label`，題組顯示「題組：Q3、Q4」）；(d) 看板型別 `Board` 由 `snapshot`／`board`／`review_updated` 整份覆蓋（沿用既有處理）。`npx tsc -b` 通過

**Checkpoint**: US1～US3 可獨立驗證——上限在老師端可見、各處一致、審核連動可見、結算前學生無分配資訊

---

## Phase 6: User Story 4 - 冷卻限制：搶得一題後要間隔一段時間才能再搶 (Priority: P2)

**Goal**: 選用的冷卻秒數：組別每次取得題目後，冷卻秒數內送出的答案沒有資格取得首選資格；只依後端時間；被讓位或被駁回的送出不啟動冷卻。

**Independent Test**: 冷卻 30 秒、無上限：第 1 組 0 秒搶得 Q1、10 秒對 Q2 最快（讓位）、50 秒對 Q3 最快（取得）。

### Tests for User Story 4

- [X] T022 [P] [US4] 新增 `backend/tests/test_fairness_cooldown.py`（使用 `fake_clock`、`make_fair_room(cooldown=30)`、`claim`；以 `fake_clock.set(秒數)` 在每次送出前設定後端時間）：(a) 第 1 組在 0 秒取得 Q1、10 秒對 Q2 最快、50 秒對 Q3 最快、第 2 組在稍後各送出 Q2、Q3 → Q1＝第 1 組、Q2＝第 2 組（第 1 組 `YieldedCooldown`）、Q3＝第 1 組（已過冷卻）；(b) 邊界：恰好相隔 30 秒的送出**符合資格**（`submitted_at - last_win >= cooldown`），相隔 29.9 秒讓位；(c) **被讓位或被駁回的送出不啟動冷卻**：第 1 組 0 秒取得 Q1、10 秒對 Q2 送出（讓位）、35 秒對 Q3 送出 → Q3 符合資格（冷卻從 0 秒起算而非 10 秒）；駁回第 1 組的 Q1 後，其 Q1 不再啟動冷卻、Q2 改為取得；(d) **上限＋冷卻同時生效**：`win_cap=2, cooldown=30`，一筆送出必須「未達上限且已過冷卻」才取得；達上限時原因為 `YieldedCap`（上限優先於冷卻）；(e) **預設不套用**：`cooldown=0` 時行為與只設上限相同，任何狀態都不出現 `YieldedCooldown`；(f) **時間來源**：冷卻只取決於後端記錄的 `submitted_at`——學生送出的訊息帶任何時間欄位（如 `{"clientTime": ...}`）都被忽略且結果不變；(g) **題組**：題組取得時以該次送出的 `submitted_at` 作為 `last_win`；(h) 冷卻在 `Kept` 保留時**不啟動**後續判定（保留發生在主判定之後）；(i) 學生等待搶答階段看到的冷卻說明與 `joined.fairness.cooldownSeconds` 一致

### Implementation for User Story 4

- [X] T023 [US4] 修改 `backend/app/services/effective.py` 的 `_ineligible()`：在上限規則之後加入**冷卻規則**：`rule.cooldown_seconds > 0` 且 `last_win` 中存在該組的上一次取得時間，並且 `(s.submitted_at - last_win[組]).total_seconds() < rule.cooldown_seconds` → 回傳 `"YieldedCooldown"`（上限優先於冷卻：兩者同時成立時回傳 `"YieldedCap"`）；確認只有 `status == "Won"` 的送出會更新 `last_win`（`YieldedCap`、`YieldedCooldown`、`Invalid`、`Behind`、`Kept` 都**不**更新）。使 T022 通過、T013～T016 與既有測試仍通過

**Checkpoint**: 四個故事皆可驗證

---

## Phase 7: Polish & Cross-Cutting Concerns

- [X] T024 [P] 比對 `diagrams/class.puml`、`diagrams/component.puml`、`diagrams/sequence.puml` 與實作（`FairnessRule` 欄位與範圍、`Allocation`／Outcome 六種狀態與判定順序〔先名次落後→上限→冷卻→取得→保留〕、建立房間的驗證順序〔指紋→題組→公平規則〕、`board.fairness`／`outcome` 與 `review_updated.changedUnits` 的受眾、`joined.fairness` 只含規則、CSV 末兩欄）；不一致時修正程式或更新圖表，並執行 `java -jar plantuml.jar -charset UTF-8 -tpng diagrams/*.puml`（無 Graphviz 時加 `-Playout=smetana`）重新產圖（Constitution VI 實作後驗證）
- [X] T025 [P] 更新 `README.md`（使用方式）：補上「建立房間的預覽頁可選填『每組最多搶得 N 題』與『冷卻秒數』（規則建立後固定、學生活動前可見）；達上限後後續題目依原始名次讓位給下一順位未達標的組別；全員不符資格時由名次最前者『保留』；題組計 N 題；老師審核後整輪重新分配，看板會提示連動影響的題目；匯出 CSV 追加『獲勝狀態』『未獲勝原因』；結果、回填與匯出全部採用讓位後的結果；尚未提供：重開題目、指定獲勝組別、跨輪累計』」；確認 `specs/011-win-cap-cooldown/quickstart.md` 與實作一致
- [X] T026 執行完整驗證：`cd backend && uv run pytest`（全數通過，含 Step 1～10 既有測試與更新後的欄位數斷言）、`cd frontend && npx tsc -b`、`npm run build`、`npm run lint`（警告數不得多於修改前）；**畫面流程**以示範後端驗證（仿 Step 10：本機測試伺服器使用記憶體假試算表取代 Google 讀寫並提供已建置的前端），逐項走 `quickstart.md` 情境 1～9、11～13（預覽頁欄位檢查與禁用確認、規則顯示與學生說明、上限讓位與保留、審核連動提示、冷卻、無規則房間、重新整理與換裝置還原；情境 10 的回填以假試算表驗證結果一致）；**真實 Google 試算表的回填驗證請老師依 Step 10 的 quickstart 手動進行**

---

## Dependencies & Execution Order

### Phase Dependencies

- **Setup (P1)** → **Foundational (P2)** → 使用者故事 → **Polish (P7)**
- US1 為 MVP（規則設定與公開）；US2 依 T004（分配骨架）與 T008（規則可設定）；US3 依 US2（需要讓位結果）；US4 依 T004、T008，可與 US3 平行但同改 `effective.py`，須在 T014 之後
- 後端同檔任務須依序：`effective.py`（T004 → T014 → T023）；`api/rooms.py`（T008 → T020）；`services/rooms.py`（T008）；`ranking.py`（T017）；`export.py`（T018）；`review.py`（T020）
- 前端同檔任務須依序：`TeacherRoom.tsx`（T012 → T021）；`RankingBoard.tsx`（T021）；`StudentJoin.tsx`（T011）；`Home.tsx`（T010）；`api.ts`（T006）
- 既有測試修改：T019 須在 T018 之後（欄位數）；其餘測試各用新檔

### Within Each Story

- 測試任務（T007、T013、T015、T016、T022）可先寫、先看到失敗
- T002 → T003、T004；T005、T006 與 T003、T004 可平行（不同檔案）；T009 與 T008 可平行

### Parallel Opportunities

- Foundational：T005、T006 可與 T003、T004 平行
- US1：T007、T009 可平行；T011 與 T008 可平行
- US2：T013、T015 可平行
- US3：T016 與 T017、T018 可平行（不同檔案）
- Polish：T024、T025 可平行

## Parallel Example: User Story 2

```bash
# 可同時進行（不同檔案）：
Task: "T013 新增 backend/tests/test_fairness_allocation.py"
Task: "T015 新增 backend/tests/test_fairness_property.py"
# 之後：T014（修改 effective.py 使兩者通過）
```

## Implementation Strategy

### MVP First

1. 完成 Phase 1、2（規則模型與驗證、分配骨架、測試輔助、前端型別）
2. 完成 US1（可設定、固定、公開規則）→ 以 quickstart 情境 1～3 驗證
3. 緊接 US2（上限生效、讓位、保留），因為驗證效果需要 US1＋US2 才完整

### Incremental Delivery

1. Setup + Foundational → 既有行為不變（289 個測試仍通過）
2. US1 → 規則可設定與公開（尚不影響結果）
3. US2 → 上限讓位、保留、題組、審核連動、確定性（達成本步驟驗證效果）
4. US3 → 老師端看得懂、各處一致、結算前保密（Constitution III 測試）
5. US4 → 冷卻限制
6. Polish → 圖表一致性、README、完整驗證
