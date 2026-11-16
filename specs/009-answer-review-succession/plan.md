# Implementation Plan: 老師端人工審核與順位遞補

**Branch**: `009-answer-review-succession`（規格目錄；實際在目前分支開發） | **Date**: 2026-11-11 | **Spec**: [spec.md](./spec.md)

**Input**: Feature specification from `/specs/009-answer-review-succession/spec.md`

## Summary

老師在搶答**結束後**於結果面板對任一筆送出按「駁回/無效」（填理由、按「確認駁回」即生效）。後端在同一個無 await 區段內：
驗證老師憑證與時機 → 追加一筆**審核紀錄**（僅追加）→ 重新推導各搶答單位的**有效第一名**（原始名次最前且未被駁回者）→ 廣播。
**原始答案、送出時間、原始名次完全不動**；有效狀態、遞補後名次、有效結果全部由「原始名次＋審核紀錄」即時推導，不另存。

新增 `POST /api/rooms/{code}/reviews`（老師憑證，Bearer 標頭）。審核成功後：
- 老師收到 `review_updated`（看板含每筆狀態／遞補後名次／理由、審核紀錄清單、有效結果）；
- 全體學生收到更新後的 `round_result`（沿用 Step 6 的專用公布通道，只含有效第一名的組名＋答案，加 `reviewed: true` 讓學生端顯示「老師已更新結果」）。

因為 `joined.result` 與老師 `snapshot` 本來就由 `build_result`／`build_board` 推導，所以重連、晚加入、換裝置自動取得審核後的結果（FR-015）。
`build_result` 改為取「有效第一名」，Step 5 看板的 `leader`／`leadTally` 同樣改取有效第一名（FR-011、FR-016）。
Step 8 的 CSV 在原七欄之後追加四欄（審核狀態、遞補後名次、審核理由、審核時間）。學生端在等待階段顯示規則說明（FR-022）。
沿用 FastAPI + 記憶體儲存 + React/Vite，**不新增依賴**。

## Technical Context

**Language/Version**: 後端 Python 3.12（uv）；前端 TypeScript、Node.js 22 LTS（沿用）

**Primary Dependencies**: 沿用 FastAPI、Pydantic、React 19、Vite、Tailwind v4；**不新增依賴**

**Storage**: 沿用僅記憶體。`Room` 新增 `reviews: list[ReviewRecord]`（僅追加）；`Submission` **不修改**；有效狀態、遞補後名次、有效結果皆為推導資料，不另存

**Testing**: pytest。重點：
(1) 遞補：第 1、2、3 組依序送出 Q1，駁回第 1 組 → Q1 結果為第 2 組；再駁回第 2 組 → 第 3 組；三組皆駁回 → `winnerGroup/answer` 為 `null`；駁回第 2 名不影響第一名，之後駁回第 1 名會略過第 2 名由第 3 名遞補；恢復後回到原始名次最前者；
(2) 性質測試：至少 100 組隨機（駁回／恢復）序列後，每個搶答單位的第一名都等於「原始名次最前且目前有效者」，遞補後名次為排除無效者後的連續名次（SC-003）；
(3) 題組：駁回題組整組生效，題組內各題的有效狀態永遠相同、結果同一個搶下組別；
(4) 驗證與時機：理由為空／全空白 → `REASON_REQUIRED`，超過 100 字元 → `REASON_TOO_LONG`；Waiting／Answering 階段、`round` 不是最新一輪、房間已結束 → 拒絕且 `reviews` 不增加；單位或組別不存在、該組在該單位沒有送出 → 拒絕；
(5) 權限：無憑證、錯誤憑證、換裝置後的舊憑證、憑證放網址 → 401 且不改變任何結果；學生 WebSocket 傳 `review` 類訊息被忽略；
(6) 冪等：同一筆連續駁回、兩個視窗同時駁回（重複 100 次）→ 審核紀錄恰 1 筆、只遞補一名（SC-009）；對有效者「恢復」、對已駁回者「駁回」皆視為重複（`changed: false`，不新增紀錄）；
(7) 同步：駁回後所有學生視窗（含同組多視窗、被駁回組、遞補組、他組）收到 `round_result`（`reviewed: true`），第一名更新；被駁回組別的組名、答案、理由在學生端收到的所有訊息與重連 `joined` 中出現次數為 0（SC-004）；遞補組標示「本組搶下」所需資料正確；
(8) 還原：審核後重新加入／晚加入的學生 `joined.result` 與廣播內容完全相同；老師以恢復碼回復後 `snapshot` 含完整 `reviews` 與看板狀態；
(9) 原始資料不變：審核前後 `room.submissions` 逐筆（答案、`submitted_at`、`seq`、`rank`）完全相同；`reviews` 只增不減、時間為後端 UTC、含操作者／組別／單位／動作／理由；
(10) 看板：`leader`、`leadTally` 取有效第一名（N 題題組計 N 題）；每筆名次帶 `status`、`successionRank`、`reason`；與學生結果各題一致；
(11) 匯出：CSV 追加四欄；有效列遞補後名次一律有值、無效列為空；未審核列理由與時間為空；恢復者為有效且帶恢復的理由與時間；理由套用公式防護；原有七欄不變；
(12) 靜態審核：`broadcast_result(` 只出現在 `phase.py` 與 `review.py`；`review` 服務不被學生 WebSocket 路徑引用；`ranking.build_board` 仍不出現在任何學生廣播呼叫附近

