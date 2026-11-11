# Research: 搶答歷史紀錄 CSV 匯出

規格無 NEEDS CLARIFICATION（Clarifications 已確定：時間用 UTC、無人搶答不列、房間結束後保留期內可匯出）。
以下為設計決策，基於 Step 1 老師憑證、Step 4/5 `submissions`、Step 7 題組與既有房間保留機制。

## D1：匯出做成唯讀 HTTP 端點，不走 WebSocket
- **Decision**: `GET /api/rooms/{code}/records.csv`，沿用 `rooms.verify_teacher(code, token)` 驗證老師憑證；成功回 `200` 與 CSV。
- **Rationale**: 匯出是一次性下載，用 HTTP 最自然；WebSocket 是即時事件通道，不適合傳檔。
  `verify_teacher` 只比對憑證、不檢查房間狀態，因此房間結束後（24 小時保留期內，見 `main.py` 的 `CLOSED_RETENTION`）仍可匯出，
  直接滿足 US4，也不必新增任何狀態。
- **Alternatives**: 透過老師 WebSocket 傳整份 CSV——訊息過大且斷線時無法重試；`POST` 端點——此操作不改變狀態，用 `GET` 才符合語意。

## D2：憑證放標頭，不放網址
- **Decision**: 使用 `Authorization: Bearer <老師憑證>`，與其他老師端點一致；網址參數的憑證一律無效。前端以 `fetch` 取得 Blob 再觸發下載，
  而不是直接用 `<a href>` 指向端點。
- **Rationale**: 憑證若出現在網址，會進入瀏覽器歷史、伺服器存取日誌與 Referer，等於把老師身分外洩（憲章原則 III 與隱私）。
  瀏覽器的 `<a href>` 下載無法附加自訂標頭，所以必須用 `fetch`。
- **Alternatives**: 短效下載連結（一次性 token）——需新增儲存與過期機制，違反簡潔性，且在單機課堂情境沒有必要。

## D3：資料來源與排序——直接讀送出紀錄，不重算
- **Decision**: 在單一同步區段內走訪 `room.submissions`（所有輪次），每筆有效送出輸出一列；排序鍵 `(round, 題目在 room.questions 中的順序, rank)`。
  題組成員各有一筆紀錄，因此自然是「各題一列」，同一次題組送出的各列 `submitted_at`、`rank`、組別相同（Step 7 的不變式）。
- **Rationale**: 名次與時間在送出當下由後端寫入且不可改寫（原則 II、資料完整性），匯出只做格式轉換，因此與老師端進度板、結果頁必然一致（FR-013）。
  同步區段內不 await，所以匯出是一致的快照：`submit_bundle` 在同一種同步區段內整組寫入，不會出現只匯出半個題組。
- **Alternatives**: 由 `ranking.build_board` 取資料——只含目前這一輪，缺少舊輪；另建匯出用的歷史表——產生第二份事實來源。

## D4：欄位與格式
- **Decision**: 欄位依序為 `輪次, 題號, 題組, 組別, 答案, 接收時間, 排名`。
  - 題號＝`Question.label`（如 `Q1`、`Q1（2）`），與老師端一致；
  - 題組＝所屬題組的成員題號以「、」相連（如 `Q3、Q4`），未綁定為空字串；
  - 接收時間＝`models.iso(submitted_at)`，即 `2026-11-11T03:04:05Z`（Clarification Q1：UTC，不提供當地時間欄）；
  - 排名＝`rank` 整數。
- **Rationale**: 題組欄用成員題號而非內部 id（`B1`），老師打開試算表就看得懂，且與老師端「題組：Q3、Q4」的呈現相同。
  既有 `iso()` 已是秒級 UTC 格式，無需新增時間格式。
- **Known limitation**: 試算表會把純數字答案（如 `007`）顯示為數字 `7`；CSV 檔內仍是原文，不為此增加複雜度。

## D5：中文與換行——UTF-8 加 BOM、CRLF
- **Decision**: 回應本文開頭加 `﻿`（UTF-8 BOM），以 `csv.writer(lineterminator="\r\n")` 產生，使用預設的最小引號策略
  （含逗號、雙引號、換行的欄位以雙引號包住，內含雙引號加倍）。
