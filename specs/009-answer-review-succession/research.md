# Research: 老師端人工審核與順位遞補

規格無 NEEDS CLARIFICATION（Clarifications 已確定：結束後才能審核、不通知被駁回組別、理由輸入即確認）。
以下為設計決策，基於 Step 4/5 送出與名次、Step 6 結果公布、Step 7 題組、Step 8 匯出與既有 `Realtime`。

## D1：審核用 REST 端點，不走 WebSocket
- **Decision**: `POST /api/rooms/{code}/reviews`，憑證放 `Authorization: Bearer`，沿用 `rooms.verify_teacher`。
- **Rationale**: 開始／結束搶答等老師動作都是 REST，結果以回應＋廣播呈現；REST 讓錯誤（401、時機不對、理由缺漏）有明確狀態碼，也好測。
  學生 WebSocket 完全不新增任何會改變結果的訊息型別。
- **Alternatives**: 走老師 WebSocket——斷線時動作會遺失且無法回報錯誤。

## D2：原始資料不動，審核紀錄僅追加，有效結果推導
- **Decision**: `Room.reviews: list[ReviewRecord]`（輪次、組別、搶答單位、動作、理由、操作者、UTC 時間），只追加。**不修改 `Submission`**。
  某筆送出是否有效＝同一 `(輪次, 組別, 搶答單位)` 的**最後一筆**審核紀錄動作是否為「駁回」；沒有紀錄即有效。
- **Rationale**: 憲章 II 要求已確定的順位不得被靜默改寫、資料完整性要求僅追加；以「新增事件」表達更正（含恢復）。
  推導資料沒有第二份事實來源，也不會與原始名次不一致（FR-010）。
- **Alternatives**: 在 `Submission` 加 `status` 欄位並改寫——違反僅追加；重算名次——改動順位，違反原則 II。

## D3：有效結果與遞補後名次的推導規則
- **Decision**: 在 `services/effective.py`（只匯入 `..models` 與 `bundles`，避免 `results`↔`review` 循環匯入）提供純函式：
  - `invalid_keys(room, round)`：由 `reviews` 推得目前無效的 `(normalized_name, unit_id)` 集合（每個鍵取最後一筆動作）；
  - `effective_winners(room)`：對本輪每個搶答單位，把該單位的送出依**原始名次**排序，取第一個不在無效集合者；
  - `succession_ranks(room, round, unit_id)`：排除無效者後從 1 起重新編號。
  搶答單位＝`bundles.unit_of(room, question_id)`（題組 id 或題目 id）。題組成員紀錄共用組別與名次，所以以單位為範圍即整組一起生效。
- **Rationale**: 規則單純、可被性質測試直接驗證（SC-003）；`results`／`ranking`／`export` 共用同一份推導，避免三處各算各的而不一致（FR-016）。
- **Alternatives**: 各處自己算——容易不一致。

## D4：審核驗證順序與錯誤碼
- **Decision**（全部在同一個同步區段、寫入前完成，任一失敗不寫入）：
  1. 老師憑證（沿用 `UNAUTHORIZED`）；房間已結束 → `ROOM_CLOSED`（409）。
  2. `phase == "Ended"` 且請求的 `round == room.round` → 否則 `REVIEW_NOT_ALLOWED`（400，「目前不開放審核，請於搶答結束後審核最新一輪」）。
  3. `action` 必須是 `invalid` 或 `valid` → 否則 `BAD_REQUEST`。
  4. `unitId` 必須是本房間題目 id 或題組 id → 否則 `UNIT_NOT_FOUND`（400）。
  5. `group`（顯示組名，正規化後比對）在該單位本輪有送出 → 否則 `REVIEW_TARGET_NOT_FOUND`（400）。
  6. 理由 `strip()` 後非空（`REASON_REQUIRED`）且 ≤ 100 字元（`REASON_TOO_LONG`）。
  7. 重複判斷：目前狀態已是目標狀態 → 回 `changed: false`、不新增紀錄、不廣播（FR-019）。
  8. 追加 `ReviewRecord`（UTC 時間）、回 `changed: true`。
- **Rationale**: FR-005、FR-019、SC-007、SC-009。請求帶 `round` 是為了避免老師的舊畫面在新一輪結束後誤審新一輪。

## D5：廣播——沿用既有專用通道，學生只收有效第一名
- **Decision**: 審核成功（`changed`）後：
  - 老師：新訊息 `review_updated`，含 `board`（每筆狀態／遞補後名次／理由）、`reviews`（審核紀錄清單）、`result`（有效結果）；
  - 全體學生：沿用 `realtime.broadcast_result` 送 `round_result`，內容仍只有各題有效第一名的組名＋答案，另加 `reviewed: true`；
  - 老師**不**另收 `round_result`（已含在 `review_updated.result`）。
  `broadcast_result` 的呼叫端由「只有 `phase.py`」擴充為「`phase.py` 與 `review.py`」，對應的靜態審核測試更新允許清單。
