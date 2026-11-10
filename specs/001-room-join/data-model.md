# Data Model: 房間建立與學生加入

所有資料僅存於後端記憶體；時間皆為後端產生的 UTC。對應 `diagrams/class.puml`。

## Room

| 欄位 | 型別 | 說明 |
|------|------|------|
| `code` | string(6) | 房間代碼，唯一（含已結束但尚未清除的房間） |
| `status` | `Open` \| `Closed` | 房間狀態 |
| `createdAt` | datetime(UTC) | 建立時間 |
| `lastActivityAt` | datetime(UTC) | 最後活動時間（FR-013） |
| `teacherToken` | string | 目前有效的老師憑證；recover 後換發 |
| `recoveryCode` | string(10) | 老師專用恢復碼，與 `code` 不同 |
| `closedReason` | `Manual` \| `IdleTimeout` \| null | 結束原因 |
| `closedAt` | datetime(UTC) \| null | 結束時間（供 24 小時後清除） |
| `groups` | map<normalizedName, Group> | 房間內組別 |

**驗證 / 規則**
- `code` 與 `recoveryCode` 隨機產生，碰撞時重新產生。
- 狀態轉移：`Open → Closed`（手動或逾時），不可逆；`Closed` 房間拒絕所有加入。

## Group

| 欄位 | 型別 | 說明 |
|------|------|------|
| `name` | string(≤20) | 顯示名稱（首次加入時去除前後空白的原文） |
| `normalizedName` | string | NFKC → 移除空白 → casefold；房間內唯一鍵 |
| `online` | bool | 是否有一條已通過 `join` 的開啟連線 |
| `joinedAt` | datetime(UTC) | 首次加入時間 |

**狀態轉移**
- 不存在 → 在線：首次加入。
- 在線 → 離線：連線關閉或 ping 逾時。
- 離線 → 在線：相同正規化組名再次加入。
- 在線時再次加入 → 拒絕（`GROUP_ONLINE`），不改變狀態。

## Teacher
無獨立實體：身分由房間的 `teacherToken` 表示（Constitution 之簡潔性）。

## 執行期連線登記（非持久資料）
- `teacherConnections`：房間 → 持有有效 token 的老師 WebSocket 集合。
- `studentConnection`：(房間, normalizedName) → 該組目前唯一的 WebSocket。
