# REST Contract（Step 10 新增）

學生 WebSocket 與學生端不新增任何回填相關訊息或入口；兩個端點皆僅老師可用，憑證**只放 `Authorization: Bearer` 標頭**（網址參數無效）。
房間已結束但仍在保留期（24 小時）內仍可使用（沿用 Step 8）。

## `POST /api/rooms/{code}/backfill/preview`（預覽，唯讀）

### Request
```http
POST /api/rooms/AB12CD/backfill/preview
Authorization: Bearer <老師憑證>
Content-Type: application/json

{ "round": 1 }
```
`round`：老師畫面上目前的輪次，必須等於房間最新一輪。

### Response 200
```json
{
  "round": 1,
  "sheetTitle": "學習單",
  "sheetUrl": "https://docs.google.com/spreadsheets/d/abc123/edit#gid=0",
  "canBackfill": true,
  "counts": { "write": 5, "skip": 1, "clear": 0, "keep": 0, "overwrite": 2 },
  "items": [
    { "questionId": "1", "label": "Q1", "action": "write", "overwrite": true,  "answer": "CPU" },
    { "questionId": "2", "label": "Q2", "action": "skip",  "overwrite": false, "answer": null }
  ]
}
```
- `counts.write/skip/clear/keep` 加總等於房間題目數；`counts.overwrite` 為「寫入類中，目標格原本有內容且與答案不同」的格數。
- `items[].action`：`write`／`clear`／`keep`／`skip`；`answer` 只有 `write` 有值（老師自己的資料，僅老師端看得到）。
- `canBackfill == false`（寫入＋清空皆為 0）時前端顯示「沒有可回填的答案」，不提供確認。
- **唯讀**：不寫入試算表、不追加回填紀錄、不廣播；預覽階段的任何錯誤都不產生回填紀錄。

## `POST /api/rooms/{code}/backfill`（確認回填）

### Request
```json
{ "round": 1 }
```
伺服器**以確認當下**的有效結果與試算表現況重新推導計畫後寫入（不採用預覽的內容）。

### Response 200（成功）
```json
{
  "round": 1,
  "sheetUrl": "https://docs.google.com/spreadsheets/d/abc123/edit#gid=0",
  "counts": { "write": 5, "skip": 1, "clear": 0, "keep": 0 },
  "record": { "round": 1, "at": "2026-11-11T08:00:00Z", "written": 5, "skipped": 1, "cleared": 0, "kept": 0,
              "result": "Success", "reason": null, "message": null }
}
```
- 寫入為**單一批次、全有或全無**；成功後追加一筆 `Success` 紀錄並廣播 `backfill_updated`（見 [websocket.md](./websocket.md)）。

### 錯誤（沿用 `{"error": {"code","message","details?"}}`）

| HTTP | code | 觸發 | 是否記錄 |
|------|------|------|----------|
| 401 | UNAUTHORIZED | 無憑證、憑證錯誤、已被換裝置後的新憑證取代 | 否 |
| 404 | ROOM_NOT_FOUND | 房間不存在（超過保留期） | 否 |
| 400 | BACKFILL_NO_SHEET | 房間未綁定試算表 | 否 |
| 400 | BACKFILL_NOT_ALLOWED | 階段不是 Ended，或 `round` 不是最新一輪 | 否 |
| 409 | BACKFILL_IN_PROGRESS | 同房間已有回填進行中（僅確認端點） | 否 |
| 400 | BACKFILL_NOTHING | 寫入與清空皆為 0（僅確認端點） | 否 |
| 503 | SHEETS_NOT_CONFIGURED | 伺服器未設定機器人 | 否 |
| 403 | SHEET_FORBIDDEN | 讀取階段無權限（未共用給機器人）；`details.serviceAccountEmail` | **是**（確認端點） |
| 404 | SHEET_NOT_FOUND | 試算表或分頁不存在 | **是** |
| 409 | SHEET_STRUCTURE_CHANGED | 結構指紋不符或表頭無法辨識 | **是** |
| 403 | SHEET_NOT_EDITABLE | 寫入無編輯權限或受保護範圍；`details.serviceAccountEmail` | **是** |
| 429 | SHEET_QUOTA | 試算表服務額度已滿 | **是** |
| 502 | SHEET_WRITE_FAILED | 寫入被拒（其他 400） | **是** |
| 504 | SHEET_TIMEOUT | 連線逾時、5xx 或無法解析回應 | **是** |

- 「是否記錄」指**確認端點**在通過前置檢查、開始讀取之後發生的失敗，會追加一筆 `Failed` 紀錄（含 `reason` 錯誤碼）並廣播；前置檢查失敗不算回填嘗試。預覽端點的錯誤一律不記錄。
- **驗證順序固定**：憑證 → 房間存在 → 是否綁定試算表 → 階段與輪次 → （確認）進行中互斥 → 讀取與指紋驗證 → （確認）可做事項 → 寫入。
- **所有失敗都保證試算表未被改動**（驗證在寫入前、寫入為單一批次）。
- 所有錯誤的回應本文**不含任何答案內容**；錯誤與日誌不含服務帳號金鑰。
