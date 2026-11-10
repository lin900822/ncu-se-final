# Research: 組別答案提交與防重複送出

規格無 NEEDS CLARIFICATION。以下為設計決策（基於現有 `Realtime`、`groups`、`phase` 的程式結構）。

## D1：去重與原子性
- **Decision**: 以索引 `room.submission_index[(round, group_key, question_id)] -> Submission` 去重。`submit()` 在**沒有 `await` 的同步區段**內依序完成：房間開放且 `Answering` → 題目存在 → 答案非空且 ≤ 500 → 查索引 → 追加紀錄並寫入索引；之後才 `await` 扇出。
- **Rationale**: 單一 worker 的 asyncio 事件迴圈只在 `await` 處切換，同步區段天然原子（沿用 Step 1 `join` 與 Step 2 `phase` 的作法）；階段檢查與追加在同一區段，所以「結束搶答瞬間」只會有一種一致結果（先處理者勝）。
- **Alternatives**: 加 `asyncio.Lock`——多一層且無必要；以資料庫唯一鍵——專案無資料庫。

## D2：重複送出的回應
- **Decision**: 重複送出不報錯：只對**發送者的視窗**回送既有結果 `submitted`（附既有答案），不新增紀錄、不扇出給他人。
- **Rationale**: 連點與同組另一視窗先到時，畫面直接收斂到正確狀態，不需處理錯誤分支（FR-005）。

## D3：事件扇出（三種受眾、三種內容）
- **Decision**:
  - 同組所有視窗（含發送者）：`submitted`＝`{questionId, answer, round}`。
  - 老師：`submission`＝`{group, questionId, answer, round, submittedAt}`。
  - 其他組別：`question_submitted`＝`{questionId, round}`（不含組名、內容、組數、時間）。
- **Rationale**: 規格 FR-006/FR-008/FR-011 與 Clarification Q2（匿名且不含數字）。三種事件互不混用欄位，易於測試「他組訊息不含任何答案」。
- **Alternatives**: 單一廣播＋前端過濾——內容已送到他組瀏覽器，違反原則 III。

## D4：同組多視窗的連線登記
- **Decision**: `Realtime.students` 由 `dict[(code, name)] -> WebSocket` 改為 `dict[(code, name)] -> set[WebSocket]`。新增 `group_connections()`、`broadcast_to_group()`、`broadcast_to_other_groups(exclude)`。`groups.join` 移除 `GROUP_ONLINE` 拒絕，改檢查視窗上限（每組 10，超過回新錯誤 `GROUP_WINDOWS_FULL`）。`Group.online` ＝ 至少一個視窗在線；`disconnect` 只在該組最後一個視窗離開時標記離線並通知老師。
- **Rationale**: 最小改動即可支援 FR-014；組別於老師端仍只有一筆；Step 1 其餘規則（組名正規化、離線保留）不變。
- **Alternatives**: 以每視窗 ID 建立子身分——違反「組別為唯一單位」且複雜。
- **影響**: Step 1 的 `group_status(online=true)` 僅在組別由離線轉在線時送出；第二個視窗加入不重複通知老師。

## D5：加入/重連還原
- **Decision**: `joined` 新增 `mySubmissions: { questionId: answer }`（該組**本輪**的送出）與 `submittedByOthers: [questionId]`（本輪有其他組送出的題目，匿名）。老師 `snapshot.room` 新增 `submissions`（所有輪次、含 `round` 與 `submittedAt`）。
- **Rationale**: FR-007、FR-011；客戶端不得靠本地狀態判斷是否已送出（後端為事實來源）。
- **Alternatives**: 另建「取得狀態」請求——多一次往返，與既有 `joined` 快照模式不一致。

## D6：輪次與舊紀錄
- **Decision**: 紀錄帶 `round`；去重鍵含 `round`，所以新一輪（`start_answering` 使 `round += 1`）自然可重新送出；還原與提示只看 `room.round`。舊紀錄永不刪除。
- **Rationale**: FR-009、FR-012；前端在收到較大的 `round` 時清空已送出狀態與提示（沿用 Step 2、3 的輪次規則）。

## D7：答案驗證
- **Decision**: 空白答案（空字串或僅空白）→ `ANSWER_EMPTY`；超過 500 字元（以原字串長度計）→ `ANSWER_TOO_LONG`；題目不存在 → `QUESTION_NOT_FOUND`；非搶答中 → `PHASE_LOCKED`（既有）。錯誤只回發送者且不關閉連線，並附 `questionId` 方便前端對應。答案原文保存（不去除內部空白與換行）。
- **Rationale**: FR-004；與 Step 3 單格 500 字元一致。

## D8：時間與保密
- **Decision**: `submittedAt` 於接受當下由 `utcnow()` 產生；客戶端不得傳時間。`question_submitted` 刻意不含時間。
- **Rationale**: 原則 II、FR-010、FR-008。

## D9：前端狀態來源
- **Decision**: 學生端以 `joined`（還原）與 `submitted`／`question_submitted`（增量）維護 `submitted` 與 `othersSubmitted`；送出按鈕只負責送訊息，**不做樂觀更新**，一律等待 `submitted` 事件才顯示「已送出」。
- **Rationale**: 避免「畫面顯示已送出但後端沒有紀錄」（Edge Cases）；連線中斷時按鈕停用，重連後由 `joined` 還原。

## D10：移除 Step 1 的 GROUP_ONLINE 重試
- **Decision**: 刪除 `StudentJoin.tsx` 中針對 `GROUP_ONLINE` 的自動重試邏輯與相關常數；後端移除該錯誤碼。
- **Rationale**: 該情境不再發生；保留死碼會誤導。