**Target Platform**: 本機/單機、單一 worker；現代桌面與手機瀏覽器

**Performance Goals**: 駁回後 2 秒內老師與全班學生結果一致（SC-002）；≤ 40 組、每組 ≤ 10 視窗、≤ 50 題，單次審核推導為 O(送出數)、記憶體內完成並扇出

**Constraints**: 單一 worker、asyncio 單執行緒——審核寫入與重複判斷靠「同步區段內不 await」保證；僅 Ended 階段、最新一輪、房間 Open、老師憑證；理由必填 ≤ 100 字元；不改動任何原始送出；學生端只能收到有效第一名；本步驟不做防壟斷上限、重開題目、指定獲勝組別、回填

**Scale/Scope**: 後端新增 `services/review.py`、一個端點、一則老師事件、`round_result` 多一個旗標、六個錯誤碼，並修改 `results`／`ranking`／`export`／`rooms.snapshot`；前端新增理由輸入元件與審核紀錄區塊，修改看板、結果頁與學生頁

## Constitution Check

*GATE: Must pass before Phase 0 research. Re-check after Phase 1 design.*

| 原則 / 約束 | 本階段判定 | 說明 |
|-------------|-----------|------|
| I 組別為唯一單位；題目僅以題號管理 | ✅ 通過 | 審核對象是「組別在搶答單位的送出」，不涉及個別學生；搶答單位沿用 Step 7 的題組設定，不新增題型或階層 |
| II 後端依送出時間仲裁 | ✅ 通過（關鍵） | 原始名次與時間、答案**永不改寫**（無任何欄位被修改）；遞補後名次只是由原始名次推導，客戶端時間不參與；審核寫入在同一同步區段內，重複動作有唯一結果 |
| III 作答保密 | ✅ 通過（關鍵） | 學生端只透過既有專用通道收到「有效第一名組名＋答案」，被駁回者的組名／答案／理由／審核紀錄／遞補後名次只出現在老師路徑；有學生訊息掃描測試與靜態審核 |
| IV 防壟斷與仲裁 | ⚠️ 部分達成（符合本步驟範圍，非違反） | 實作「教師仲裁：判定答案不合格」，每次記錄操作者、時間、理由，並在活動開始前向學生公開規則（FR-022）。**防壟斷上限、重開題目、指定獲勝組別尚未實作**（FR-023），憲章 IV 需待後續步驟才完整落實；本步驟的有效結果推導可作為其基礎 |
| V 回填與歷程 | ✅ 通過 | 審核紀錄可被匯出核對（CSV 追加欄位）；原始送出不變，回填日後可直接取有效第一名 |
| VI PlantUML 設計優先 | ✅ 通過 | `diagrams/` 已於 specify 階段加入 `ReviewRecord`／`EffectiveResult`、審核服務與審核時序並已產 PNG；實作後須再比對一次（見 quickstart） |
| 即時同步與斷線還原 | ✅ 通過 | 結果由後端推導，`joined`／`snapshot` 還原審核後狀態，不依賴客戶端 |
| 資料完整性（append-only） | ✅ 通過 | 審核紀錄僅追加；恢復也是新增一筆，不覆寫、不刪除 |
| 時間來源 | ✅ 通過 | 審核時間由後端 UTC 產生 |
| 隱私 | ✅ 通過 | 審核紀錄不含學生個資；理由僅老師可見 |
| 測試要求 | ✅ 通過 | 覆蓋 II（原始資料不變、併發重複）、III（被駁回者不外洩）、IV（審核與稽核）、V（匯出核對） |
| 簡潔性 | ✅ 通過 | 無新依賴、無新儲存表；有效結果為推導；單一 `services/review.py` |

