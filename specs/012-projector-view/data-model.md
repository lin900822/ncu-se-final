# Data Model: 教室大螢幕投影專用視圖

不新增任何持久資料結構；只在 `Room` 加一個欄位，其餘皆為推導資料。

## Room（修改）
| 欄位 | 型別 | 說明 |
|------|------|------|
| `projector_key` | `str` | 唯讀投影憑證；建立房間時以既有權杖產生器產生，房間存續期間固定；≠ `teacher_token`、≠ `recovery_code`；只經老師路徑下發（建立回應、老師 `snapshot.room.projectorKey`） |

## ProjectorState（推導、唯讀，不另存）
由 `projector.build_state(room)` 產生，整份推送給所有投影連線。

| 欄位 | 型別 | 說明 |
|------|------|------|
| `type` | `"projector_state"` | 訊息類型 |
| `code` | `str` | 房間代碼 |
| `status` | `"Open" \| "Closed"` | 房間狀態；Closed 時前端顯示「房間已結束」並保留最後內容 |
| `phase` | `"Waiting" \| "Answering" \| "Ended"` | 目前階段 |
| `round` | `int` | 目前輪次（尚未開始為 0） |
| `groups` | `string[]` | 已加入的組別名稱（依加入順序）；不含在線狀態 |
| `questions` | `{id,label,bundleId}[]` | 題目清單（公開資訊；與學生 `joined.questions` 相同） |
| `bundles` | `{id,questionIds}[]` | 題組設定（公開） |
| `progress` | `{answered,total} \| null` | 僅 `Answering`：已有組別送出的單位數／單位總數；其他階段為 `null` |
| `submitted` | `{[unitId]: bool} \| null` | 僅 `Answering`：各單位是否已有組別送出（**匿名**）；其他階段為 `null` |
| `result` | `RoundResult \| null` | 僅 `Ended`：與學生 `round_result` 完全相同的有效結果（`results.build_result`）；其他階段為 `null` |
| `scoreboard` | `GroupScore[]` | 已結算輪次累計得分排行；組別名單為空時為 `[]` |

### 保密不變式（憲章 III）
- `phase == "Answering"` 時，整個物件（序列化後）**不得**包含：任何送出組別的歸屬、答案、`rank`、`seq`、`submittedAt`、`outcome`、讓位／保留／名次落後資訊。`groups` 與 `scoreboard` 內的組名僅來自房間組別名單，與當輪送出無關。
- `phase == "Ended"` 時 `result` 只含各題得主組名＋答案（或 `noValid`／無人搶答），不含被駁回者、理由、名次、時間。

## GroupScore（推導）
| 欄位 | 型別 | 說明 |
|------|------|------|
| `group` | `str` | 組別名稱 |
| `score` | `int` | 已結算輪次取得題數累計（題組 N 題計 N；含 Step 11 讓位後與「保留」） |
| `rank` | `int` | 競賽排名：同分並列、下一名跳號（1、1、3）；同分者依組名排序 |

### 計算
```
settled = range(1, round)      若 phase == "Answering"
        = range(1, round + 1)  其他階段（Waiting 且 round==0 時為空）
score[g] = Σ_{n in settled} effective.allocate(room, n).wins[g]   （缺項為 0）
```
- 每輪各自以該輪的審核紀錄與公平規則重新分配（`allocate` 本身依 `round_no` 推導）。
- 房間組別名單中沒有任何取得的組別得 0 分並列出。

## Realtime（修改，記憶體）
- `projectors: dict[code, set[WebSocket]]`；`add_projector`／`remove_projector`／`broadcast_to_projectors`。
- 不在 `students`／`teachers`；不影響 `has_connections`（不阻止閒置逾時）。

## 事件觸發點（呼叫 `projector.publish(room)`）
| 事件 | 位置 |
|------|------|
| 開始搶答／結束搶答 | `phase.start_answering`／`end_answering`（開始後另送一次性 `countdown`） |
| 單題／題組送出（新紀錄） | `ws.py` 兩個 submit 路徑（重複送出不發） |
| 審核成功 | `review.publish_review` |
| 新組別加入 | `groups.announce_join`（`is_new`） |
| 房間結束 | `rooms.close_room`（`status:"Closed"`） |

## 狀態轉移（畫面）
```
連線 → [Waiting: 代碼+組別]
         └─ countdown(一次性) → [Answering: 匿名進度]
                                   └─ 結算 → [Ended: 得主看板 + 排行榜]
                                                └─ 新一輪 → countdown → [Answering] …
任何階段 ─ 房間結束 → [Closed: 房間已結束(保留最後內容)]
```
