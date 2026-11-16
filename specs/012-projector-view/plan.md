# Implementation Plan: 教室大螢幕投影專用視圖

**Branch**: `012-projector-view`（規格目錄；實際在目前分支開發） | **Date**: 2026-11-12 | **Spec**: [spec.md](./spec.md)

**Input**: Feature specification from `/specs/012-projector-view/spec.md`

## Summary

老師端取得一個**投影網址**（`/projector?code=…&key=…`），在教室電腦開啟後得到唯讀、放大、無控制按鈕的畫面，隨房間階段顯示：等待搶答（房間代碼與組別）→ 開始搶答時播放「3、2、1、開始！」動畫 → 搶答中的**匿名進度看板** → 結算後的**各題得主看板＋累計得分排行榜**。

核心設計：
1. **獨立的唯讀通道**：房間建立時多產生一把 `projector_key`（與老師憑證不同）；新增 `/ws/projector`，**只收不送**（忽略任何客戶端訊息），不計為組別、不更新房間活動時間。
2. **整份狀態推送**：後端以純函式 `projector.build_state(room)` 推導出「全班公開」的完整畫面資料，連線時送一次、之後每次相關事件（階段變更、送出、審核、組別加入、房間結束）重送整份；畫面是無狀態的，斷線重連與重新整理自然還原（憲章「即時同步與斷線還原」）。
3. **保密由後端決定**（憲章 III）：搶答中 `build_state` 只輸出各題「已有／尚無組別送出」與總進度，**根本不含**組名（除組別名單）、答案、名次、時間、讓位／保留；結算後的得主看板直接重用學生端的 `results.build_result()`，因此與學生、老師看到的結果逐題一致。
4. **得分排行榜**：把每個**已結算**輪次的 `effective.allocate(room, n).wins` 累計；同分名次並列。完全是推導資料，不新增儲存、不改動任何紀錄。
5. **倒數動畫**：`start_answering` 在推送新狀態後，對投影連線多送一個一次性 `countdown` 事件；前端收到才播放（約 3 秒、尊重「減少動態效果」），晚連線者不補播；學生端開放時間與階段規則完全不變。

不新增依賴、不新增儲存；沿用 FastAPI 記憶體房間與 React/Vite。

## Technical Context

**Language/Version**: 後端 Python 3.12（uv）；前端 TypeScript、Node.js 22 LTS（沿用）

**Primary Dependencies**: 沿用 FastAPI、React 19、Vite、Tailwind v4；**不新增依賴**（動畫用 CSS keyframes）

**Storage**: 沿用僅記憶體。`Room` 新增 `projector_key: str`（建立時以既有的權杖產生器產生、固定）；投影內容與得分皆為推導資料，不另存；`Submission`、`ReviewRecord` 等紀錄**不修改**

