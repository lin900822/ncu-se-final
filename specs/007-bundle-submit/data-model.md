# Data Model: 題組打包提交機制

僅列相對 Step 1～6 的新增與修改；其餘實體（Group、Question、SheetSource、PhaseChange、RoundResult…）不變。
所有資料仍僅存記憶體；時間一律由後端以 UTC 產生。

## QuestionBundle（新增，屬於 Room）

| 欄位 | 型別 | 說明 |
|------|------|------|
| `id` | str | `B1`、`B2`…；依第一個成員在題目清單中的位置編號 |
| `question_ids` | list[str] | 成員題目 id，依題目順序；≥ 2 題 |

**驗證規則**（建立房間時，全部通過才建立；失敗回 `BUNDLES_INVALID`，見 [rest-api.md](./contracts/rest-api.md)）：
- 每個題組 ≥ 2 題；成員都必須是本房間的題目；
- 同一題最多屬於一個題組，同一題組內不重複；
- 成員在題目清單（Step 3 順序：題號、再小題編號）中**連續相鄰**；
- 房間沒有題目（未貼試算表）時，`bundles` 必須為空或省略。

**生命週期**：隨房間建立確定，房間存續期間不可新增、修改或刪除；新一輪搶答不影響。

**對外表示** `bundle_public(b)`：`{"id": "B1", "questionIds": ["3", "4"]}`（不含任何作答內容，可給所有學生）。

## Room（修改）

| 新增欄位 | 型別 | 說明 |
|----------|------|------|
| `bundles` | list[QuestionBundle] | 依 `id` 排序；預設空 |
| `bundle_of` | dict[str, str] | questionId → bundleId；由 `bundles` 推得，查詢用 |

| 修改欄位 | 變更 |
|----------|------|
| `rank_counts` | 鍵由 `(round, questionId)` 改為 `(round, unitId)`；`unitId` ＝ 題目所屬題組 id，未綁定時為題目 id |

**搶答單位（Answer Unit，推導概念，不另存）**：`unit_of(room, qid) = room.bundle_of.get(qid, qid)`。
送出、去重、名次、進度板、結果皆以搶答單位為範圍。

## Submission（修改）

| 新增欄位 | 型別 | 說明 |
|----------|------|------|
| `bundle_id` | str \| None | 題組送出時為題組 id；單題送出為 `None` |

**題組送出的寫入規則**（`submit_bundle`，同一無 await 區段內完成）：
- 為題組每個成員題目各追加**一筆** `Submission`；
- 這些紀錄的 `seq`、`submitted_at`、`rank`、`round`、`group_name` 完全相同，`answer` 為各題自己的答案；
- `submission_index[(round, normalized_name, questionId)]` 為每個成員各寫一筆，指向各自的紀錄；
- 去重：任一成員已在本輪有紀錄 ⇒ 整個題組已送出（成員紀錄總是一起寫入），回傳既有紀錄、不新增；
- 驗證失敗不寫入任何一筆，`next_seq`、`rank_counts` 也不變。

**不變式**：
- 同一 `(round, normalized_name, unitId)` 最多一次被接受的送出；
- 同一 `(round, bundleId)` 下，同一組別各成員紀錄的 `seq`／`rank` 相同；不同組別的 `rank` 唯一、連續、不並列；
- 題組成員題目不會有 `bundle_id = None` 的紀錄（單題 `submit` 會被 `QUESTION_IN_BUNDLE` 擋下）；
- 僅追加，建立後不可改寫（沿用 Step 4/5）。

## 推導資料的影響

| 推導 | 變更 |
|------|------|
| `build_board`（Step 5） | 邏輯不變；每題項目多 `bundleId`（未綁定為 `null`）。同題組各題 leader／ranking 相同；`leadTally` 以題數計（N 題題組計 N） |
| `build_result`（Step 6） | 不變；同題組各題 `winnerGroup` 相同、`answer` 為各題答案 |
| `my_submissions` / `submitted_by_others`（Step 4） | 不變；題組成員會一起出現 |

## 新增錯誤碼

| code | HTTP / 通道 | 訊息 |
|------|-------------|------|
| `BUNDLES_INVALID` | 400（建立房間） | 題組設定有誤 |
| `BUNDLE_NOT_FOUND` | WS 錯誤 | 找不到該題組 |
| `BUNDLE_INCOMPLETE` | WS 錯誤 | 請填完題組內所有題目 |
| `QUESTION_IN_BUNDLE` | WS 錯誤 | 此題屬於題組，請整組一起送出 |

（題組內某題超過 500 字沿用 `ANSWER_TOO_LONG`，以 `details.questionIds` 指出題目。）
