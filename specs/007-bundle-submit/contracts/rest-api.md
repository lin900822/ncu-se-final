# REST Contract（相對 Step 3 的修改）

## `POST /api/rooms`（建立房間）

### Request（新增 `bundles`）
```json
{
  "sheetUrl": "https://docs.google.com/spreadsheets/d/…",
  "fingerprint": "sha256 hex",
  "bundles": [["3", "4"], ["1-2", "2-1"]]
}
```
- `bundles`：選填；每個內層陣列為一個題組的 questionId（取自預覽回應的 `questions[].id`），順序不拘，伺服器依題目順序整理。
- 處理順序：讀取試算表 → 比對指紋（`SHEET_CHANGED`）→ **驗證題組** → 建立房間。任何一步失敗都不建立房間。
- 未帶 `sheetUrl` 時 `bundles` 必須省略、為 `null` 或 `[]`。

### Response 201（新增 `bundles`）
```json
{
  "code": "…", "teacherToken": "…", "recoveryCode": "…", "createdAt": "…",
  "sheetTitle": "學習單",
  "questions": [{ "id": "3", "number": 3, "sub": null, "label": "Q3" }],
  "bundles": [{ "id": "B1", "questionIds": ["1-2", "2-1"] }, { "id": "B2", "questionIds": ["3", "4"] }]
}
```
題組 id 依第一個成員在題目清單中的位置編號。

### 新增錯誤
| HTTP | code | 觸發 | 訊息 |
|------|------|------|------|
| 400 | BUNDLES_INVALID | 見下表任一原因 | 題組設定有誤 |

`details`：
```json
{ "reason": "TOO_FEW | NOT_ADJACENT | OVERLAP | UNKNOWN_QUESTION | NO_QUESTIONS", "questionIds": ["2", "5"] }
```

| reason | 觸發 |
|--------|------|
| TOO_FEW | 某題組少於 2 題（含同組重複後剩 1 題） |
| NOT_ADJACENT | 成員在題目清單中不連續 |
| OVERLAP | 同一題出現在兩個題組，或同組內重複 |
| UNKNOWN_QUESTION | 成員不是本房間的題目 |
| NO_QUESTIONS | 房間沒有題目卻帶了題組 |

前端在預覽頁先做相同檢查以即時提示（題組至少 2 題／只能相鄰／一題只能屬於一個題組），但以伺服器結果為準。

## 其他端點
`POST /api/sheets/preview` 不變（題組只在前端預覽頁暫存，確認建立時才送出）。
