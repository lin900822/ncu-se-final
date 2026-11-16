# WebSocket Contract（Step 10 新增與修改）

## 學生 `/ws/student`

**完全不變**：不新增任何回填相關訊息；`joined` 不含任何回填資訊；學生傳送回填類訊息（如 `{"type":"backfill"}`）一律被忽略。

## 老師 `/ws/teacher`

### `backfill_updated`（新增）
每次回填嘗試（成功或失敗）追加紀錄後，送給老師**所有視窗**，以整份清單覆蓋：

```json
{
  "type": "backfill_updated",
  "backfills": [
    { "round": 1, "at": "2026-11-11T08:00:00Z", "written": 5, "skipped": 1, "cleared": 0, "kept": 0,
      "result": "Success", "reason": null, "message": null },
    { "round": 1, "at": "2026-11-11T08:05:00Z", "written": 0, "skipped": 0, "cleared": 0, "kept": 0,
      "result": "Failed", "reason": "SHEET_NOT_EDITABLE",
      "message": "無法寫入，請將試算表共用給機器人並設為編輯者" }
  ]
}
```
- `backfills` 是**所有**回填紀錄（含舊輪），依時間先後；格式為公開格式，**不含儲存格位置與答案內容**。
- 只經 `realtime.broadcast_to_teachers` 發送。

### `snapshot.room`（修改）
- 新增 `backfills`：同上的完整清單（老師換裝置以恢復碼回復後仍可看到，沿用 Step 8 的保留規則）。
- 新增 `sheetUrl`：`room.sheet.url`（僅老師；未綁定試算表為 `null`），供「開啟試算表」連結。
- `board`、`result`、`reviews` 等其他欄位不變。

## 保密檢查（原則 III）
- 學生連線收到的所有訊息中，**不得**出現：`backfill_updated`、`backfills`、`sheetUrl`、回填紀錄與任何回填內容。
- 回填服務只被老師 HTTP 路由引用，學生 WebSocket 路徑與學生廣播不引用（靜態審核測試把關）。
