# Data Model: 公平機制：獲勝上限與冷卻限制

僅列相對 Step 1～10 的新增與修改。所有資料仍僅存記憶體；時間一律為後端產生的 UTC。
**不修改** `Submission`、`ReviewRecord`、`Question`、`SheetSource`、`BackfillRecord`；分配結果完全由它們與公平規則推導，不另存。

## FairnessRule（新增，屬於 Room，建立後固定）

| 欄位 | 型別 | 規則 |
|------|------|------|
| `win_cap` | int \| None | 每組在**一輪**中最多搶得幾題；`None`＝不限制；設定時必須是 `1 <= win_cap <= 題目數` 的整數 |
| `cooldown_seconds` | int | 組別每次取得題目後的冷卻秒數；`0`＝不套用；必須是 `0..600` 的整數 |

- 預設 `FairnessRule(win_cap=None, cooldown_seconds=0)`（不限制）；建立後**不可修改**。
- 沒有題目（未綁定試算表）的房間只能是預設值；帶規則建立 → `FAIRNESS_INVALID`。
- **對外格式** `fairness_public(f)`：`null`（預設、不限制）或 `{"winCap": 2 | null, "cooldownSeconds": 30}`；不含任何作答內容，可給所有學生。

## Room（修改）

| 新增欄位 | 型別 | 說明 |
|----------|------|------|
| `fairness` | FairnessRule | 預設不限制；建立房間時確定 |

## Allocation（推導，不另存）

`effective.allocate(room, round_no) -> Allocation`（純函式、唯讀）：

| 欄位 | 型別 | 說明 |
|------|------|------|
| `winners` | dict[unit_id, Submission \| None] | 每個「有有效申請」的單位的獲勝送出；沒有任何有效申請（含全被駁回）為 `None`；沒有送出的單位不在字典中 |
| `status` | dict[(unit_id, normalized_name), Outcome] | 每個 (單位, 組別) 申請的狀態 |
| `wins` | dict[normalized_name, int] | 各組取得題數（含 `Kept`；題組計成員數） |

### Outcome（每筆申請的狀態）

| 值 | 意義 | 是否獲勝 | CSV「未獲勝原因」 |
|----|------|----------|-------------------|
| `Won` | 符合資格且為該單位最先符合資格者 | 是 | （空） |
| `Kept` | 全員不符資格時由原始名次最前者保留 | 是 | （空） |
| `Behind` | 該單位已由其他組取得，這筆名次落後 | 否 | 名次落後 |
| `Invalid` | 被老師駁回（Step 9） | 否 | 被駁回 |
| `YieldedCap` | 取得前該組題數已達上限，讓位 | 否 | 已達上限 |
| `YieldedCooldown` | 距離該組上一次取得未達冷卻秒數，讓位 | 否 | 冷卻中 |

### 分配規則（演算法，見 research D1～D5）
1. 申請＝本輪未被駁回的 `unit_entries`（每組每單位一筆）；被駁回者 `status = Invalid`。
2. 全部申請依 `Submission.seq` 由小到大逐筆判定：
   - 單位已有獲勝者 → `Behind`；
   - 否則：`win_cap` 非空且 `wins[組] >= win_cap` → `YieldedCap`；否則 `cooldown_seconds > 0` 且該組有上一次取得時間 `last_win` 且 `submitted_at - last_win < cooldown` → `YieldedCooldown`；
   - 皆符合 → `Won`：`winners[單位]` 設為該筆、`wins[組] += 單位題數`、`last_win[組] = submitted_at`。
3. 主判定後，仍無獲勝者但有有效申請的單位：原始名次最前的申請改為 `Kept` 並成為獲勝者，`wins[組] += 單位題數`。
4. 單位題數＝題組成員數（單題為 1）；每輪獨立計算。

### 不變式
- 每個有有效申請的單位**恰有一個**獲勝者；全部被駁回的單位獲勝者為 `None`。
- 沒有規則（`win_cap is None` 且 `cooldown_seconds == 0`）時，獲勝者與 Step 9 的 `effective_winners` 完全相同，且不會出現 `Yielded*`／`Kept`。
- 在存在符合資格的其他申請者可遞補時，任一組的 `Won` 單位在取得前的題數都 `< win_cap`（題組導致的最後一次略超過、與 `Kept` 除外）。
- 確定性：相同的 `submissions`、`reviews`、`fairness`，任何時間呼叫結果完全相同。
- `Submission` 的答案、`submitted_at`、`seq`、`rank` 在分配前後完全相同。

## 對既有資料的影響

| 位置 | 變更 |
|------|------|
| `effective.effective_winners` | 改回傳 `allocation.winners`（簽章不變） |
| `effective.succession_ranks` | **不變**（仍是排除被駁回者後的名次） |
| `results.build_result` | 不變（呼叫 `effective_winners`）；`noValid` 判斷不變 |
| `ranking.build_board` | 每筆 `ranking[]` 新增 `outcome`；頂層新增 `fairness`；`leader`／`leadTally` 自動為讓位後結果 |
| `export.build_rows` | 追加 `獲勝狀態`、`未獲勝原因` 兩欄（共 13 欄） |
| `snapshot.room` / `joined` / 建立回應 | 新增 `fairness` |

## 新增錯誤碼

| code | HTTP | 訊息 | 觸發 |
|------|------|------|------|
| `FAIRNESS_INVALID` | 400 | 公平規則設定有誤 | 建立房間時規則不合法；`details.reason`：`NO_QUESTIONS`、`WIN_CAP_RANGE`、`COOLDOWN_RANGE`、`TYPE` |
