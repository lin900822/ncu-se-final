# Quickstart：題目表單生成驗證

## 一次性設定（Google 端與 `.env`）

1. 確認 Google Cloud 專案已**啟用 Google Sheets API**。
2. 把服務帳號 JSON 金鑰檔放在專案外或不入版控的位置（例如 `~/secrets/ncu-bot.json`）。**不要提交到 git**。
3. 建立 `backend/.env`（可複製 `backend/.env.example`）：
   ```
   GOOGLE_SERVICE_ACCOUNT_FILE=/絕對路徑/ncu-bot.json
   ```
4. 打開金鑰檔，複製 `client_email`；到要使用的 Google Sheet →「共用」→ 加入該 email（目前檢視者即可；到回填步驟需改為**編輯者**）。
5. 把範例學習單（單題、題組）各上傳為 Google Sheet 並共用給機器人。

## 啟動
同 [Step 1 quickstart](../001-room-join/quickstart.md)（後端單一 worker；前端 `npm run dev`）。啟動後端時不應在日誌看到金鑰內容。

## 自動化測試
```bash
cd backend && uv run pytest
```
預期：解析器（兩份範例檔與錯誤格式）、Sheets 用戶端錯誤對應、題目 API、憑證不外洩全數通過（不需要真實 Google 連線）。

## 手動驗證情境

| # | 步驟 | 預期（對應規格） |
|---|------|------------------|
| 1 | 首頁貼上**單題**範例連結 → 讀取題目 | 10 秒內預覽 Q1～Q6 共 6 題，尚未建立房間（SC-001、FR-004、SC-003） |
| 2 | 按「確認建立」 | 房間建立；老師端顯示同一份題號清單（US1、US3） |
| 3 | 學生加入（老師尚未開始搶答） | 2 秒內看到 Q1～Q6 六個填空格，順序與題號一致，**看不到題目文字**，輸入框鎖定（SC-002、FR-006、FR-014） |
| 3b | 老師按「開始搶答」 | 2 秒內各題號下出現題目文字且輸入框解鎖；按「結束搶答」後題目文字隱藏；搶答中重新整理學生頁面立即看到題目文字；結束後重新整理看不到（SC-007） |
| 4 | 老師按「開始搶答」，學生在 Q3 輸入文字 | 只有 Q3 改變，其他格不受影響（SC-004、FR-007） |
| 5 | 重新整理學生頁面 | 同一輪內文字還原；老師結束再開始搶答後各格清空（FR-013、SC-006） |
| 6 | 改貼**題組**範例連結重新讀取 | 預覽 Q1（1）、Q1（2）、Q2（1）、Q2（2）、Q3、Q4，學生端依題號分組顯示 |
| 7 | 貼非 Google Sheet 網址 | 顯示「請貼上有效的 Google Sheet 連結」，未建立房間 |
| 8 | 貼未共用給機器人的試算表 | 顯示請共用給機器人，並列出機器人 email |
| 9 | 把測試表的題號改成 1、2、2、4 | 拒絕並列出重複的 2 與缺漏的 3 |
| 10 | 預覽後、確認前，在試算表加一題再按確認建立 | 回「試算表內容已變動，請重新讀取」，未建立房間 |
| 11 | 不貼連結直接建立房間 | 可建立；學生端不顯示填空格 |
| 12 | 移除 `.env` 的路徑後重啟後端，再貼連結 | 回「伺服器尚未設定 Google 機器人」；不貼連結仍可建房 |
| 13 | 瀏覽器開發者工具檢查 `joined`／API 回應／後端日誌 | 沒有金鑰、private key、儲存格位置 |

契約見 [rest-api.md](./contracts/rest-api.md)、[websocket.md](./contracts/websocket.md)；資料見 [data-model.md](./data-model.md)。

## 實作後的圖表一致性檢查（Constitution VI）
比對 `diagrams/*.puml` 與程式（Question、SheetSource、學習單服務、預覽/確認與指紋流程、憑證設定）；
不一致時修正程式或更新圖表並重跑 `plantuml -tpng diagrams/*.puml`。
