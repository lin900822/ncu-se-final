# Research: 搶答結果公布看板

規格無 NEEDS CLARIFICATION。以下為設計決策（基於 Step 2 `phase`、Step 4/5 `submissions`/`ranking`、`Realtime`）。

## D1：結果由名次 1 推導，不另存
- **Decision**: `results.build_result(room)` 取本輪（`room.round`）各題 `rank == 1` 的送出，輸出 `[{questionId, winnerGroup, answer}]`（依題目順序；無人送出為 `null`）。僅在 `room.phase == "Ended"` 時回傳結果，其餘階段回 `None`。
- **Rationale**: 階段為 Ended 後，`submit()` 的階段閘門拒絕新送出，該輪紀錄凍結，推導結果天然確定、不可改寫（FR-011）；不另存即沒有第二份可能不一致的事實（資料完整性）。
- **Alternatives**: 結算時存快照——多一份狀態且需處理重置；快取——規模小不需要。

## D2：公布時機與事件
- **Decision**: `end_answering` 在階段變更廣播之後，送一則 `round_result`（`{round, results}`）給「全體學生連線」與老師。僅在階段實際由 Answering 變為 Ended 時送（`changed == True`）；重複結束不再送。
- **Rationale**: FR-002、FR-011；階段先到、結果隨後，客戶端以「Ended 且有結果」切換畫面，兩則事件順序不影響最終狀態。
- **Alternatives**: 把結果夾進 `phase_changed`——污染原本「不含作答內容」的房間層級訊息（Step 2 約束）。

## D3：學生廣播與保密
- **Decision**: 於 `Realtime` 新增專用 `broadcast_result(code, message)`，對房間所有學生連線送出；其 docstring 明列「僅限結算後的公布結果（每題第 1 名組名＋答案）」。`broadcast_to_students` 的禁令維持不變。
- **Rationale**: 憲法原則 III 允許結算後公布獲勝內容；以獨立方法隔離，靜態測試可確認只有結果事件使用它，其他路徑仍受原禁令約束。
- **Alternatives**: 放寬 `broadcast_to_students`——會削弱既有保護與靜態掃描。

## D4：還原（加入／重連／晚加入）
- **Decision**: 學生 `joined` 新增 `result`：房間 Open 且階段 Ended 時為 `build_result` 結果，其餘為 `null`。老師 `snapshot.room` 新增 `result`（同規則）。
- **Rationale**: FR-008、FR-013；後端為事實來源。`room_closed` 房間既有行為不變。

## D5：「本組搶下」的判定
- **Decision**: 由學生端以 `winnerGroup === 自己的組名` 判斷（`joined.group.name` 與結果中的 `winnerGroup` 皆為同一個顯示組名）。
- **Rationale**: 避免為每組分別送不同內容；比對只用已公布的資訊，不洩漏任何額外內容。

## D6：新一輪
- **Decision**: 開始新一輪時階段變為 Answering，`build_result` 回 `None`；學生端收到 `phase_changed(Answering)` 即清除結果並回到作答畫面；重連的 `joined.result` 為 `null`。舊輪紀錄與名次保留（僅追加）。
- **Rationale**: FR-010、SC-008。

## D7：老師端
- **Decision**: 老師端沿用 Step 5 進度板作為最終結果：已結束階段於標題標示「最終結果」；`round_result` 事件與 `snapshot.result` 讓老師端可核對與學生端一致。不新增獨立頁面。
- **Rationale**: Assumptions；最小改動。