**Testing**: pytest（TestClient WebSocket）。重點：
(1) **憑證**：`/ws/projector` 以正確的 `code`＋`key` 連線即收到 `projector_state`；錯誤 key、老師憑證、恢復碼、不存在的房間一律回 `projector_unavailable` 並關閉（訊息相同、不洩漏房間是否存在）；以投影連線送任何訊息（`submit`、`start`…）都被忽略、房間狀態不變；投影憑證打 REST 老師端點（開始／結束／審核／回填／匯出／關房）全部 401；
(2) **網址不含老師憑證**：`projector_key` ≠ `teacher_token` ≠ `recovery_code`；老師端 `snapshot.room.projectorKey` 與建立回應一致，換裝置恢復後相同；學生 `joined`、學生任何訊息不含 `projectorKey`；
(3) **不計為組別**：開啟多個投影連線後，老師 `snapshot.groups`、`count`、組別清單、學生加入同名組別、在線／離線狀態均不受影響；投影連線不更新 `last_activity_at`；
(4) **保密（關鍵）**：搶答中投影收到的**所有**訊息序列化後不含任何送出組別的組名與答案、`rank`、`seq`、`submittedAt`、`outcome`、`Yielded`、`Kept`、`Behind`、`leader`；只含各單位 `submitted: true/false` 與 `{answered,total}`；多組多題（含題組）送出後逐則斷言；排行榜組名只可能是房間組別名單（與送出無關）；
(5) **階段內容**：Waiting＝代碼＋組別名單；Answering＝匿名進度；Ended＝`result`（與 `build_result` 完全相等，含題組並列、無人搶答、全被駁回 `noValid`）＋排行榜；Closed＝保留最後內容且 `status:"Closed"`；無題目房間只有代碼與組別；
(6) **即時更新**：送出→投影在同一回應週期收到更新的 `projector_state`（該單位 `submitted:true`，進度＋1）；審核駁回／恢復→得主與排行榜重新推導；Step 11 讓位後的結果與得分一致；新組別加入→名單更新；結束房間→`status:"Closed"`；
(7) **倒數事件**：`start_answering` 對每個已連線投影送一次 `countdown`（`round` 為新輪次），之後才是 Answering 的 `projector_state`（或先後順序固定且寫入契約）；**重連／晚連線不收到** `countdown`；重複按開始（冪等）不重送；學生端與老師端的 `phase_changed`／輸入開放時序與 Step 10 完全相同（既有測試不修改）；
(8) **得分**：多輪累計（第 1 輪第 1 組 3 題、第 2 輪第 1 組 1 題 → 4）；進行中的新一輪不計入；題組 N 題計 N；Step 11 的「保留」計入；被駁回後重新分配得分隨之改變；同分名次並列（1、1、3）且以組名排序穩定；0 分組別列出；跨輪各自以該輪的審核與公平規則推導；
(9) **確定性與唯讀**：相同紀錄重複 `build_state` 100 次結果相等；呼叫前後逐欄比對 `Room`（submissions、reviews、phase_log、groups）完全不變；
(10) **一致性**：同一時刻投影的得主看板＝學生 `round_result`＝老師 `snapshot.result`（逐題相等）；
(11) **規模**：30 題 × 20 組 × 3 輪，單次 `build_state` < 200 ms；20 個投影連線的廣播於 1 秒內送達；
(12) 既有 340 個測試**不需修改**即全數通過。

前端以 `npx tsc -b`、`npm run build`、`npm run lint`（警告數不得多於修改前）驗證；畫面流程以示範後端（仿 Step 10／11：記憶體假試算表）在瀏覽器走過 `quickstart.md`。

**Target Platform**: 本機／單機、單一 worker；投影畫面針對 16:9、1920×1080 最佳化，其他比例不破版

**Project Type**: web-service（FastAPI 後端 + React SPA 前端）

**Performance Goals**: 事件發生後 3 秒內投影更新（沿用即時通道，實際為毫秒級）；`build_state` 為 O(送出數＋輪次×分配) 的記憶體內推導

**Constraints**: 單一 worker；投影通道唯讀、不接受任何寫入；搶答中投影資料由後端過濾而非前端隱藏；不更動任何仲裁、審核、公平分配、回填、匯出；倒數僅為視覺事件；投影憑證不提供作廢／重發；不做音效、輪播、主題、排行榜圖片匯出

**Scale/Scope**: 後端新增 `services/projector.py`、`Room.projector_key`、`Realtime` 的投影連線登記與廣播、`/ws/projector` 端點，並在既有的 5 個事件點呼叫 `projector.publish(room)`；前端新增 `/projector` 頁與少量展示元件，並在老師頁加入「開啟投影視圖」按鈕

## Constitution Check

*GATE: Must pass before Phase 0 research. Re-check after Phase 1 design.*

| 原則 / 約束 | 本階段判定 | 說明 |
|-------------|-----------|------|
| I 組別為唯一單位 | ✅ 通過 | 得分與排行榜以組別為單位；投影連線不是組別、不影響組別清單 |
| II 後端依送出時間仲裁 | ✅ 通過 | 不新增任何仲裁；倒數只是視覺事件，不延後學生端開放、不改變名次；得主一律由既有的有效結果推導，原始紀錄不改 |
| III 作答保密 | ✅ 通過（關鍵） | 大螢幕等同全班可見：搶答中**只輸出匿名進度**（已有／尚無組別送出），後端直接不產生組名與答案；結算後只公開各題得主組名＋答案與累計題數（與學生結果頁同一份資料）；被駁回者、理由、名次、時間、讓位細節不出現；以自動化測試逐則斷言 |
| IV 防壟斷與仲裁 | ✅ 通過 | 看板與得分採 Step 9／11 的有效結果（含審核與讓位）；規則與仲裁不變 |
| V 回填與歷程 | ✅ 通過 | 不改動回填與匯出；投影純讀取 |
| VI PlantUML 設計優先 | ✅ 通過 | `diagrams/` 已於 specify 階段加入 `ProjectorView`／`GroupScore`、投影服務元件與開啟投影的時序，並已產 PNG；實作後依 quickstart 再驗證 |
| 即時同步與斷線還原 | ✅ 通過 | 整份狀態推送：連線即還原、重連自動一致；不依賴本機暫存 |
| 資料完整性（append-only） | ✅ 通過 | 無新增可覆寫資料；投影唯讀 |
| 時間來源 | ✅ 通過 | 不使用任何客戶端時間作為判定依據；倒數僅顯示 |
| 隱私 | ✅ 通過 | 只顯示組別名稱與已公開的答案；不新增個資 |
| 測試要求 | ✅ 通過 | 覆蓋 III（搶答中零洩漏）、憑證與唯讀、一致性、得分推導與確定性 |
| 簡潔性 | ✅ 通過 | 無新依賴、無新儲存；一個新服務＋一個唯讀通道，重用 `results`／`effective` |

