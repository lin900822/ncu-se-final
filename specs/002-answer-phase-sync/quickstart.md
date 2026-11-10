# Quickstart：階段同步驗證

## 前置條件與啟動
同 [Step 1 quickstart](../001-room-join/quickstart.md)（後端 `uv sync` 後以單一 worker 啟動；前端 `npm run dev`）。

## 自動化測試（原則 III 與鎖定閘門）
```bash
cd backend && uv run pytest
```
預期：階段轉換/冪等、非老師被拒、廣播僅含階段欄位、鎖定時 `submit` 被拒、重連快照階段正確，全數通過。

## 手動驗證情境

| # | 步驟 | 預期（對應規格） |
|---|------|------------------|
| 1 | A 建房；B、C 以「第 1 組」「第 2 組」加入 | B、C 皆顯示「等待搶答」，輸入框不可輸入（FR-002, SC-001） |
| 2 | B 嘗試點擊/輸入 | 無法輸入 |
| 3 | A 點「開始搶答」 | 2 秒內 B、C 輸入框解鎖；A 顯示「搶答中」，按鈕改為「結束搶答」（FR-003, FR-005, SC-002） |
| 4 | B 輸入一段文字，A 點「結束搶答」 | B、C 輸入框鎖定並顯示「搶答已結束」；B 的文字仍在、未被送出（FR-004, FR-010, SC-003） |
| 5 | A 再點「開始搶答」 | 全班解鎖，且輸入框為空白（Clarification Q2） |
| 6 | 搶答中重新整理 B | 重新加入後直接為解鎖（FR-008, SC-004） |
| 7 | 結束搶答前讓 C 斷網，A 結束後 C 恢復網路 | C 重連後為鎖定（Story 4 情境 2） |
| 8 | 搶答中新組別 D 才加入 | D 一進來即解鎖（Story 2 情境 3） |
| 9 | 房間無人在線時 A 點開始，之後 B 加入 | 允許開始；B 進來即解鎖（Clarification Q1） |
| 10 | 連點「開始搶答」多次 | 狀態不變、無重複事件（FR-009） |
| 11 | 用 curl 以學生/無憑證呼叫 `phase/start` | `401`（FR-006） |
| 12 | A 結束房間 | 學生顯示房間已結束、輸入維持鎖定（FR-013） |

契約見 [rest-api.md](./contracts/rest-api.md)、[websocket.md](./contracts/websocket.md)；資料見 [data-model.md](./data-model.md)。

## 實作後的圖表一致性檢查（Constitution VI）
比對 `diagrams/*.puml` 與程式碼（`phase`/`round`/`PhaseChange`、階段服務、開始/結束時序）；不一致時修正程式或更新圖表並重跑
`plantuml -tpng diagrams/*.puml`。
