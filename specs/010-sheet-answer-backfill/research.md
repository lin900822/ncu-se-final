# Research: 答案自動寫入回原 Google Sheet

規格無 NEEDS CLARIFICATION（Clarifications 已確定：只回填最新一輪、無有效答案時清空先前寫入的格、先確認再寫入）。
以下為設計決策，基於 Step 3 試算表讀取與結構指紋、Step 8 保留規則、Step 9 有效結果與既有 `httpx`／服務帳號流程。

## D1：預覽與確認兩個端點，確認時重新計算
- **Decision**: `POST /api/rooms/{code}/backfill/preview`（唯讀：讀取試算表、驗證、推導計畫、回傳摘要）與
  `POST /api/rooms/{code}/backfill`（確認：重新讀取、重新推導、寫入、記錄）。確認時**不信任預覽的內容**，一律以當下結果與試算表現況重算。
- **Rationale**: FR-011、邊緣情況「按下回填與確認之間結果被審核更新」——以確認當下為準；兩個端點分離也讓「預覽不寫入」可被測試證明。
- **Alternatives**: 確認時帶回預覽的計畫直接寫入——結果可能已過期，風險更高；單一端點加 `confirm` 旗標——語意混雜、測試不直觀。

## D2：以「批次更新」＋字串值寫入（全有或全無、純文字）
- **Decision**: 寫入使用 Sheets API 的 `spreadsheets:batchUpdate`，每個目標格一個 `updateCells` 請求：
  `range` 為單一儲存格的 `GridRange`（`sheetId`、`startRowIndex`/`endRowIndex`、`startColumnIndex`/`endColumnIndex`），
  `rows[0].values[0].userEnteredValue = {"stringValue": "<答案原文>"}`，`fields = "userEnteredValue"`。清空則送出不含值的 `userEnteredValue`（欄位遮罩仍為 `userEnteredValue`）。
- **Rationale**:
  - `spreadsheets:batchUpdate` 的所有請求**以單一不可分割的更新套用**（任一請求無效則整批不生效）→ 滿足 FR-007 全有或全無；
  - `stringValue` 以文字儲存：`=1+1` 保持為文字而不是公式（公式必須用 `formulaValue`）、`007`、`3/4` 不會被自動轉成數字或日期 → 滿足 FR-006、SC-005；
  - `fields = "userEnteredValue"` 只寫值，不動格式、資料驗證、合併設定 → 滿足 FR-008、SC-003。
- **Alternatives**: `values:batchUpdate` 搭配 `USER_ENTERED`——會把 `=` 開頭解析成公式、字串解析成數字／日期，違反原文寫入；搭配 `RAW` 可保持文字，但全有或全無的保證較弱，且 A1 範圍字串需處理分頁名跳脫。

## D3：作答格位置——解析既有 A1 記錄，分頁以 sheetId 定位
- **Decision**: 新增 `sheets/a1.py` 的 `parse_a1(cell)`：解析 Step 3 記錄的 `'分頁名'!H6`（分頁名內的單引號以兩個單引號跳脫）為 0 起算的 `(row, col)`；
  寫入時使用房間記錄的 `SheetSource.sheet_id`（gid）當 `sheetId`，不用分頁名。
- **Rationale**: 位置沿用 Step 3 已驗證並記錄的作答格，不重新辨識（避免「題號數＝空格數」被重新判定而錯位）；`sheetId` 比分頁名穩定。
  合併儲存格：Step 3 記錄的是作答格的左上格，寫入左上格不改動合併設定。
- **Alternatives**: 另存列／欄座標——需改資料模型與既有測試；以 A1 字串當範圍——分頁改名時才會出錯，但本來就會被指紋攔下。

## D4：寫入前用 Step 3 的結構指紋再驗證（FR-009）
- **Decision**: 預覽與確認都先讀取試算表（沿用唯讀範圍的 `_fetch`），重新 `parse_questions`，以 `fingerprint_of(questions)` 與 `room.sheet.fingerprint` 比對；
  不符 → `SHEET_STRUCTURE_CHANGED`（409，「試算表已變動，請重新建立房間」），**不寫入任何格**。分頁被刪除 → 沿用 `SHEET_NOT_FOUND`。
  解析失敗（表頭被改壞）也一律視為結構變動。
- **Rationale**: 指紋由「題號＋作答格位址（含分頁名）」組成，插入列、改題號、改分頁名都會改變指紋；這與 Step 3「建立後題目固定、建立時比對指紋」是同一套機制。
- **Alternatives**: 只檢查目標格存在——無法偵測列被插入造成的錯位，正是 FR-009 要防的情況。

## D5：回填計畫推導規則（純函式，可獨立測試）
- **Decision**: `build_plan(room, grid)` 輸入有效結果（`results.build_result`）、題目作答格、先前成功回填紀錄、目前格線；輸出：
  - **寫入**：有有效第一名的題目 → `(題目, 作答格, 答案原文)`；**覆寫計數**＝目標格現有內容非空且與答案不同的格數（內容相同不算覆寫）；
  - **清空**：沒有有效第一名、但「先前由本系統寫入」的格，且目前內容**仍等於當初寫入的文字** → 清空；
  - **保留**：先前由本系統寫入、但目前內容已被老師改過 → 不動（計入 `kept`）；
  - **略過**：其餘沒有有效第一名的題目。
  「先前由本系統寫入的格」＝依時間先後套用所有**成功**回填紀錄（加入其 `written`、移除其 `cleared`）得到的 `{格: 最後寫入文字}`。
- **Rationale**: FR-005、Clarification Q2：只碰「本系統寫過」的格；格被老師改過就代表那不再是本系統的內容，不應清掉老師的字。
- **Alternatives**: 沒有有效答案一律不動——會殘留已被駁回的答案；一律清空——可能清掉老師自己打的內容。

