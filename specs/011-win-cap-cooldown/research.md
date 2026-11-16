# Research: 公平機制：獲勝上限與冷卻限制

規格無 NEEDS CLARIFICATION（Clarifications 已確定：全員不符資格時由名次最前者保留、冷卻從上一次取得的送出起算、題組可略超過上限）。
以下為設計決策，基於 Step 5 處理序與名次、Step 7 題組、Step 9 `effective.py` 的有效結果推導、Step 8／10 的下游共用。

## D1：分配集中在 `effective.py`，以「逐筆資格判定」的貪婪演算法推導
- **Decision**: 在 `services/effective.py` 新增 `allocate(room, round_no) -> Allocation`，演算法：
  1. 取該輪每個單位的 `unit_entries`（每組每單位一筆、依原始名次排序），剔除被駁回的（`invalid_keys`）→ 全部有效申請；
  2. 把所有有效申請依**後端處理序 `seq`** 由小到大排序；
  3. 逐筆判定（`wins[組]` 目前取得題數、`last_win[組]` 上一次取得的送出時間）：
     - 該單位已有獲勝者 → 此筆狀態 `Behind`（名次落後）；
     - 否則檢查資格：`win_cap` 非空且 `wins[組] >= win_cap` → 讓位 `YieldedCap`；`cooldown_seconds > 0` 且存在 `last_win[組]` 且 `submitted_at - last_win[組] < cooldown` → 讓位 `YieldedCooldown`（兩者同時成立時以上限為準）；
     - 皆符合 → 此筆 `Won`：單位獲勝者設為該筆、`wins[組] += 單位題數`、`last_win[組] = 該筆 submitted_at`；
  4. **保留**：主判定結束後，仍沒有獲勝者、但有有效申請的單位，由原始名次最前的有效申請取得，狀態 `Kept`（不影響其他判定）。
  `effective_winners()` 改為回傳 `allocation.winners`，簽章不變。
- **Rationale**: `effective.py` 已是結果、看板、匯出、回填的唯一推導處（Step 9），改這一處下游全部一致（FR-012、SC-006、SC-010）；
  逐筆依 `seq` 判定天然對應「成功搶得 2 題**後**，再搶第 3 題」的語意；演算法是純函式、只依輸入，所以確定性、可重現（FR-010）。
- **Alternatives**: 依題號順序分配——與「先搶先得」的時間語意不符，且同一組送出順序不同會得到相同結果，違反直覺；
  每個下游各自套用公平規則——容易不一致，違反 FR-012。

## D2：為什麼依處理序 `seq`，而不是 `submitted_at` 或題號
- **Decision**: 判定順序用 `Submission.seq`（Step 5：後端唯一仲裁鍵，每筆被接受的送出取得一次、單調遞增）；冷卻的時間差才用 `submitted_at`。
- **Rationale**: 憲章原則 II 規定仲裁以後端處理序／時間為準；`seq` 不會有同一時刻並列的問題（Step 5 已用 `seq` 保證唯一）；題組成員共用一個 `seq`，所以一次題組送出是單一事件。
  `submitted_at` 只精確到系統時鐘解析度，且可能相同，用來做順序可能不唯一，所以只拿它計算冷卻的時間差。
- **Alternatives**: 以 `submitted_at` 排序——同值時需要額外打破平手規則。

## D3：資格規則與冷卻起算
- **Decision**: 資格＝「取得前題數 < 上限」且「距離該組上一次**取得**的送出已達冷卻秒數」。只有狀態為 `Won`（含題組）的送出會更新 `last_win`；`YieldedCap`／`YieldedCooldown`／被駁回的送出**不啟動冷卻**（Clarification Q2）。`Kept` 在主判定之後產生，不影響任何資格判定。
- **Rationale**: FR-005、FR-006；避免「亂送」讓自己一直處於冷卻（對一般組別不公平）；`Kept` 晚於主判定才指派，因此不會反過來改變別的單位的結果，演算法保持單向、可推理。
- **Alternatives**: 任何送出都啟動冷卻——會懲罰沒有取得的送出。

## D4：全員不符資格時「保留」（FR-008、Clarification Q1）
- **Decision**: 見 D1 步驟 4；`Kept` 的獲勝者計入看板的獲勝題數（可能顯示 3/2），在老師端標示「保留」。其他不符資格的申請維持原本的讓位狀態。
- **Rationale**: 避免題目懸空造成回填試算表出現空格；上限只在有其他符合資格者可遞補時才擋人。
- **Impact**: `results.build_result` 的 `noValid` 判斷（`w is None` 且有送出）只會發生在「全部被駁回」，因為有有效申請的單位一定有獲勝者。

## D5：題組計入上限（Clarification Q3）
- **Decision**: 單位題數＝題組成員數（單題為 1）；資格只檢查「取得前」的 `wins < 上限`，取得後 `wins += 單位題數`，因此允許略超過上限一次。題組內各題的獲勝者永遠同一組（沿用 Step 7、9）。
- **Rationale**: 沿用 Step 7、9 的「N 題計 N 題」；避免題組大於上限時沒有任何組別能取得。

