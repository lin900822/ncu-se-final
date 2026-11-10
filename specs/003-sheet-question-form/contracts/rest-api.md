# REST Contract（新增與修改）

錯誤格式沿用 `{ "error": { "code", "message", "details"? } }`。

## `POST /api/sheets/preview`（新增，無需憑證）

Body：`{ "url": "https://docs.google.com/spreadsheets/d/<id>/edit#gid=0" }`

成功 `200`：
```json
{
  "sheetTitle": "學習單",
  "questions": [
    { "id": "1-1", "number": 1, "sub": 1, "label": "Q1（1）" },
    { "id": "1-2", "number": 1, "sub": 2, "label": "Q1（2）" },
    { "id": "3",   "number": 3, "sub": null, "label": "Q3" }
  ],
  "fingerprint": "sha256 hex"
}
```
回應**不含**儲存格位置、題目文字與試算表其他內容。

| HTTP | code | 觸發 | 訊息（繁中） |
|------|------|------|--------------|
| 400 | SHEET_URL_INVALID | 不是有效的 Google Sheet 連結 | 請貼上有效的 Google Sheet 連結 |
| 503 | SHEETS_NOT_CONFIGURED | 伺服器未設定 `GOOGLE_SERVICE_ACCOUNT_FILE` 或金鑰檔無法載入 | 伺服器尚未設定 Google 機器人 |
| 403 | SHEET_FORBIDDEN | Google 回 403 | 無法讀取，請將試算表共用給 `<機器人 email>`（`details.serviceAccountEmail`） |
| 404 | SHEET_NOT_FOUND | Google 回 404 | 找不到該試算表 |
| 504 | SHEET_TIMEOUT | 呼叫逾時（10 秒）或網路失敗 | 讀取逾時，請稍後再試 |
| 422 | SHEET_FORMAT_UNRECOGNIZED | 找不到「題號／題目／作答」表頭 | 無法辨識學習單格式 |
| 422 | SHEET_NO_QUESTIONS | 有表頭但沒有任何題號 | 找不到填空格 |
| 422 | SHEET_QUESTIONS_INVALID | 題號重複／缺漏、小題不連續、題號數與作答格數不一致 | 題號有問題（`details`：`duplicates`、`missing`、`invalidSubs`，以及題號下沒有作答格時的 `empty`） |
| 422 | SHEET_TOO_MANY_QUESTIONS | 超過 50 題 | 題數超過上限（50） |

## `POST /api/rooms`（修改：Body 改為選填）

- 無 Body 或空 Body：行為同 Step 1（無題目）。
- 帶 Body：`{ "sheetUrl": "...", "fingerprint": "..." }`，後端**重新讀取**並比對指紋。

成功 `201`：原有欄位（`code`、`teacherToken`、`recoveryCode`、`createdAt`）＋
```json
{ "sheetTitle": "學習單", "questions": [ { "id": "1", "number": 1, "sub": null, "label": "Q1" } ] }
```
（無連結時 `questions: []`、`sheetTitle: null`）

額外錯誤：`SHEET_*`（同預覽）與

| HTTP | code | 觸發 | 訊息 |
|------|------|------|------|
| 409 | SHEET_CHANGED | 重新讀取後指紋與預覽不同 | 試算表內容已變動，請重新讀取並確認 |
| 400 | BAD_REQUEST | 只帶 `sheetUrl` 或只帶 `fingerprint` | 請求格式錯誤 |

任何錯誤皆**不建立房間**（FR-004）。

## 不變
`/recover`、`/close`、`/phase/start|end`、`/status` 行為不變。恢復後（recover）的回應不含題目；題目由老師 WebSocket 的 `snapshot` 取得。
