# Research: 題組打包提交機制

規格無 NEEDS CLARIFICATION（Clarifications 已確定：領先題數按題算、只能相鄰、小題不自動綁、建立後不可改）。
以下為設計決策，基於 Step 3 建立流程、Step 4 `submissions`、Step 5 `ranking`、Step 6 `results` 與 `Realtime`。

## D1：題組是「房間層級的送出單位設定」，題目維持扁平（原則 I）
- **Decision**: 不修改 `Question`。`Room` 新增 `bundles: list[QuestionBundle]`（`id`、依題目順序的 `question_ids`）與推得的
  反查表 `bundle_of: dict[questionId, bundleId]`。未綁定的題目自成一個搶答單位，其 unitId 就是題目 id。
- **Rationale**: 原則 I 禁止題型分類與題目階層；題組不是題目的屬性或父節點，而是老師選用的「哪些題一起送出」設定，
  題號、順序、`cell` 全部不變。這樣學習單回填與題號驗證都不受影響，也不需要修訂憲章。
- **Alternatives**: 在 `Question` 加 `bundle_id`——讓題目帶分組屬性，較接近原則 I 禁止的父子關係，且 `question_public`
  會外洩設定方式之外的耦合；新建「題組題目」取代成員題目——破壞扁平清單與逐題回填。

## D2：題組送出存成「每題一筆」紀錄，共用 seq／時間／名次
- **Decision**: `submit_bundle()` 成功時為每個成員題目追加一筆 `Submission`，共用同一個 `seq`、`submitted_at`、`rank`，
  並設 `bundle_id`。去重以 `(round, normalized_name, bundleId)` 判斷（查任一成員的既有紀錄即可，因為成員紀錄總是一起寫入）。
- **Rationale**:
  - Step 5 `build_board` 與 Step 6 `build_result` 逐題運作，同題組各題 rank 相同 → leader／winner 自然一致（SC-006），
    領先題數自然以題數計（Clarification Q1），兩者都不必改排名邏輯；
  - 逐題保存答案，回填時直接依 `cell` 寫回（原則 V、FR-020）；
  - `bundle_id`＋共用 `seq` 讓歷程能看出是同一次送出（FR-019）。
- **Alternatives**: 新增 `BundleSubmission` 實體——進度板、結果、回填、`my_submissions` 都要多一條分支，且產生第二份事實來源。

## D3：名次以「搶答單位」計數
- **Decision**: `rank_counts` 的鍵由 `(round, questionId)` 改為 `(round, unitId)`；單題 unitId＝題目 id（行為與 Step 5 相同），
  題組 unitId＝題組 id。`seq` 每次被接受的送出（單題或題組）只取一次。
- **Rationale**: 題組是一個搶答單位，一個名次（FR-014）。題組成員不可單題送出（D5），所以成員題目不會有另一套計數。
- **Alternatives**: 各題各自計數再檢查一致——多此一舉且可能不一致。

## D4：全有或全無與併發（原則 II）
- **Decision**: `submit_bundle()` 與 `submit()` 一樣**整段同步、不 await**：依序檢查房間開放與搶答中 → 題組存在 →
  `answers` 的 key 恰為題組成員（不多不少）→ 每題非空白且 ≤ 500 → 去重 → 取 seq／rank → 追加所有成員紀錄 → 更新索引。
  任何檢查失敗都在寫入前丟出錯誤，不會留下部分紀錄。
- **Rationale**: 單 worker 的 asyncio 事件迴圈在無 await 區段內不會切換，等同於原子操作；這是 Step 4/5 已驗證的做法。
- **Alternatives**: 鎖（asyncio.Lock）——不需要，且會引入 await。

## D5：題組成員不可單題送出
- **Decision**: `submit()` 收到屬於題組的 questionId 時回 `QUESTION_IN_BUNDLE`，不寫入。
- **Rationale**: FR-006 規定題組內各題沒有各自的送出鈕；後端也必須擋住繞過畫面的請求，否則會出現只送出半個題組。

