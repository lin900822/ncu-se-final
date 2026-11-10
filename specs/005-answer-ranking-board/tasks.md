# Tasks: 搶答順位仲裁與即時進度板

**Input**: `/specs/005-answer-ranking-board/` 下的 plan.md、spec.md、research.md、data-model.md、contracts/、quickstart.md
**Prerequisites**: plan.md、spec.md（皆已備齊）；Step 1～4 已實作完成
**Tests**: 依 plan.md 的 Testing 與 Constitution（原則 II 並發名次、原則 III 不外洩）加入 pytest；真實畫面以 quickstart.md 手動驗證
**Format**: `- [ ] T### [P?] [Story?] 描述（含檔案路徑）`；`[P]` = 可平行（不同檔案、無未完成相依）

> 使用者故事對應：US1＝依抵達先後判定各題順位（P1）、US2＝老師端即時進度板（P1）、US3＝學生端看不到順位與他組組名（P1）

## Phase 1: Setup

- [X] T001 執行 `cd backend && uv run pytest` 與 `cd frontend && npx tsc -b`（於 `frontend/` 內 `nvm use`），確認 Step 1～4 基準全數通過後才開始；本步驟不新增任何依賴

---

## Phase 2: Foundational（阻擋所有故事的共用基礎）

**⚠️ 完成前不得開始任何使用者故事**

- [X] T002 修改 `backend/app/models.py`：`Submission` 新增 `seq: int`（房間內單調遞增處理序，仲裁依據）與 `rank: int`（同一 `(round, question_id)` 的名次，1 起算）；兩者與既有欄位在建立時一次寫入，之後不得有任何更新路徑；`submitted_at` 註解改為「後端 UTC，僅供顯示，不參與排序判定」。`Room` 新增 `next_seq: int = 1` 與 `rank_counts: dict[tuple[int, str], int]`（鍵為 `(round, question_id)`，由 `submissions` 推得，用於取得下一個名次）

**Checkpoint**: 模型就緒，既有測試仍通過（`Submission` 建構處由 T003 補齊）

---

## Phase 3: User Story 1 - 依抵達先後判定各題送出順位 (Priority: P1) 🎯 MVP

**Goal**: 同題同輪的有效送出依後端處理序得到唯一、連續、不並列的名次，確定後不改寫。

**Independent Test**: 兩個不同組別同時對 Q1 送出，恰得到第 1 名與第 2 名；被拒絕或重複的送出不佔名次。

### Tests for User Story 1

- [X] T003 [P] [US1] 新增 `backend/tests/test_ranking.py`（沿用 `conftest.py` 的 `make_started_room`、`join_student`、`use_sheet`）：(a) 組 A 先送 Q1、組 B 後送 → 老師端 `submission` 事件的 `rank` 分別為 1、2，組 C 再送為 3；(b) 同組重複送出（連點 10 次、同組另一視窗）→ `room.submissions` 不增加、名次與 `submitted_at` 不變；(c) 被拒絕的送出（空白、501 字元、非搶答中、題目不存在）不佔名次，之後的有效送出仍得下一個連續名次；(d) 不同題目各自從 1 起算；(e) 客戶端在訊息夾帶 `submittedAt`（1999 年）、`rank`、`seq` 等欄位 → 全被忽略，名次仍只依抵達先後；(f) 新一輪開始後同題重新從 1 起算，舊輪紀錄的 `rank`、`seq` 保留不變；(g) 每筆紀錄 `seq` 嚴格遞增且全房間唯一，同題同輪依 `rank` 排序與依 `seq` 排序結果相同
- [X] T004 [P] [US1] 新增 `backend/tests/test_ranking_concurrency.py`：以 `asyncio.gather` 讓 N 個不同組別同時呼叫 `services.submissions.submit` 對同一題送出，重複 100 輪（每輪新房間或新一輪）：每輪名次集合恰為 `{1..N}`、無重複、無並列、`seq` 唯一；另測「同組兩個視窗同時送同題」只產生 1 筆且只有 1 個名次；另測在 `submit` 前後以 monkeypatch 讓 `utcnow()` 回傳完全相同的時間，名次仍唯一且依處理序（SC-001、SC-002、原則 II）

