# REST Contract（Step 12 修改）

本步驟**不新增 REST 端點**。投影視圖的資料全部經 `/ws/projector` 取得；投影憑證打任何既有 REST 老師端點一律 `401`。

## `POST /api/rooms`（回應新增欄位）
```json
{ "code": "AB12CD", "teacherToken": "…", "recoveryCode": "…", "projectorKey": "…", "...": "…" }
```
- `projectorKey`：唯讀投影憑證；只在此回應與老師 `snapshot.room.projectorKey` 出現。
- 投影網址由前端組成：`/projector?code=<code>&key=<projectorKey>`。

## `POST /api/rooms/recover`
回應不變（不含 `projectorKey`）；老師以新 token 連 `/ws/teacher` 後由 `snapshot.room.projectorKey` 取得**同一把**投影憑證。

## 既有端點與投影憑證
| 端點 | 以投影憑證呼叫 |
|------|----------------|
| `POST /api/rooms/{code}/phase/start`、`phase/end`、`reviews`、`backfill`、`backfill/preview`、`close` | `401 UNAUTHORIZED`（只認老師 token） |
| `GET /api/rooms/{code}/records.csv` | `401` |
| `GET /api/rooms/{code}/status` | 不變（公開，只回 `open`） |