- **Rationale**: Excel 開啟沒有 BOM 的 UTF-8 CSV 會把中文顯示成亂碼（FR-016）；Google 試算表與 LibreOffice 也能正確讀取含 BOM 的檔案。
  CRLF 是 CSV 通用規則（RFC 4180），欄位內的換行仍原樣保留在引號內（FR-015）。
- **Alternatives**: 輸出 Big5——不能表示所有字元；輸出 `.xlsx`——需要新依賴，且需求明確要 CSV。

## D6：公式注入防護（FR-017）
- **Decision**: 對「組別」與「答案」兩個使用者提供的文字欄位套用 `safe_cell()`：
  若第一個字元是 `=`、`+`、`-`、`@`、Tab（`\t`）、CR（`\r`）或 LF（`\n`），在前面補一個單引號 `'`。其餘欄位為系統產生的固定格式，不需處理。
- **Rationale**: 這是 OWASP 對 CSV injection 的建議做法；補上單引號後試算表把該格視為文字，不會計算，且原文仍完整保留（去掉第一個字元 `'` 即還原），
  符合「以文字呈現、可還原」。副作用：以 `-` 開頭的負數答案（如 `-5`）會多一個 `'`，屬可接受代價。
- **Alternatives**: 刪除危險字元——會改寫答案，違反資料完整性；前綴 Tab——部分軟體會保留不可見字元造成比對困難。

## D7：檔名與下載
- **Decision**: 後端回 `Content-Disposition: attachment`，並同時給 ASCII 後備名 `records_<CODE>_<YYYYMMDD>.csv`（UTC 日期）與
  `filename*=UTF-8''<百分比編碼的 搶答紀錄_CODE_YYYYMMDD.csv>`；前端實際下載時以**本地日期**自行命名為 `搶答紀錄_<CODE>_<YYYYMMDD>.csv`。
- **Rationale**: 老師在台灣時，午夜至早上 8 點的 UTC 日期會比當地日期早一天，會造成歸檔困擾；前端本來就用 Blob 下載，由前端命名最準確。
  標頭保留是為了讓直接以工具（如 `curl -OJ`）取得時也有合理檔名。
- **Alternatives**: 只由後端命名——日期偏差；只由前端命名且後端不給標頭——非瀏覽器客戶端沒有檔名提示。

## D8：錯誤與空狀態
- **Decision**:
  - 憑證缺少或錯誤 → 沿用 `UNAUTHORIZED`（401）；
  - 房間已被清除 → 此端點內把 `ROOM_NOT_FOUND` 轉成 `RECORDS_GONE`（404，「紀錄已不存在，請於活動結束後盡快匯出」）；
  - 沒有任何有效送出 → `NO_RECORDS`（404，「尚無送出紀錄可匯出」），不回空檔；
  - 其他情況回 CSV。
- **Rationale**: FR-004、FR-021；用不同錯誤碼讓前端顯示精確的提示，且不下載空檔案。
- **Alternatives**: 回 `204` 或只有標題列的檔——前端要多分支，且老師可能誤以為匯出成功。

## D9：唯讀與快取
- **Decision**: 匯出不呼叫 `rooms.touch()`、不修改任何欄位；回應加 `Cache-Control: no-store`。
- **Rationale**: FR-022；答案屬於敏感內容，不應被瀏覽器或中介快取。房間仍開啟時老師的 WebSocket 已維持活動，不需靠匯出延長。

## D10：前端
- **Decision**: `exportRecords(code, token)`：`fetch` 帶標頭 → `!ok` 時解析 JSON 轉成 `ApiError`（沿用既有格式）→ 成功取 Blob，建立 `URL.createObjectURL`、
  暫時的 `<a download>` 觸發下載後立即 `revokeObjectURL`。老師端 `TeacherRoom` 新增常駐的「匯出紀錄」區塊，放在 `closed` 判斷之外，
  使搶答中、已結束、房間已結束都看得到；匯出中按鈕停用防止連點；401 沿用身分失效處理（`clearTeacherSession` + `revoked`）；
  `NO_RECORDS`、`RECORDS_GONE` 以既有 `error` 狀態顯示訊息。
- **Rationale**: FR-001、FR-005、FR-021、US3-2。學生端程式碼不修改，天然沒有匯出入口（FR-019）。
