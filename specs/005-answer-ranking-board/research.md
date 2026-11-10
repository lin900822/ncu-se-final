# Research: 搶答順位仲裁與即時進度板

規格無 NEEDS CLARIFICATION。以下為設計決策（基於 Step 4 的 `submit()` 與 `Realtime`）。

## D1：以處理序（seq）仲裁，而非比較時間戳記
- **Decision**: `Room.next_seq` 為單調遞增計數；`submit()` 在接受新送出的同一個無 await 區段內取得 `seq` 並遞增。名次 `rank`＝同一 `(round, questionId)` 已有的有效送出數＋1（以 `Room.rank_counts[(round, questionId)]` 維護）。`seq`、`rank` 寫入 `Submission` 後不提供任何更新路徑。
- **Rationale**: 單一事件迴圈只在 `await` 切換，同步區段天然序列化；處理序即「系統收到的先後」。時間戳記解析度有限，兩筆可能相同，不能作為唯一仲裁鍵；`seq` 保證嚴格全序、不並列、可重現。`submittedAt` 仍由後端 UTC 產生，供顯示與核對（原則 II、V）。
- **Alternatives**: 事後依 `submittedAt` 排序——相同時刻會並列且順位可能隨資料變動；`asyncio.Lock`——同步區段已足夠，多餘。

## D2：名次與看板分開——名次存、看板推導
- **Decision**: `rank` 是紀錄不可變欄位；看板（每題領先、名次清單、各組領先題數）每次由 `room.submissions` 過濾本輪後即時推導，不另存。
- **Rationale**: 避免出現可被改寫的第二份事實（資料完整性）；規模小（≤ 40 組 × ≤ 50 題）重算成本可忽略；重連還原只需重算。
- **Alternatives**: 另建 `SubmissionRank` 實體——與 `Submission` 一對一，徒增複雜度（簡潔性原則）；快取看板——小規模不需要。

## D3：看板推送——完整快照，而非差量
- **Decision**: 每筆新有效送出後，僅對老師連線送一則 `board`（本輪完整看板）；新一輪開始時送空白 `board`；snapshot 也含 `board`。
- **Rationale**: 完整快照讓老師端狀態永遠收斂、不需處理漏事件或順序問題；資料量小。
- **Alternatives**: 差量更新——需處理斷線補送與順序，無明顯收益。

## D4：保密——名次不進學生事件
- **Decision**: `to_group_event` 與 `to_other_groups_event` 不變（不含 rank）；`joined` 不含 rank；`board` 與老師 `submission` 事件（新增 `rank`）只經 `broadcast_to_teachers`。
- **Rationale**: FR-012、FR-013；名次與領先資訊屬競賽敏感資訊。以測試掃描所有學生連線訊息驗證。

## D5：領先題數的定義
- **Decision**: `leadTally[組名]`＝本輪該組為第 1 名的題數；只列出至少領先一題的組別，依題數由大到小、同數依組名排序。「尚無組別送出」的題目 `leader` 為 `null`。
- **Rationale**: 對應規格 FR-008；僅是進度參考，不是計分或獲勝（FR-014）。

## D6：新一輪
- **Decision**: 看板只取 `round == room.round` 的紀錄，新一輪開始自然為空；`phase.py` 開始搶答時額外推一則空白 `board` 給老師。舊紀錄（含舊 `rank`、`seq`）保留；`rank_counts` 以 `(round, questionId)` 為鍵，不需重設。