## D6：看板與狀態標籤（FR-013、FR-016）
- **Decision**: `ranking.build_board` 的每筆 `ranking[]` 新增 `outcome`：`Won`／`Kept`／`Behind`／`Invalid`／`YieldedCap`／`YieldedCooldown`（取自 `allocation.status[(單位, 組)]`）；`board.fairness = {winCap, cooldownSeconds}`；
  `leader` 與 `leadTally` 仍來自獲勝者（因此自動為讓位後結果）。前端以「x/上限」顯示各組取得題數（來自 `leadTally` 與 `winCap`）。
- **Rationale**: 老師需要看懂為什麼某組沒拿到；沿用既有 `status`（有效／已駁回）欄位不動，避免破壞 Step 9 的契約，新增欄位只增不減。
- **Privacy**: 看板只經老師路徑，沿用既有靜態審核。

## D7：匯出 CSV 追加兩欄（FR-014）
- **Decision**: 在 Step 9 的十一欄之後追加 `獲勝狀態`（`獲勝`／`未獲勝`）與 `未獲勝原因`（`被駁回`／`已達上限`／`冷卻中`／`名次落後`；獲勝者與 `Kept` 獲勝者皆留空）。每個送出依其輪次與單位取 `allocation.status`；各輪各自呼叫 `allocate`。
- **Rationale**: 憲章原則 V 要求遞補事件可匯出核對；前十一欄內容與順序不變，只影響測試中寫死的欄位數。

## D8：審核連動可見（`changedUnits`）
- **Decision**: 不保存歷史、也不改 `review.apply_review` 的簽章（Step 9 既有測試直接呼叫它）。在審核端點（`api/rooms.py`）呼叫 `apply_review` **之前**先以 `allocate` 取得各單位獲勝組別（`before`），成功追加後再取（`after`），差異的單位（排除被審核的那個單位本身）作為 `changedUnits` 傳給 `review.publish_review(room, changed_units)`，併入 `review_updated`；老師端提示「此次審核連動影響：Q3、Q5」。
- **Rationale**: FR-011、FR-013；連動是公平規則下審核的新行為，老師必須能一眼看出。計算只多一次 `allocate`，成本可忽略。

## D9：規則設定、驗證與固定
- **Decision**: `POST /api/rooms` 的 `CreateBody` 新增選填 `fairness: {winCap: int | null, cooldownSeconds: int}`；`services/fairness.py` 的 `validate_fairness(questions, raw)`：
  `raw` 為空或 `winCap is None and cooldownSeconds == 0` → 回傳預設（不限制）；沒有題目卻帶規則 → `FAIRNESS_INVALID{reason:"NO_QUESTIONS"}`；
  `winCap` 必須是整數且 `1 <= winCap <= 題目數`（`WIN_CAP_RANGE`）；`cooldownSeconds` 必須是整數且 `0 <= x <= 600`（`COOLDOWN_RANGE`）；型別不對（含布林）→ `TYPE`。
  驗證在指紋比對與題組驗證之後、建立房間之前；任何失敗都不建房。房間建立後沒有任何修改規則的端點。
- **Rationale**: FR-001、FR-002、FR-004；與 Step 7 題組完全相同的建立流程與錯誤格式。
- **Alternatives**: 建立後再開端點設定——違反「進行中不得更動」。

## D10：規則公開給學生
- **Decision**: `joined` 新增 `fairness`（`null` 或 `{winCap, cooldownSeconds}`）；學生頁在「等待搶答」顯示規則說明，其他階段不顯示；老師 `snapshot.room.fairness` 與建立回應也帶規則。
- **Rationale**: FR-003、憲章 IV；規則只含兩個數字，不含任何作答資訊，可給所有學生，不影響保密。

## D11：向下相容與既有測試
- **Decision**: 沒有規則時 `allocate` 的結果與舊 `effective_winners` 完全相同（無上限、無冷卻、無讓位；每個有效單位的獲勝者為原始名次最前的有效申請；`Kept` 不會出現）。CSV 欄位數由 11 改為 13，僅影響寫死欄位數的既有測試。
- **Rationale**: SC-010。

## D12：效能
- **Decision**: `allocate` 一次呼叫為 O(n log n)（對 n 筆有效申請依 `seq` 排序一次）；`results`／`ranking`／`export` 各自呼叫，匯出對每一輪呼叫一次。6000 筆在 1 秒內。
- **Rationale**: SC 與既有 Step 8 的規模測試門檻一致。

## D13：前端
- **Decision**: `FairnessEditor`（預覽頁，放在題組設定之後）：「每組最多搶得 [ ] 題（留空＝不限制）」與「冷卻 [ ] 秒（0＝不套用）」，即時檢查範圍（1～題目數、0～600），無效時禁用「確認建立房間」並顯示原因；
  `RankingBoard` 每筆名次顯示 `outcome` 標籤（取得／保留／讓位（已達上限）／讓位（冷卻中）／已駁回／名次落後），並在看板上方顯示「規則：每組最多搶得 N 題・冷卻 M 秒」與各組「x/N」；
  `TeacherRoom` 收到 `review_updated.changedUnits` 時顯示「此次審核連動影響：…」；學生頁等待搶答階段顯示規則說明。
- **Rationale**: SC-001（只多填一個欄位）、FR-003、FR-013。