### Implementation for User Story 1

- [X] T005 [US1] 修改 `backend/app/services/submissions.py` 的 `submit()`：在「確定為新送出」的**同一個無 `await` 區段**內，取 `seq = room.next_seq` 並遞增 `room.next_seq`；取 `rank = room.rank_counts.get((room.round, question_id), 0) + 1` 並寫回 `rank_counts`；將 `seq`、`rank` 與既有欄位一併建立 `Submission`（建立後不得再修改）。驗證失敗與重複送出路徑**不得**遞增任何計數。使 T003、T004 通過
- [X] T006 [US1] 修改 `backend/app/services/submissions.py` 的 `to_teacher_event()` 與 `backend/app/services/rooms.py` 的 `snapshot()`：老師的 `submission` 事件與 `snapshot.room.submissions[]` 每筆新增 `"rank": <int>`（所有輪次的舊紀錄保留其當時名次）；**不得**修改 `to_group_event`、`to_other_groups_event` 與學生 `joined` 的內容（保密，見 US3）。補充 T003 的斷言：`submission` 事件與 snapshot 皆含正確 `rank`

**Checkpoint**: US1 可獨立驗證（quickstart 情境 2、3、4、5、8、11）

---

## Phase 4: User Story 2 - 老師端即時進度板顯示各題領先組別 (Priority: P1)

**Goal**: 老師端即時看到每題最快組別、依名次清單與各組領先題數；重整、換裝置、新一輪皆正確。

**Independent Test**: 兩組同時對 Q1 送出後，老師端 2 秒內在 Q1 顯示最快送出組別名稱；未送出題目顯示「尚無組別送出」。

### Tests for User Story 2

- [X] T007 [P] [US2] 新增 `backend/tests/test_ranking_board.py`：(a) `ranking.build_board(room)` 無送出時每題 `leader is None`、`submittedCount == 0`、`ranking == []`、`leadTally == []`，且 `questions` 依題目順序包含所有題目；(b) 兩組送 Q1 → Q1 `leader` 為先送者、`ranking` 依名次含 `{rank, group, submittedAt}`、`submittedCount == 2`；(c) `leadTally` 為各組第 1 名題數，只列至少領先一題者，依題數降序、同數依組名；(d) 老師 WebSocket 在每筆新有效送出後收到一則 `{"type":"board",...}`，內容與 `build_board` 一致；重複與被拒絕的送出**不**觸發 `board`；(e) 新開始一輪時老師收到空白 `board`（`submittedCount == 0`），且 `board.round` 為新輪次；舊輪紀錄仍在 `room.submissions`；(f) 老師重新連線與以恢復碼換裝置後，`snapshot.room.board` 與當下 `build_board` 一致；(g) 兩台不同組別裝置同時對 Q1 送出 → 老師端看板 Q1 的 `ranking` 恰為第 1、第 2 名，`leader` 為第 1 名組別（本步驟驗證效果）

### Implementation for User Story 2