## D6：建立房間時驗證題組
- **Decision**: `POST /api/rooms` 多收 `bundles: list[list[str]] | null`（每個內層為 questionId 清單）。在讀取試算表並比對指紋**之後**、
  建立房間**之前**驗證：每組 ≥ 2 題、題目都存在、同一題不出現在兩組（或同組重複）、成員在題目清單中**連續相鄰**
  （以 Step 3 的題目順序判斷，排序後索引連續）。不合法回 `400 BUNDLES_INVALID`，`details` 列出原因；不建立房間。
  題組 id 依第一個成員在清單中的位置排序後編為 `B1`、`B2`…；成員依題目順序保存。沒有試算表卻帶非空 `bundles` 也回 `BUNDLES_INVALID`。
- **Rationale**: FR-002、FR-004；與 Step 3「全部驗證通過才建立房間」一致。前端也做相同檢查以即時提示，但以後端為準。
- **Alternatives**: 建房後另開端點設定題組——違反「建立後固定」（Clarification Q4）。

## D7：事件與保密（原則 III）
- **Decision**（學生 WebSocket）：
  - 學生 → `submit_bundle {bundleId, answers: {questionId: answer}}`；
  - 同組所有視窗 ← `bundle_submitted {bundleId, answers, round}`（一則訊息，整張卡片一次切換，不會出現半張卡片已送出）；
  - 老師 ← 每個成員一則 `submission`（沿用 Step 4 欄位，多 `bundleId`），之後一則 `board`；
  - 他組 ← `bundle_hint {bundleId, round}`（不含組名、答案、數量、時間）；
  - 重複送出 ← 只回發送者 `bundle_submitted`（既有答案）；
  - 錯誤 ← 只回發送者 `error`，多帶 `bundleId` 與 `details.questionIds`（標示哪幾題有問題）。
- **Rationale**: 沿用 Step 4 三種受眾的切分；老師端已會處理逐題 `submission`，沿用可少改前端。
- **Alternatives**: 他組收逐題 `question_submitted`——會多送 N 則，且讓他組知道題組大小以外的資訊並無必要；同組收逐題 `submitted`——畫面可能短暫只鎖一半。

## D8：下發題組設定
- **Decision**: 建立回應、學生 `joined`、老師 `snapshot.room` 都加 `bundles: [{id, questionIds}]`。重連時 `mySubmissions`／
  `submittedByOthers` 仍逐題（題組成員會一起出現），前端以 `bundles` 對回卡片。
- **Rationale**: FR-005、FR-012；題組設定不含作答內容，可給所有學生（原則 III 不受影響）。

## D9：前端呈現
- **Decision**:
  - `lib/questions.ts` 新增 `groupByUnit(questions, bundles)`：依題目順序產生卡片清單，題組成員合為一張卡片，未綁定的題目
    沿用既有「依題號分組」顯示（題組小題仍在同一個框內、各自送出）；
  - 預覽頁：題號清單旁可勾選題目，按「設為題組」時檢查 ≥2、相鄰、未被綁定；已設定的題組可「取消」；改連結或重新讀取時清空；
  - 學生題組卡片：標題「題組：Q3、Q4」，各題一個輸入框、卡片底部一顆送出鈕；任一格 `trim()` 為空時按鈕停用並提示；
    收到 `bundle_submitted` 整卡鎖定；他組提示文字「本題組已有組別送出」；
  - 老師進度板與結果頁：以同一函式分卡，題組只顯示一份名次清單／一個搶下組別，並列出各題答案；無人送出顯示「本題組無人搶答」。
- **Rationale**: FR-006、FR-007、FR-011、FR-015、FR-017。

## D10：草稿與新一輪
- **Decision**: 草稿仍逐題存在學生瀏覽器（Step 3 `drafts`），題組不影響；新一輪開始時清空沿用既有規則，`bundles` 不變。
- **Rationale**: FR-012、Edge Cases；不需新機制。
