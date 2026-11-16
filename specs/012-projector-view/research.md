# Research: 教室大螢幕投影專用視圖

規格中的三項取捨已於 Clarifications 確認；以下為設計決策。

## D1. 投影視圖走獨立的唯讀 WebSocket，而不是複用老師通道
- **Decision**: 新增 `/ws/projector?code=&key=`；伺服器忽略該連線上的任何客戶端訊息，只推送。
- **Rationale**: 老師通道含答案、名次、審核與控制動作的資料與權限；投影網址會放在大螢幕與瀏覽器歷史中，必須是「即使外流也無害」的憑證。獨立通道讓保密由伺服器決定。
- **Alternatives**: (a) 用老師 token 開唯讀模式——外流即全面失守，且 token 會出現在網址；(b) 投影頁輪詢 REST——延遲高、需另做斷線還原；(c) 學生通道扮成組別——會污染組別清單與在線狀態。

## D2. 憑證：房間建立時產生的 `projector_key`
- **Decision**: 與老師 token、恢復碼不同的隨機權杖，建立時產生、房間存續期間固定；放在投影網址 query（`code`、`key`）。老師端由 `snapshot.room.projectorKey`／建立回應取得，換裝置恢復後仍相同。
- **Rationale**: 簡單、可重現；投影可看到的內容等同全班公開內容，因此即使 key 外流風險有限（Assumption：不提供作廢）。比對用常數時間比較；錯誤回應對「房間不存在」與「key 錯誤」完全相同，不洩漏房間是否存在。
- **Alternatives**: 以老師 token 衍生簽章（無狀態）——更複雜且無實益；每次開啟產生一次性 key——投影重新整理就失效，違背「重新整理可還原」。

## D3. 推送整份狀態，而不是增量事件
- **Decision**: `projector.build_state(room)` 是純函式；連線時與每次相關事件後推送整份 `projector_state`。
- **Rationale**: 畫面無狀態、重連與重新整理自然還原、不會顯示過期看板（FR-009）；資料量很小（30 題 × 20 組以內）。測試只要斷言整份狀態的保密與正確。
- **Alternatives**: 增量事件＋客戶端合併——易漂移、需要補同步；只推「請重新抓」再 REST 取——多一個端點與一次往返。

## D4. 保密：由後端建構「全班公開」資料，搶答中不產生敏感欄位
- **Decision**: Answering 時狀態只含各單位 `submitted`（布林）與 `{answered,total}`、以及已結算輪次的累計得分與組別名單；結算後的得主直接用 `results.build_result()`（與學生端同一份）。
- **Rationale**: 憲章 III；以「根本不產生」取代「前端隱藏」，並以逐則序列化斷言測試。排行榜與名單只含組別名稱與已結算得分，與當輪送出無關。
- **Alternatives**: 搶答中顯示領先組名——已於 clarify 否決。

## D5. 得分＝已結算各輪 `allocate().wins` 累計
- **Decision**: 已結算輪次＝階段為 Answering 時 `1..round-1`，其他階段 `1..round`；對每輪呼叫 `effective.allocate(room, n)` 取 `wins`（含 Step 11 讓位後與「保留」、題組 N 題計 N）並相加；排名用「競賽排名」（同分並列、下一名跳號），同分以組名排序。
- **Rationale**: 重用唯一的獲勝者推導來源，審核與公平規則自動連動；各輪各自以該輪的審核與規則計算，不需新儲存。
- **Alternatives**: 另存計分表——與紀錄可能不一致；每題固定 1 分——與題組計法重複，已確認採題數。

## D6. 倒數動畫：一次性 `countdown` 事件
- **Decision**: `start_answering` 確實切換階段、廣播學生／老師事件之後，先 `publish` 新狀態，再對已連線的投影送 `{type:"countdown", round}`；前端收到後覆蓋播放約 3 秒，之後顯示進度看板。重連或晚連線只收到 `projector_state`，不補播。
- **Rationale**: 純視覺、不改階段規則與學生端時序（clarify 已確認）；事件與狀態分離讓重新整理不重播。
- **Alternatives**: 以 `phase_changed` 推導——重連會誤播；新增「倒數中」階段——已於 clarify 否決。

## D7. 前端：獨立頁面、無互動元件、減少動態效果
- **Decision**: 新增 `/projector` 路由與頁面，不含按鈕與輸入；用 CSS `clamp()`／`vh` 放大字級與格線自動分欄（題目多時縮小、不捲動）；倒數用 CSS keyframes，並在 `prefers-reduced-motion` 下改為逐秒靜態數字。連線用既有 `useReconnectingSocket`（指數退避重連），斷線時顯示「連線中斷，重新連線中」；投影被拒（`projector_unavailable`）時顯示「無法顯示」且不再重連。
- **Rationale**: 零新依賴；重用重連機制；滿足 SC-005、SC-007、FR-014。

## D8. 房間結束與保留
- **Decision**: `close_room` 對投影推送最終狀態（`status:"Closed"`）後關閉連線；房間仍在保留期內時，新連線收到 `Closed` 狀態後即被關閉，前端顯示「房間已結束」並保留最後內容；超過保留期（房間已被清除）等同不存在。
- **Rationale**: 符合 FR-011，與既有 24 小時保留一致。

## D9. 投影連線不計入組別與活動時間
- **Decision**: `Realtime.projectors` 獨立登記；不進 `students`、`teachers`；`has_connections` 不計入（不阻止閒置逾時）；連線與忽略的訊息都不呼叫 `rooms.touch`。
- **Rationale**: FR-010；避免大螢幕開著讓房間永遠不逾時。