- [X] T008 [US2] 新增 `backend/app/services/ranking.py`：`build_board(room) -> dict`，僅取 `round == room.round` 的 `room.submissions` 推導（**不另存任何狀態**）；回傳 `{"type":"board","round":room.round,"questions":[{"questionId","leader","submittedCount","ranking":[{"rank","group","submittedAt"}]}],"leadTally":[{"group","leadCount"}]}`：`questions` 依 `room.questions` 順序、含尚無送出者（`leader: null`、`ranking: []`）；`ranking` 依 `rank` 升冪、`submittedAt` 以 `iso()` 輸出；`leadTally` 只含 `leadCount >= 1` 的組別，依 `leadCount` 降序、同數依組名。模組 docstring 註明：僅供老師連線，嚴禁送往學生連線（原則 III）
- [X] T009 [US2] 修改 `backend/app/api/ws.py` 學生 `submit` 成功新建的扇出段落（`created` 為 True 後）：在 `broadcast_to_teachers(... submission ...)` 之後追加 `await realtime.broadcast_to_teachers(room.code, ranking.build_board(room))`；重複與錯誤路徑不推送。修改 `backend/app/services/phase.py` 的 `start_answering`：在既有廣播之後對老師推送一則 `build_board(room)`（新一輪的空白看板，僅 `broadcast_to_teachers`）。修改 `backend/app/services/rooms.py` 的 `snapshot()`：`room` 新增 `"board": ranking.build_board(room)`（僅 `type` 之外的結構亦可，前端以 `board` 欄位使用）。使 T007 通過
- [X] T010 [P] [US2] 新增 `frontend/src/components/RankingBoard.tsx`：props 為 `board`（對應 contracts/websocket.md 的 `board` 結構，於檔內以 TypeScript 型別宣告）；(a) 總覽列顯示各組領先題數（`leadTally`，無資料時顯示「尚無領先組別」）；(b) 每題一張卡片：題號（沿用 `QuestionFields` 的標籤慣例）、最快組別名稱（`leader`，醒目呈現）、已送出組數；`leader` 為 `null` 時顯示「尚無組別送出」；(c) 卡片內依名次列出所有已送出組別（名次、組名、送出時間以本地時間顯示到秒）；(d) 版面可在手機寬度使用，沿用既有 Tailwind 樣式
- [X] T011 [US2] 修改 `frontend/src/pages/TeacherRoom.tsx`（依 T010）：新增狀態 `board`；`snapshot` 事件時以 `room.board` 設定；新增 `case 'board'` 直接覆蓋 `board`；`submission` 事件型別 `SubmissionItem` 新增 `rank: number`；在既有「本輪送出清單」附近渲染 `<RankingBoard board={board} />`；搶答中以外的階段（等待、已結束）仍顯示最後的看板（已結束時保留本輪結果），新一輪收到空白 `board` 即清空；`npx tsc -b` 通過

**Checkpoint**: US1 + US2 可獨立驗證（quickstart 情境 1～7、10）

---

## Phase 5: User Story 3 - 學生端不得看到他組的順位與組名 (Priority: P1)

**Goal**: 名次、看板、領先組別與領先題數絕不出現在任何學生連線的資料中。

**Independent Test**: 組別 A 成為 Q1 第 1 名後，檢視組別 B 與 A 同組視窗收到的所有訊息，找不到名次、看板、領先組別與他組組名。

### Tests for User Story 3

- [X] T012 [P] [US3] 新增 `backend/tests/test_ranking_privacy.py`（沿用 `test_submission_privacy.py` 的 `flush`、`dumps` 技巧）：A 組（兩個視窗）、B 組、C 組各一視窗，A 先送 Q1、B 再送 Q1、C 送 Q2，所有組別完成後蒐集各學生連線收到的全部訊息（含 `joined`、`submitted`、`question_submitted`、`phase_changed`），序列化後斷言：(a) 不含 `"rank"`、`"seq"`、`"board"`、`"leader"`、`"leadTally"`、`"ranking"`、`"submittedCount"`；(b) 不含他組組名（B 看不到「A 組」，反之亦然）；(c) 同組視窗收到的 `submitted` 事件格式與 Step 4 完全相同（鍵集合為 `type, questionId, answer, round`）；(d) 他組 `question_submitted` 鍵集合為 `type, questionId, round`；(e) 新加入或重連的學生 `joined` 不含任何名次或看板資料；(f) 靜態掃描：`backend/app/services/ranking.py` 與 `rank` 相關輸出只出現在 `broadcast_to_teachers`／老師 `snapshot` 路徑，`broadcast_to_group`、`broadcast_to_other_groups`、`broadcast_to_students` 的呼叫處不引用 `ranking`、`rank`（以讀取 `backend/app/` 原始碼並以正則檢查，比照 Step 4 的作法）

### Implementation for User Story 3

