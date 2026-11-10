# Quickstart：手動驗證（無自動化測試）

## 前置條件
- nvm、Node 22 LTS：`nvm install 22 && nvm use 22`（於 `frontend/` 內可用 `nvm use` 讀取 `.nvmrc`）
- uv（Python 3.12 由 uv 自動取得）

## 啟動
```bash
# 終端機 1：後端（單一 worker）
cd backend && uv sync && uv run uvicorn app.main:app --reload --port 8000 \
  --ws-ping-interval 10 --ws-ping-timeout 10

# 終端機 2：前端
cd frontend && nvm use && npm install && npm run dev   # http://localhost:5173
```

## 驗證情境

| # | 步驟 | 預期（對應規格） |
|---|------|------------------|
| 1 | 瀏覽器 A 開首頁 → 建立房間 | 10 秒內看到房間代碼、恢復碼與空清單（FR-001, SC-001） |
| 2 | 瀏覽器 B 輸入代碼與組名「第 1 組」 | 進入等待畫面；A 於 2 秒內出現「第 1 組」，數量 1（FR-006, SC-003） |
| 3 | 瀏覽器 C 加入「第 2 組」 | A 清單共 2 組，各一次；B/C 畫面看不到對方（FR-009） |
| 4 | 瀏覽器 D 以「第１組」（全形）加入 | 顯示「該組目前在線」，清單不變（FR-005） |
| 5 | 關閉 B 分頁，觀察 A | 「第 1 組」仍在清單並標示離線（FR-007） |
| 6 | 新分頁再以「第 1 組」加入 | 回到同一組，A 無重複項、狀態回在線（Story 4） |
| 7 | 重新整理 B | 自動重新加入（可能短暫重試）；A 無重複（SC-005） |
| 8 | 輸入錯誤代碼 / 空白組名 | 顯示「找不到該房間」/「請填寫組名」 |
| 9 | 重新整理 A；另開無痕視窗用恢復碼回復 | 清單完整還原；舊視窗被登出（FR-008, FR-012） |
| 10 | A 按「結束房間」後學生再加入 | 顯示「該房間已結束」（FR-011） |
| 11 | （可選）以 `ROOM_IDLE_SECONDS=30 ROOM_SCAN_SECONDS=5` 啟動後端，開房後關閉所有分頁 | 房間自動結束（FR-013） |

契約細節見 [contracts/rest-api.md](./contracts/rest-api.md) 與 [contracts/websocket.md](./contracts/websocket.md)；
資料欄位見 [data-model.md](./data-model.md)。

## 實作後的圖表一致性檢查（Constitution VI）
實作完成後比對 `diagrams/*.puml` 與程式碼；不一致時修正程式或更新圖表並重跑
`plantuml -tpng diagrams/*.puml`。
