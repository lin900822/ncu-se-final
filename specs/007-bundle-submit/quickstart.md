# Quickstart：題組打包提交驗證

## 前置條件與啟動
同 [Step 3](../003-sheet-question-form/quickstart.md)～[Step 6](../006-results-reveal-board/quickstart.md)：
`backend/.env` 設好機器人金鑰、試算表已共用給機器人；前後端啟動方式相同。

## 自動化測試
```bash
cd backend && uv run pytest
cd frontend && npx tsc -b      # 於 frontend/ 內 nvm use
```
預期通過：題組驗證（<2 題、不相鄰、重疊、不存在、無題目）、全有或全無、單題送題組成員被拒、同組兩視窗與兩組同時送出、
他組只收匿名提示、進度板與結果題組各題一致、領先題數以題數計、重連還原、新一輪清空。既有 Step 1～6 測試仍全數通過。

## 手動驗證情境

準備：老師貼單題範例（Q1～Q6）讀取預覽。

| # | 步驟 | 預期（對應規格） |
|---|------|------------------|
| 1 | 預覽中勾選 Q3、Q4，按「設為題組」 | 預覽顯示「題組：Q3、Q4」，其餘為單題（US1-1） |
| 2 | 只勾 Q2 設為題組；再勾 Q2、Q5 設為題組；再把 Q3 加入另一個題組 | 依序提示「至少 2 題」「只能相鄰」「一題只能屬於一個題組」，不建立題組（US1-4～6） |
| 3 | 按「重新讀取」 | 題組設定被清空（US1-7） |
| 4 | 重新設定 Q3+Q4，按「確認建立」 | 房間建立；老師端題目清單顯示題組；重新整理後不變（US1-2） |
| 5 | 「第 1 組」開兩個視窗、「第 2 組」開一個視窗加入 | Q3、Q4 在同一張卡片內，只有一顆送出鈕（US2-1、SC-002） |
| 6 | 開始搶答；第 1 組只填 Q3 | 送出鈕不可按並提示需填完（US2-2） |
| 7 | 第 1 組填完 Q3、Q4 後送出 | 整張卡片同時「已送出」；第二個視窗 2 秒內同步並顯示兩題答案（US2-4、US3-1、SC-004） |
| 8 | 檢視第 2 組畫面與 WebSocket 訊息 | 只看到「本題組已有組別送出」；找不到第 1 組組名與答案（US3-3、SC-007） |
| 9 | 第 2 組填完題組送出 | 老師進度板題組只有一份名次清單：第 1 組第 1、第 2 組第 2（US4-1、SC-006） |
| 10 | 看老師端各組領先題數 | 第 1 組計入 2 題（US4-5） |
| 11 | 結束搶答 | 結果頁 Q3、Q4 框在一起，顯示第 1 組與兩題答案；另一個無人送出的題組顯示「本題組無人搶答」（US4-3、US4-4） |
| 12 | 搶答中重新整理學生視窗、斷線重連 | 題組卡片與已送出狀態正確還原（US3-4、SC-008） |
| 13 | 開始新一輪 | 題組卡片清空可再作答，題組設定不變 |
| 14 | 以瀏覽器主控台送 `{"type":"submit","questionId":"3","answer":"x"}` | 回 `QUESTION_IN_BUNDLE`，不產生紀錄 |
| 15 | 以主控台送 `submit_bundle` 但 Q4 為空白 | 回 `BUNDLE_INCOMPLETE`（`details.questionIds:["4"]`），Q3 也沒有被記錄（US2-3、SC-003） |

契約見 [rest-api.md](./contracts/rest-api.md)、[websocket.md](./contracts/websocket.md)；資料見 [data-model.md](./data-model.md)。

## 實作後的圖表一致性檢查（Constitution VI）
比對 `diagrams/*.puml` 與程式（QuestionBundle、`services/bundles.py`、`submit_bundle` 全有或全無與共用名次、
`bundle_submitted`／`bundle_hint` 受眾）；不一致時修正程式或更新圖表，並重新產圖：
```bash
java -jar plantuml.jar -charset UTF-8 -tpng diagrams/*.puml
```
（本機若無 Graphviz，加 `-Playout=smetana`。）