- [X] T013 [US3] 檢視並確認隱私邊界（無新功能，僅補強）：於 `backend/app/realtime.py` 的模組 docstring 與 `broadcast_to_teachers` 註解補充「名次、看板、領先組別、領先題數僅能經 `broadcast_to_teachers` 傳送」；於 `backend/app/services/ranking.py` 確認未被任何學生路徑（`api/ws.py` 學生段落、`services/groups.py`）匯入使用；`frontend/src/pages/StudentJoin.tsx` 確認不處理 `board`、`rank` 欄位，也**不顯示**自己的名次（FR-013）。若發現洩漏路徑，修正後使 T012 通過

**Checkpoint**: 三個故事皆可獨立驗證（quickstart 情境 9）

---

## Phase 6: Polish & Cross-Cutting Concerns

- [X] T014 [P] 修改 `diagrams/sequence.puml`、`diagrams/component.puml`、`diagrams/class.puml`（若實作與圖不一致才改）：確認「名次於送出同一區段內以處理序賦予」「看板推送僅送老師」「`Submission.seq/rank`」「新一輪空白看板」皆與程式一致；執行 `plantuml -tpng diagrams/*.puml` 重新產圖（Constitution VI 實作後驗證）
- [X] T015 [P] 更新 `specs/005-answer-ranking-board/quickstart.md` 與 `README.md`（若 README 有功能清單）：補上順位與進度板的說明；確認與實作行為一致
- [X] T016 執行完整驗證：`cd backend && uv run pytest`（全數通過，含 Step 1～4 既有測試）、`cd frontend && npx tsc -b`；依 `quickstart.md` 的手動驗證情境 1～11 逐項走一遍，特別是「兩台不同組別裝置同時對 Q1 送出，老師端看板 2 秒內顯示最快組別名稱」與「學生連線訊息中找不到名次／看板／他組組名」

---

## Dependencies & Execution Order

### Phase Dependencies

- **Setup (P1)** → **Foundational (P2)** → 使用者故事（P3、P4、P5）→ **Polish (P6)**
- US1 為 US2、US3 的前置（名次必須先存在）；US2 與 US3 在 US1 完成後可平行（T012 只依賴 T005、T006 與 T009 的老師推送完成後才能完整斷言看板不外洩，故建議 US3 測試在 T009 後執行）

### Within Each Story

- 測試任務（T003、T004、T007、T012）可在對應實作前先寫、先看到失敗
- T005 → T006；T008 → T009；T010 → T011
- 同檔案任務不可平行：`submissions.py`（T005、T006）、`ws.py`（T009）、`rooms.py`（T006、T009）、`phase.py`（T009）

### Parallel Opportunities

- T003、T004 可平行（不同檔案）
- T007（測試）與 T010（前端元件）可平行；T012 與 T010 可平行
- T014、T015 可平行

## Parallel Example: User Story 2

```bash
# 可同時進行（不同檔案）：
Task: "T007 新增 backend/tests/test_ranking_board.py"
Task: "T010 新增 frontend/src/components/RankingBoard.tsx"
# 之後依序：T008 → T009（後端）；T011（前端，依 T010）
```

## Implementation Strategy

### MVP First（User Story 1）

1. 完成 Phase 1、2
2. 完成 Phase 3（US1）：名次唯一且由處理序決定、老師 `submission` 事件帶 `rank`
3. **停下驗證**：quickstart 情境 2～5，名次並發正確即達成核心公平性

### Incremental Delivery

1. Setup + Foundational → 模型就緒
2. US1 → 驗證名次（MVP，可由老師 `submission` 事件與測試觀察）
3. US2 → 老師端進度板（驗證效果的畫面部分）
4. US3 → 隱私把關與自動掃描
5. Polish → 圖表一致性與完整驗證

---

## Notes

- 本步驟**不**判定最終獲勝、不做防壟斷遞補與老師仲裁、不回填試算表（FR-014）；`rank`、`seq` 為後續步驟的輸入
- 學生端協定與畫面**不變**；名次與看板僅老師可見
- 新依賴：無
- Commit 建議：每完成一個使用者故事 phase 提交一次