- **Rationale**: 學生端本來就處理 `round_result`（切換結果頁、標示本組搶下），重用即可；內容只有有效第一名，被駁回者的組名與答案自然不會出現（FR-014）。
  專用通道讓「誰能對學生廣播結果」仍由靜態測試把關（原則 III）。
- **Alternatives**: 新增學生訊息型別——前端與測試多一條分支，且得再審一次保密；把審核資訊夾進 `phase_changed`——污染「不含作答內容」的房間層級訊息。

## D6：還原——重用既有推導，不另存
- **Decision**: `joined.result`（`build_result`）與老師 `snapshot.room.result`／`board` 都改由有效推導，另在 `snapshot.room` 加 `reviews`。學生端 `joined` 不加任何審核資訊。
- **Rationale**: FR-015；後端為事實來源，離線、重整、換裝置自然看到審核後的結果。學生重連不顯示「老師已更新結果」（只在即時更新時顯示）。

## D7：Step 5 看板與領先題數
- **Decision**: `ranking.build_board` 的每筆名次加入 `status`（`Valid`／`Invalid`）、`successionRank`（無效者為 `null`）、`reason`（最近一次審核理由，沒有為 `null`）、`answer`（該題答案，僅老師看板）；
  每題 `leader` 與 `leadTally` 改取**有效第一名**（N 題題組計 N 題）；`submittedCount` 與原始 `rank` 不變。
- **Rationale**: FR-011、FR-013、FR-016。沒有任何審核時，有效第一名＝原始第一名，Step 5 既有測試不需改動語意。看板仍只給老師（既有靜態審核測試把關）。
- **Alternatives**: 另開一個審核專用看板——兩份看板容易不一致。

## D8：Step 8 CSV 追加欄位
- **Decision**: 原七欄之後依序追加：`審核狀態`（`有效`／`無效`）、`遞補後名次`、`審核理由`、`審核時間`。
  規則：有效列一律填遞補後名次（沒有更前面的被駁回時等於原始名次）；無效列為空；未審核列的理由與時間為空；最近一次審核是「恢復」者為「有效」並帶該次恢復的理由與時間；理由套用 `safe_cell`（公式防護）。
- **Rationale**: FR-021；憲章 V 要求歷程可匯出核對。已更新規格 FR-021 的措辭，避免「其餘審核欄位留空」被誤讀成遞補後名次也留空。
- **Impact**: Step 8 既有測試中寫死「七欄」的斷言需改為十一欄（見 plan 的測試清單）；原有七欄內容與排序不變。

## D9：規則公開（FR-022）
- **Decision**: 學生端在「等待搶答」階段顯示固定說明：「老師可審核答案；答案被判定無效時，名次由次順位組別遞補」。為前端靜態文字，規則寫在程式碼中、活動進行中不會變動。
- **Rationale**: 憲章 IV 要求規則於活動開始前公開、進行中不更動；不需要後端欄位。

## D10：前端互動
- **Decision**:
  - `RankingBoard`：每個搶答單位一張卡片，列出每筆（原始名次、組別、答案、時間、狀態、遞補後名次、理由）；Ended 階段每筆旁顯示「駁回/無效」（有效者）或「恢復有效」（已駁回者）；
    題組以一張卡片、各成員題的答案並列顯示。
  - 點擊後在該筆下方展開 `ReviewForm`：常用理由快速選取（答案錯誤、亂填、錯字）＋自行輸入（≤ 100 字元），按「確認駁回／確認恢復」即送出；理由為空時按鈕停用；送出中防連點。
  - 老師端新增「審核紀錄」區塊，列出時間、組別、題目、動作、理由。
  - 學生端結果頁：`reviewed: true` 時顯示「老師已更新結果」；某單位沒有有效答案顯示「本題（題組）無有效答案」，與「無人搶答」區分。
  - `UNAUTHORIZED` 視為老師身分失效（與 Step 8 匯出一致）。
- **Rationale**: SC-001（3 次點擊內完成）、FR-002、FR-013。

## D11：併發與重複
- **Decision**: `apply_review` 整段同步、不 await；重複判斷與追加在同一區段，所以同一筆連點或兩個視窗同時駁回只會寫入一筆（SC-009）。
- **Rationale**: 沿用 Step 4/5/7 驗證過的做法（單一 worker 的 asyncio 無 await 區段即原子）。
