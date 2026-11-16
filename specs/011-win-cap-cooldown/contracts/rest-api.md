# REST Contract（Step 11 修改）

公平規則只經建立房間設定；**沒有任何修改規則的端點**（規則於房間存續期間固定）。

## `POST /api/rooms`（建立房間）

### Request（新增選填 `fairness`）
```json
{
  "sheetUrl": "https://docs.google.com/spreadsheets/d/…",
  "fingerprint": "sha256 hex",
  "bundles": [["3", "4"]],
  "fairness": { "winCap": 2, "cooldownSeconds": 30 }
}
```
- `fairness` 可省略、為 `null`，或其欄位省略／`winCap: null`／`cooldownSeconds: 0` → 皆視為**不限制**（預設）。
- 驗證順序：讀取試算表 → 比對指紋 → 驗證題組 → **驗證公平規則** → 建立房間；任何失敗都不建立房間。
- 沒有帶 `sheetUrl`（沒有題目）卻帶了非預設的規則 → 錯誤。

### Response 201（新增 `fairness`）
```json
{
  "code": "AB12CD", "teacherToken": "…", "recoveryCode": "…", "createdAt": "…",
  "sheetTitle": "學習單",
  "questions": [ … ],
  "bundles": [ … ],
  "fairness": { "winCap": 2, "cooldownSeconds": 30 }
}
```
預設（不限制）時 `fairness` 為 `null`。

### 新增錯誤
| HTTP | code | 觸發 |
|------|------|------|
| 400 | FAIRNESS_INVALID | 見下表 |

`details`：`{ "reason": "NO_QUESTIONS | WIN_CAP_RANGE | COOLDOWN_RANGE | TYPE" }`

| reason | 觸發 |
|--------|------|
| `NO_QUESTIONS` | 房間沒有題目卻設定了上限或冷卻 |
| `WIN_CAP_RANGE` | `winCap` 不是 `1..題目數` 的整數（0、負數、大於題目數） |
| `COOLDOWN_RANGE` | `cooldownSeconds` 不是 `0..600` 的整數 |
| `TYPE` | 欄位型別錯誤（非整數、小數、字串、布林等） |

前端在預覽頁先做相同檢查（上限 1～題目數、冷卻 0～600，無效時禁用「確認建立房間」），但以伺服器結果為準。

## `POST /api/rooms/{code}/reviews`（Step 9，行為補充）
請求與回應格式**不變**。審核（駁回／恢復）成功後，整輪依公平規則重新分配；連動影響的其他單位由 WebSocket 的 `review_updated.changedUnits` 告知（見 [websocket.md](./websocket.md)）。

## 其他端點
`GET /api/rooms/{code}/records.csv` 追加兩欄，見 [csv-format.md](./csv-format.md)；回填（Step 10）自動寫入讓位後的獲勝答案，端點與契約不變。
