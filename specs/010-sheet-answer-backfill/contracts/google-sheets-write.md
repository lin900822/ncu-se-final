# External Contract：寫入 Google Sheets

本系統對 Google 的**唯一**寫入呼叫。固定網域 `sheets.googleapis.com`（不使用使用者提供的主機名稱）；逾時 10 秒；錯誤與日誌不含金鑰內容。

## 權限範圍（OAuth scope）

| 動作 | 範圍 |
|------|------|
| 讀取試算表（建立房間預覽、回填預覽與確認的指紋驗證、現況比對） | `https://www.googleapis.com/auth/spreadsheets.readonly`（`SHEETS_SCOPE`，不變） |
| **回填寫入** | `https://www.googleapis.com/auth/spreadsheets`（`SHEETS_WRITE_SCOPE`，新增，只用於寫入） |

服務帳號 JSON 金鑰不變；機器人 email 必須被該試算表共用為**編輯者**。

## 請求：`POST https://sheets.googleapis.com/v4/spreadsheets/{spreadsheetId}:batchUpdate`

```json
{
  "requests": [
    {
      "updateCells": {
        "range": { "sheetId": 0, "startRowIndex": 5, "endRowIndex": 6, "startColumnIndex": 7, "endColumnIndex": 8 },
        "rows": [ { "values": [ { "userEnteredValue": { "stringValue": "=1+1" } } ] } ],
        "fields": "userEnteredValue"
      }
    },
    {
      "updateCells": {
        "range": { "sheetId": 0, "startRowIndex": 6, "endRowIndex": 7, "startColumnIndex": 7, "endColumnIndex": 8 },
        "rows": [ { "values": [ {} ] } ],
        "fields": "userEnteredValue"
      }
    }
  ]
}
```

規則：
1. **一次請求包含所有要寫入與清空的格**（一個作答格一個 `updateCells`）；Google 對整批請求先驗證再套用，任一無效則**整批不生效** → 全有或全無。
2. `sheetId` 取自房間記錄的 `SheetSource.sheet_id`；列／欄為 0 起算、結束不含，由作答格位址（`'分頁'!H6` → row 5、col 7）解析而來。
3. 寫入以 `userEnteredValue.stringValue` 送出：**文字原樣儲存**，`=` 開頭不會被當成公式、`007`／`3/4` 不會被轉成數字或日期；換行與特殊字元保留。
4. 清空：該格的 `values` 為空物件 `{}`，欄位遮罩仍為 `userEnteredValue`。
5. `fields` 固定為 `"userEnteredValue"`：**只寫值，不改格式、資料驗證、合併設定**；請求中沒有任何其他格或其他分頁。
6. 不使用 `values:update`／`USER_ENTERED`（會解析公式與數字）。

## 回應對應

| Google 回應 | 本系統錯誤碼 |
|-------------|--------------|
| `200` | 成功 |
| `401`、`403` | `SHEET_NOT_EDITABLE`（`details.serviceAccountEmail`） |
| `404` | `SHEET_NOT_FOUND` |
| `429` | `SHEET_QUOTA` |
| `400` 且訊息含 `protected` | `SHEET_NOT_EDITABLE` |
| 其他 `400` | `SHEET_WRITE_FAILED` |
| 連線逾時、`5xx`、無法解析 | `SHEET_TIMEOUT` |

## 讀取（沿用 Step 3，補充用途）
回填的預覽與確認都先以唯讀範圍重新讀取該分頁（`sheets(properties,merges,data(rowData(values(formattedValue))))`），
用於：(1) 重新 `parse_questions` 並以 `fingerprint_of` 比對房間記錄的指紋（結構驗證）；(2) 取得目標格的目前內容（覆寫計數與清空判斷）。