**Post-Phase 1 重新檢查**：設計後仍全部通過；唯一「部分達成」為憲章 IV 的防壟斷等項目，屬已明列的範圍外（FR-023），無需填寫 Complexity Tracking。

## Project Structure

### Documentation (this feature)

```text
specs/009-answer-review-succession/
├── plan.md
├── research.md
├── data-model.md
├── quickstart.md
├── contracts/
│   ├── rest-api.md
│   ├── websocket.md
│   └── csv-format.md
├── checklists/requirements.md
└── tasks.md             # 由 /speckit-tasks 產生
```

### Source Code (repository root)

```text
diagrams/                          # 已更新：ReviewRecord／EffectiveResult、審核服務、審核時序

backend/app/
├── models.py                      # 修改：ReviewRecord、Room.reviews；錯誤碼 REVIEW_NOT_ALLOWED／REASON_REQUIRED／
│                                  #       REASON_TOO_LONG／UNIT_NOT_FOUND／REVIEW_TARGET_NOT_FOUND
├── services/
│   ├── effective.py               # 新增：純推導（只匯入 models、bundles）：review_state()／invalid_keys()／unit_entries()／
│   │                              #       effective_winners()／succession_ranks()／review_public()；避免 results↔review 循環匯入
│   ├── review.py                  # 新增：apply_review()（同步驗證＋追加）、publish_review()（async 廣播）
│   ├── results.py                 # 修改：build_result 改取有效第一名；有送出但全被駁回時該題附 noValid: true
│   ├── ranking.py                 # 修改：看板每筆加 status／successionRank／reason／answer；leader／leadTally 取有效第一名
│   ├── export.py                  # 修改：追加四欄（審核狀態、遞補後名次、審核理由、審核時間）
│   └── rooms.py                   # 修改：snapshot 加 reviews
└── api/rooms.py                   # 修改：POST /api/rooms/{code}/reviews

backend/tests/
├── test_review.py                 # 新增：遞補、連續駁回、全部駁回、恢復、題組、驗證與時機、冪等、原始資料不變
├── test_review_property.py         # 新增：隨機駁回／恢復序列的性質測試（100 組）、重複併發
├── test_review_sync.py            # 新增：學生／老師同步、重連還原、被駁回者不外洩（原則 III）、權限
├── test_review_export.py          # 新增：CSV 追加欄位
└── （修改）test_export*.py、test_results_privacy.py   # 更新七欄→十一欄與 broadcast_result 允許清單

frontend/src/
├── lib/api.ts                     # 修改：reviewSubmission()；describeError 補審核錯誤
├── components/ReviewForm.tsx      # 新增：理由輸入（常用理由快速選取＋自行輸入≤100字）與「確認駁回」
├── components/RankingBoard.tsx    # 修改：每筆顯示狀態／遞補後名次／理由，Ended 階段顯示「駁回/無效」「恢復有效」
├── components/ResultBoard.tsx     # 修改：無有效答案時顯示「本題（題組）無有效答案」；顯示「老師已更新結果」提示
├── pages/TeacherRoom.tsx          # 修改：處理 review_updated、顯示審核紀錄區塊、串接審核操作
└── pages/StudentJoin.tsx          # 修改：處理 round_result.reviewed 提示；等待階段顯示規則說明
```

**Structure Decision**: 沿用前後端分離。圖中「審核服務」對應 `services/review.py`；有效結果由 `results.py` 與 `ranking.py` 呼叫
`effective.effective_winners()` 推導。審核動作用 REST（與開始／結束搶答一致），廣播沿用既有通道，不新增學生訊息型別。

## Complexity Tracking

無違反項目，不需填寫。
