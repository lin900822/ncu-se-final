# REST Contract（Step 9 新增）

學生 WebSocket 不新增任何會改變結果的訊息型別；審核只能由老師經此端點進行。

## `POST /api/rooms/{code}/reviews`（駁回／恢復）

### Request
```http
POST /api/rooms/AB12CD/reviews
Authorization: Bearer <老師憑證>
Content-Type: application/json

{
  "round": 1,
  "unitId": "1",
  "group": "第 1 組",
  "action": "invalid",
  "reason": "答案錯誤"
}
```

| 欄位 | 型別 | 說明 |
|------|------|------|
| `round` | int | 老師畫面上目前的輪次；必須等於房間最新一輪 |
| `unitId` | string | 搶答單位：題目 id（`1`、`1-2`）或題組 id（`B1`）；取自 `snapshot.room.questions[].id`／`bundles[].id` |
| `group` | string | 組別顯示名稱（以正規化後比對） |
| `action` | `"invalid"` \| `"valid"` | 駁回／恢復有效 |
| `reason` | string | 必填，`strip()` 後非空、≤ 100 字元 |

- 憑證**只接受標頭**，網址參數無效。
- 題組只能以題組 id 整組審核；以題組成員題的 id 送出回 `UNIT_NOT_FOUND`。

### Response 200
```json
{
  "changed": true,
  "round": 1,
  "unitId": "1",
  "group": "第 1 組",
  "action": "invalid",
  "reviewedAt": "2026-11-11T03:30:00Z"
}
```
- `changed: true`：已追加一筆審核紀錄並已廣播（見 [websocket.md](./websocket.md)）。
- `changed: false`：重複動作（已駁回再駁回、有效再恢復）；**不新增紀錄、不廣播、不重複遞補**；其餘欄位為目前狀態（`reviewedAt` 為最近一次審核時間，沒有則省略）。
- 最新結果與狀態以 WebSocket 的 `review_updated`、`round_result` 為準，回應不含看板內容。

### 錯誤（沿用 `{"error": {"code","message"}}`；任何錯誤都不寫入、不廣播）

| HTTP | code | 觸發 |
|------|------|------|
| 401 | UNAUTHORIZED | 無憑證、憑證錯誤、已被換裝置後的新憑證取代 |
| 404 | ROOM_NOT_FOUND | 房間不存在（沿用既有行為） |
| 409 | ROOM_CLOSED | 房間已結束 |
| 400 | REVIEW_NOT_ALLOWED | 階段不是 Ended，或 `round` 不是最新一輪 |
| 400 | BAD_REQUEST | `action` 不是 `invalid`／`valid`，或欄位型別錯誤 |
| 400 | UNIT_NOT_FOUND | `unitId` 不是本房間題目或題組 id |
| 400 | REVIEW_TARGET_NOT_FOUND | 該組本輪在該單位沒有送出 |
| 400 | REASON_REQUIRED | 理由為空或只有空白 |
| 400 | REASON_TOO_LONG | 理由超過 100 字元 |

- 驗證順序固定：憑證 → 房間狀態 → 階段與輪次 → `action` → 單位 → 組別送出 → 理由 → 重複判斷（見 research D4）。
- 所有錯誤的回應本文**不含任何答案、組名或其他紀錄內容**。

## 其他端點
`GET /api/rooms/{code}/records.csv`（Step 8）追加四欄，見 [csv-format.md](./csv-format.md)。其餘端點不變。
