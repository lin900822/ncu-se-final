# REST Contract（Step 8 新增）

WebSocket 協定**完全不變**（學生端與老師端皆無修改）。

## `GET /api/rooms/{code}/records.csv`（匯出紀錄）

### Request
```http
GET /api/rooms/AB12CD/records.csv
Authorization: Bearer <老師憑證>
```
- 憑證**只接受標頭**；網址參數（如 `?token=`）一律忽略，視同未帶憑證。
- 沒有 request body；不接受篩選參數（FR-023）。
- 房間代碼大小寫不拘（沿用既有正規化）。

### Response 200
```http
HTTP/1.1 200 OK
Content-Type: text/csv; charset=utf-8
Content-Disposition: attachment; filename="records_AB12CD_20261111.csv"; filename*=UTF-8''%E6%90%B6%E7%AD%94%E7%B4%80%E9%8C%84_AB12CD_20261111.csv
Cache-Control: no-store

﻿輪次,題號,題組,組別,答案,接收時間,排名
...
```
- 本文格式見 [csv-format.md](./csv-format.md)。
- 內容為呼叫當下的完整快照；包含所有輪次的有效送出。
- 房間狀態不限：搶答中、已結束、房間已結束（保留期內）皆可。
- **唯讀**：不修改任何紀錄、不更新房間最後活動時間。

### 錯誤（沿用既有 JSON 格式 `{"error": {"code","message"}}`）

| HTTP | code | 觸發 | 訊息 |
|------|------|------|------|
| 401 | UNAUTHORIZED | 無標頭、憑證錯誤，或已被換裝置後的新憑證取代 | 無權限操作此房間 |
| 404 | RECORDS_GONE | 房間不存在（超過 24 小時保留期被清除，或服務重啟） | 紀錄已不存在，請於活動結束後盡快匯出 |
| 404 | NO_RECORDS | 房間存在、憑證正確，但沒有任何有效送出 | 尚無送出紀錄可匯出 |

- 所有錯誤的回應本文**不含任何答案、組名或其他紀錄內容**。
- 檢查順序：房間是否存在（`RECORDS_GONE`）→ 憑證（`UNAUTHORIZED`）→ 是否有紀錄（`NO_RECORDS`）。
  憑證錯誤時不會洩漏房間是否有紀錄。

### 前端行為（非契約，供對照）
- 以 `fetch` 帶標頭取得 Blob，再以 `<a download>` 觸發下載；檔名由前端以**本地日期**命名為 `搶答紀錄_<CODE>_<YYYYMMDD>.csv`。
- `NO_RECORDS`、`RECORDS_GONE` 顯示訊息、不下載；`UNAUTHORIZED` 視為老師身分失效。
