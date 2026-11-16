# WebSocket Contract（Step 12 新增與修改）

## 投影 `/ws/projector?code=<房間代碼>&key=<投影憑證>`（新增，唯讀）

### 連線
- 驗證：房間存在且 `key` 以常數時間比對等於 `projector_key`。
- **失敗**（key 錯誤、使用老師 token／恢復碼、房間不存在或已被清除）：伺服器送 `{"type":"projector_unavailable"}` 並以 `1008` 關閉；兩種失敗訊息完全相同（不洩漏房間是否存在）。前端收到後顯示「無法顯示」且**不再重連**。
- 成功：立即送一則 `projector_state`（見下）。若房間已 `Closed`，該狀態 `status:"Closed"`，隨後伺服器關閉連線（`1000`）。
- 連線本身與其送來的任何訊息：**一律忽略**（不改房間狀態、不更新 `last_activity_at`、不計為組別）。

### `projector_state`（伺服器 → 投影；整份狀態）
```json
{
  "type": "projector_state",
  "code": "AB12CD", "status": "Open", "phase": "Answering", "round": 2,
  "groups": ["第 1 組", "第 2 組"],
  "questions": [{"id":"1","label":"Q1","bundleId":null}],
  "bundles": [{"id":"B1","questionIds":["3","4"]}],
  "progress": {"answered": 3, "total": 6},
  "submitted": {"1": true, "2": false, "B1": true},
  "result": null,
  "scoreboard": [{"group":"第 1 組","score":4,"rank":1},{"group":"第 2 組","score":2,"rank":2}]
}
```
- 欄位定義見 [data-model.md](../data-model.md)。`submitted`／`progress` 只在 `Answering`；`result` 只在 `Ended`，格式與學生 `round_result` 的 `{round, results[]}` **完全相同**。
- **搶答中不含**：任何送出組別的歸屬、答案、`rank`、`seq`、`submittedAt`、`outcome`、讓位／保留／名次落後。
- 推送時機：連線時、階段變更、新紀錄的送出、審核成功、新組別加入、房間結束。

### `countdown`（伺服器 → 投影；一次性）
```json
{ "type": "countdown", "round": 2 }
```
- 只在老師**實際**開始搶答（階段由非 Answering 變 Answering）時，對**當下已連線**的投影送出一次；順序固定為：先送 Answering 的 `projector_state`，再送 `countdown`。
- 重複按開始（冪等）、重連、晚連線**不會**收到。前端收到後播放約 3 秒動畫（`prefers-reduced-motion` 時逐秒靜態數字），結束後顯示進度看板。
- 不含任何仲裁資訊；學生端開放輸入的時間與 `phase_changed` 不受影響。

## 老師 `/ws/teacher`（修改）
### `snapshot.room`（新增 `projectorKey`）
```json
{ "type": "snapshot", "room": { "...": "...", "projectorKey": "…" } }
```
- 僅老師可見；換裝置恢復後相同。

## 學生 `/ws/student`（不變）
- 學生任何訊息**不得**出現 `projectorKey`、`projector_state`、`countdown`、`scoreboard`。
