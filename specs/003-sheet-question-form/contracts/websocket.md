# WebSocket Contract（相對 Step 1、2 的新增）

## 題目形狀
```json
{ "id": "1-2", "number": 1, "sub": 2, "label": "Q1（2）" }
```
單題 `id` 為 `"3"`、`sub` 為 `null`。**不含**儲存格位置。清單順序即畫面順序。

## 學生 `/ws/student`
`joined` 新增 `questions`（新加入、重新加入、重連皆然；無題目的房間為 `[]`）：

```json
{ "type": "joined", "room": { "code": "K7M2QX" }, "group": { "name": "第 1 組" },
  "rejoined": false, "phase": "Waiting", "round": 0,
  "questions": [ { "id": "1", "number": 1, "sub": null, "label": "Q1" } ] }
```

題目在房間建立後不變，因此沒有「題目變更」事件。

## 題目文字（僅搶答中才送給學生）
新事件 `question_texts`（伺服器 → 老師與該房間所有學生），在 `phase_changed`（`Answering`）之後立即送出：

```json
{ "type": "question_texts", "round": 2, "texts": { "1-1": "題目文字…", "3": "題目文字…" } }
```
- `joined` 另含 `texts`：房間為 `Answering` 時為完整對照表，**其餘階段一律為 `{}`**（搶答開始前與結束後重連都拿不到）。
- `phase_changed` 的鍵集合維持 `{type, phase, round, changedAt}`（Step 2 契約不變）；學生端收到 `phase_changed` 為 `Ended` 時隱藏題目文字。
- 搶答開始前，學生連線不會收到任何含題目文字的訊息（原則 III、FR-014）。

## 老師 `/ws/teacher`
`snapshot.room` 新增 `sheetTitle` 與 `questions`：

```json
{ "type": "snapshot",
  "room": { "code": "K7M2QX", "status": "Open", "phase": "Waiting", "round": 0,
            "sheetTitle": "學習單", "questions": [ ... ], "texts": { "1": "題目文字…" } },
  "groups": [ ... ], "count": 1 }
```

## 保密（原則 III、FR-011）
- 題目清單僅含 `id/number/sub/label`，所有組別拿到的內容相同，且不含任何組別的作答資料。
- 學生草稿不經由任何 WebSocket 訊息傳送；`submit` 訊息仍維持 Step 2 的閘門行為，本步驟不接收作答內容。

## 客戶端行為（非契約）
- 學生端依 `questions` 動態生成填空格；同一 `number` 的多個小題分組顯示；`sub` 為 null 者直接顯示 `label`。
- 草稿存於 `localStorage`（見 data-model.md）；輸入框鎖定／解鎖沿用 Step 2 的階段與連線狀態。