## D4b：沒有可做的事
- **Decision**: 計畫的「寫入＋清空」為 0 時，預覽回 `canBackfill: false`；確認端點回 `BACKFILL_NOTHING`（400，「沒有可回填的答案」），**不寫入也不產生回填紀錄**（因為沒有發生回填嘗試）。
- **Rationale**: FR-014。

## D6：回填紀錄與「先前寫入的格」
- **Decision**: `Room.backfills: list[BackfillRecord]`，每次**嘗試**（通過驗證後進入寫入流程）追加一筆：輪次、UTC 時間、操作者、
  `written: dict[格, 文字]`（成功才有內容）、`cleared: list[格]`、`skipped_count`、`kept_count`、結果（`Success`／`Failed`）、失敗原因（錯誤碼）。
  公開格式（`backfill_public`）只含時間、輪次、四個格數、結果與原因訊息，**不含儲存格位置與答案內容**；內含答案的 `written` 只供伺服器推導，不外送。
- **Rationale**: FR-016、FR-017、原則 III；紀錄存記憶體，與其他紀錄相同（房間結束後保留 24 小時、重啟即消失——已寫入規格假設）。
- **Alternatives**: 另存「目前已回填格」表——第二份事實來源，且可能與紀錄不一致。

## D7：重複與併發——同房間一次只允許一個回填
- **Decision**: 服務內以「進行中房間代碼集合」作為互斥：確認端點在進入寫入前（同步區段）檢查並加入集合，結束時（`finally`）移除；
  已在集合中則回 `BACKFILL_IN_PROGRESS`（409）。預覽不受影響。
- **Rationale**: FR-015、US4-6、SC：連點或兩視窗同時確認只會有一次寫入、一筆紀錄；循序的第二次回填（第一次已完成）是正常的新一次回填。前端也在確認期間停用按鈕。
- **Alternatives**: `asyncio.Lock` 讓第二次排隊——結果相同卻會多一次寫入與一筆紀錄，與規格「只執行一次」不符。

## D8：權限範圍——只有寫入才用讀寫範圍
- **Decision**: `config.py` 保留 `SHEETS_SCOPE`（唯讀，既有測試斷言不變），新增 `SHEETS_WRITE_SCOPE = ".../auth/spreadsheets"`；
  `SheetsClient` 的 token provider 依動作指定範圍：讀取＝唯讀、寫入＝讀寫。預覽與指紋驗證（讀取）仍用唯讀。
- **Rationale**: FR-021 最小權限；Step 3 註解本來就預告「回填步驟才改為讀寫」。服務帳號 JSON 金鑰同一把即可取得不同範圍的權杖，不需要新憑證。
- **Impact**: 試算表必須共用給機器人為**編輯者**（Step 3 的「檢視者」不足），README 同步更新。

## D9：外部錯誤對應（寫入）
- **Decision**: 寫入回應：`401/403` → `SHEET_NOT_EDITABLE`（403，附機器人 email）；`404` → `SHEET_NOT_FOUND`；`429` → `SHEET_QUOTA`（429，「試算表服務使用額度已滿，請稍後再試」）；
  `400` 且訊息含 `protected`（受保護範圍）→ `SHEET_NOT_EDITABLE`；其他 `400` → `SHEET_WRITE_FAILED`（502，「寫入試算表失敗，未做任何變更」）；
  連線逾時、`5xx`、無法解析 → `SHEET_TIMEOUT`。錯誤本文與日誌不含金鑰內容（沿用 Step 3）。
- **Rationale**: FR-019、FR-020。**預覽是唯讀，無法事先得知機器人是否有編輯權限**，所以「需要編輯者」會在老師按下確認、實際寫入時才被發現（並記為失敗紀錄）。
- **Alternatives**: 預覽時先做一次無害寫入探測——會在老師尚未確認前就改動試算表，不可接受；呼叫 Drive API 查權限——需要額外範圍與依賴。

## D10：時機與權限
- **Decision**: 預覽與確認皆需：老師憑證（沿用 `verify_teacher`，房間 Closed 在保留期內仍可）→ 房間有 `sheet`（否則 `BACKFILL_NO_SHEET`）→
  `phase == "Ended"` 且請求 `round == room.round`（否則 `BACKFILL_NOT_ALLOWED`）。憑證只讀標頭。
- **Rationale**: FR-001、FR-002、FR-018；與 Step 9 審核一致的「最新一輪、已結束」。

## D11：廣播與還原（僅老師）
- **Decision**: 成功或失敗的回填都在紀錄追加後送老師 `backfill_updated {backfills}`（整份覆蓋）；`snapshot.room` 新增 `backfills` 與 `sheetUrl`（供連結）。學生協定不變。
- **Rationale**: FR-017、原則 III。

## D12：前端互動
- **Decision**: `BackfillPanel`：按鈕「回填至 Google Sheet」（未綁定試算表／搶答未結束時停用並顯示原因）；點擊 → 呼叫預覽 → 顯示確認摘要
  （寫入 N 格、略過 M 題、清空 K 格、保留 X 格、其中 J 格原有內容將被覆寫，並可展開逐題清單）→「確認回填」「取消」；確認中停用按鈕；
  成功顯示結果摘要與「開啟試算表」連結；錯誤顯示伺服器訊息（`SHEET_NOT_EDITABLE` 附「請將試算表共用給〈email〉並設為編輯者」）；
  下方列出回填紀錄。`UNAUTHORIZED` 視為老師身分失效（與匯出、審核一致）。
- **Rationale**: SC-009（2 次點擊）、FR-011、FR-012、FR-017。
