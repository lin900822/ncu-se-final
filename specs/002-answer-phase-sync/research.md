# Research: 活動階段同步

規格與技術脈絡無 NEEDS CLARIFICATION；以下為設計決策。

## D1：階段觸發走 REST，還是老師 WebSocket 訊息？
- **Decision**: REST `POST /api/rooms/{code}/phase/start|end`，Bearer 老師憑證。
- **Rationale**: 與既有 `close` 一致；有明確 HTTP 回應（成功/401/409）；老師 WebSocket 目前是純接收通道，不需增加訊息處理分支。
- **Alternatives**: 老師 WS 發 `start`/`end` 訊息——延遲略低但需自建回應與錯誤通道，收益不足。

## D2：階段集合與「結束後」語意
- **Decision**: `Waiting`、`Answering`、`Ended`；`Ended` 可再 `start`（多輪）；每次 `start` 令 `round += 1`。
- **Rationale**: 規格要求「已結束」提示與「等待」不同，且可重複開始。`round` 讓學生端可區分「同輪重連」與「新一輪」，用來實現「每次開始搶答清空輸入框」（Clarification Q2），避免重連（同輪）時誤清空或舊文字殘留。
- **Alternatives**: 僅用兩態——無法區分提示文字；以時間戳判斷輪次——不必要的複雜度。

## D3：冪等
- **Decision**: `start` 於 `Answering`、`end` 於非 `Answering` 時，回 200 與目前階段，不改狀態、不廣播、不追加紀錄。
- **Rationale**: 連點與重送安全（FR-009），也避免廣播風暴與重複紀錄。
- **Alternatives**: 回 409——前端需額外處理，對老師無價值。

## D4：廣播範圍與內容
- **Decision**: `phase_changed` 同時送老師與該房間所有學生連線；內容僅 `phase`、`round`、`changedAt`。
- **Rationale**: 全班同步（FR-005）；符合原則 III。Step 1 的 `Realtime` 刻意沒有向學生廣播的方法，新增 `broadcast_to_students` 時其簽名只接受階段訊息，並以測試守住內容欄位。
- **Alternatives**: 學生輪詢——不即時且浪費。

## D5：重連還原
- **Decision**: 學生 `joined` 回應與老師 `snapshot` 內附 `phase`、`round`；前端以此為準，不採用本地快取判斷可否作答。
- **Rationale**: 憲法「斷線重連後由後端還原」；Step 1 已有「連線即快照」模式，增量最小。

## D6：後端鎖定閘門（FR-007）
- **Decision**: 學生 WS 新增 `{"type":"submit"}` 處理：非 `Answering` 回 `{"type":"error","code":"PHASE_LOCKED"}`（不關閉連線）；`Answering` 時本步驟不儲存內容、不回應，留給 Step 3。
- **Rationale**: 規格要求鎖定時送出被拒；先放置閘門讓 Step 3 直接接上，並可被測試驗證。
- **Alternatives**: 完全不做——FR-007 無法驗證。

## D7：階段紀錄
- **Decision**: `Room.phase_log: list[PhaseChange]` 僅追加（phase、round、changedAt UTC、by="Teacher"）。
- **Rationale**: FR-012 與憲法 append-only；歷程匯出為後續步驟，本步驟不提供讀取 API。

## D8：前端輸入框鎖定
- **Decision**: 學生端新增禁用的 `<textarea>`/輸入框，`disabled` 由階段是否為 `Answering` 決定；鎖定時顯示「等待搶答」或「搶答已結束」；輸入框文字僅在 `round` 增加時清空。
- **Rationale**: 滿足驗證效果；鎖定期間保留未送出文字（FR-010）。
