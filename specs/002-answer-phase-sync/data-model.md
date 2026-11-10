# Data Model: 活動階段同步

僅存後端記憶體；時間為後端 UTC。對應 `diagrams/class.puml`。

## Room（擴充）

| 新增欄位 | 型別 | 說明 |
|----------|------|------|
| `phase` | `Waiting` \| `Answering` \| `Ended` | 目前階段；建立時為 `Waiting` |
| `round` | int | 已開始搶答的次數；初始 0，每次由 `Waiting/Ended → Answering` 加 1 |
| `phase_log` | list<PhaseChange> | 階段變更紀錄，僅追加 |

## PhaseChange

| 欄位 | 型別 | 說明 |
|------|------|------|
| `phase` | `Answering` \| `Ended` | 轉換後的階段（初始 `Waiting` 不記錄） |
| `round` | int | 當時輪次 |
| `changedAt` | datetime(UTC) | 後端產生 |
| `by` | `"Teacher"` | 操作者（本專案單一老師，無獨立實體） |

## 狀態轉移

```text
Waiting ──start──▶ Answering ──end──▶ Ended ──start──▶ Answering ...
```

- `start`：`Waiting`/`Ended` → `Answering`（`round += 1`，追加紀錄）；已在 `Answering` → 無變化（冪等）。
- `end`：`Answering` → `Ended`（追加紀錄）；其他階段 → 無變化（冪等）。
- 房間 `Closed`（手動或逾時）後，所有階段操作拒絕（`ROOM_CLOSED`）；學生視為鎖定。

## 規則

- 學生可否作答 = `room.status == Open` 且 `room.phase == Answering`，僅以後端判定。
- 階段事件不含任何組別資料。