**Post-Phase 1 重新檢查**：設計後仍全部通過，無需填寫 Complexity Tracking。

## Project Structure

### Documentation (this feature)

```text
specs/012-projector-view/
├── plan.md
├── research.md
├── data-model.md
├── quickstart.md
├── contracts/
│   ├── rest-api.md
│   └── websocket.md
├── checklists/requirements.md
└── tasks.md             # 由 /speckit-tasks 產生
```

### Source Code (repository root)

```text
diagrams/                          # 已更新：ProjectorView/GroupScore、投影服務元件、開啟投影視圖時序

backend/app/
├── models.py                      # 修改：Room.projector_key
├── realtime.py                    # 修改：projectors 登記、add/remove_projector、broadcast_to_projectors；close_room_connections 對投影送最終狀態
├── services/
│   ├── projector.py               # 新增：build_state(room)、scoreboard(room)、publish(room)、announce_countdown(room)
│   ├── rooms.py                   # 修改：create_room 產生 projector_key；snapshot 加 projectorKey；close_room 推送 Closed 狀態
│   ├── phase.py                   # 修改：階段變更後 publish；開始搶答後送 countdown
│   ├── groups.py                  # 修改：新組別加入後 publish（名單更新）
│   └── review.py                  # 修改：publish_review 後 publish
└── api/
    ├── rooms.py                   # 修改：建立回應加 projectorKey
    └── ws.py                      # 修改：新增 /ws/projector（唯讀）；兩個 submit 路徑送出後 publish

backend/tests/
├── test_projector_access.py       # 新增：憑證、唯讀、不計為組別、錯誤一致
├── test_projector_privacy.py      # 新增：搶答中零洩漏（含題組、多組）、結算後只公開得主與得分
├── test_projector_state.py        # 新增：各階段內容、即時更新、Closed、無題目房間、與學生／老師結果一致
├── test_projector_score.py        # 新增：多輪累計、題組、保留、審核連動、並列、確定性、唯讀、規模
└── test_projector_countdown.py    # 新增：countdown 只發一次、晚連線不補播、不影響階段時序

frontend/src/
├── App.tsx                        # 修改：新增 /projector 路由
├── lib/api.ts                     # 修改：createRoom 回應加 projectorKey；ProjectorState 型別
├── pages/Projector.tsx            # 新增：唯讀投影頁（連線、階段切換、斷線提示、無法顯示）
├── components/projector/
│   ├── Countdown.tsx              # 新增：3、2、1、開始！動畫（尊重 prefers-reduced-motion）
│   ├── ProgressBoard.tsx          # 新增：搶答中匿名進度看板
│   ├── WinnersBoard.tsx           # 新增：結算後各題得主看板（題組一格）
│   └── Scoreboard.tsx             # 新增：累計得分排行榜（並列名次）
├── index.css                      # 修改：倒數 keyframes 與減少動態效果的覆寫
└── pages/TeacherRoom.tsx          # 修改：保存 projectorKey、「開啟投影視圖」（新分頁）與「複製投影網址」
```

**Structure Decision**: 沿用前後端分離。圖中「投影服務」對應 `services/projector.py`，「投影視圖」對應 `/projector` 頁；投影通道與老師／學生通道分開，**唯讀、只推送**，確保投影憑證即使外流也不能做任何事。

## Complexity Tracking

無違反項目，不需填寫。
