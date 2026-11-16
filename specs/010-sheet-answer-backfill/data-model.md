# Data Model: 答案自動寫入回原 Google Sheet

僅列相對 Step 1～9 的新增與修改。所有資料仍僅存記憶體；時間一律為後端產生的 UTC。
**不修改** `Submission`、`ReviewRecord`、`Question`、`SheetSource`；回填只讀取它們。

## BackfillRecord（新增，僅追加）

老師每一次「確認回填」進入寫入流程的嘗試（成功或失敗各一筆）。

| 欄位 | 型別 | 規則 |
|------|------|------|
| `round` | int | 回填的輪次，必為當時最新一輪（`room.round`） |
| `by` | str | 操作者，固定 `"Teacher"` |
| `at` | datetime | 後端 UTC，建立時產生 |
| `written` | dict[str, str] | **成功才有內容**：`{作答格位址: 寫入的答案文字}`（僅供伺服器推導「先前寫入的格」，**不外送**） |
| `cleared` | list[str] | 成功時被清空的作答格位址（不外送） |
| `skipped_count` | int | 略過的題數（無有效答案且不需清空／保留） |
| `kept_count` | int | 保留不動的格數（先前由本系統寫入，但目前內容已被老師改過） |
| `result` | `"Success"` \| `"Failed"` | 結果 |
| `reason` | str \| None | 失敗時的錯誤碼（如 `SHEET_NOT_EDITABLE`）；成功為 `None` |

**不變式**：只追加、不修改、不刪除；失敗紀錄的 `written`、`cleared` 為空；`written` 的鍵必為該房間題目的 `cell`。

**公開格式** `backfill_public(r)`（老師端顯示用，**不含儲存格位置與答案內容**）：
```json
{ "round": 1, "at": "2026-11-11T08:00:00Z", "written": 6, "skipped": 0, "cleared": 0, "kept": 0,
  "result": "Success", "reason": null, "message": null }
```
失敗時 `result` 為 `"Failed"`、`reason` 為錯誤碼、`message` 為該錯誤的繁體中文訊息。

## Room（修改）

| 新增欄位 | 型別 | 說明 |
|----------|------|------|
| `backfills` | list[BackfillRecord] | 依時間先後追加；預設空 |

進行中的回填以服務層的「房間代碼集合」互斥，**不存在 `Room` 上**（重啟後自然清空）。

## 推導資料（不另存）

### 先前由本系統寫入的格 `system_written(room) -> dict[格, 文字]`
依時間先後套用所有 `result == "Success"` 的紀錄：先加入其 `written`（後者覆蓋前者），再移除其 `cleared` 的格。
Failed 紀錄不影響。

### BackfillPlan（回填計畫）
輸入：有效結果（`results.build_result`，僅 Ended 階段）、每題 `Question.cell`、`system_written`、試算表目前格線（讀取）。

| 類別 | 條件 | 動作 |
|------|------|------|
| **寫入 write** | 該題有有效第一名 | 把該組在**這一題**的答案原文寫入該題作答格 |
| **清空 clear** | 該題沒有有效第一名，且該格在 `system_written` 中，且目前內容 **等於** 當初寫入的文字 | 清空該格 |
| **保留 keep** | 該題沒有有效第一名，且該格在 `system_written` 中，但目前內容 **不等於** 當初寫入的文字（老師已改過） | 不動 |
| **略過 skip** | 該題沒有有效第一名，且該格不在 `system_written` 中 | 不動 |

**覆寫計數 `overwrite`**：寫入類中，目標格目前內容**非空且與答案不同**的格數（內容與答案相同不算覆寫）。
**可回填 `canBackfill`**：寫入數＋清空數 > 0。每題恰屬一類，總數等於房間題目數。

### 目前內容的比對
以讀取試算表得到的「顯示字串」（Step 3 的 `Grid`）判斷空白與相等；題組小題與一般題目一視同仁；合併儲存格以記錄的左上格為準。

## 驗證規則與狀態轉換

回填請求通過的條件（缺一即拒絕）：老師憑證有效 → 房間有 `sheet` → `phase == "Ended"` 且請求 `round == room.round` →（確認端點）沒有其他回填進行中 →
試算表可讀取且結構指紋與 `room.sheet.fingerprint` 相同 → 計畫的寫入＋清空數 > 0（確認端點，否則 `BACKFILL_NOTHING`）→ 批次寫入成功。

```text
（預覽）          讀取＋驗證指紋＋推導計畫 ──▶ 回傳摘要（不寫入、不記錄）
（確認）進行中集合加入 ──▶ 讀取＋驗證＋重新推導 ──▶ 單一批次寫入
         ├─ 成功 ──▶ 追加 Success 紀錄 ──▶ 廣播 ──▶ 回傳結果摘要
         └─ 失敗（讀取後的任何錯誤）──▶ 追加 Failed 紀錄 ──▶ 廣播 ──▶ 回傳錯誤（試算表未被改動）
         （finally）進行中集合移除
```

## 新增錯誤碼

| code | HTTP | 訊息 | 觸發 |
|------|------|------|------|
| `BACKFILL_NOT_ALLOWED` | 400 | 目前不開放回填，請於搶答結束後回填最新一輪 | 階段不是 Ended，或 `round` 不是最新一輪 |
| `BACKFILL_NO_SHEET` | 400 | 此房間未綁定試算表，無法回填 | `room.sheet is None` |
| `BACKFILL_NOTHING` | 400 | 沒有可回填的答案 | 確認時寫入數與清空數皆為 0 |
| `BACKFILL_IN_PROGRESS` | 409 | 回填進行中，請稍候 | 同房間已有回填在進行 |
| `SHEET_STRUCTURE_CHANGED` | 409 | 試算表已變動，請重新建立房間後再回填 | 指紋不符或表頭無法辨識 |
| `SHEET_NOT_EDITABLE` | 403 | 無法寫入，請將試算表共用給機器人並設為編輯者 | 寫入收到 401／403，或受保護範圍；`details.serviceAccountEmail` 為機器人 email |
| `SHEET_QUOTA` | 429 | 試算表服務使用額度已滿，請稍後再試 | 寫入收到 429 |
| `SHEET_WRITE_FAILED` | 502 | 寫入試算表失敗，未做任何變更 | 寫入收到其他 400 |

沿用：`UNAUTHORIZED`（401）、`ROOM_NOT_FOUND`（404）、`SHEET_FORBIDDEN`（讀取階段 403）、`SHEET_NOT_FOUND`（404）、`SHEET_TIMEOUT`（504）、`SHEETS_NOT_CONFIGURED`（503）。

## 對既有資料的影響

- `snapshot.room` 新增 `backfills`（公開格式清單）與 `sheetUrl`（`room.sheet.url`，僅老師）。
- 回填不改變 `results`、`board`、`reviews`、匯出 CSV 的任何內容。
