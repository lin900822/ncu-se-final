# 課堂搶答數位化系統 — Step 1：房間建立與學生加入

老師建立房間取得代碼，學生輸入代碼與組名加入，老師端即時列出已加入的組別。

## 前置需求

- [nvm](https://github.com/nvm-sh/nvm)（前端使用 Node.js 22 LTS）
- [uv](https://docs.astral.sh/uv/)（後端 Python 3.12 由 uv 自動取得）

## 啟動

需要開**兩個終端機**，先啟動後端，再啟動前端。以下指令都從專案根目錄開始。

### 1. 後端（終端機 A）

```bash
cd backend
uv sync
uv run uvicorn app.main:app --reload --port 8000 --ws-ping-interval 10 --ws-ping-timeout 10
```

- 服務位址：http://localhost:8000
- 必須使用**單一 worker**（不要加 `--workers`）；資料只存在記憶體，後端重啟後所有房間都會消失。
- `--ws-ping-interval` / `--ws-ping-timeout` 用來偵測異常斷線，約 20 秒內會把該組判定為離線。

### 2. 前端（終端機 B）

```bash
cd frontend
nvm install   # 第一次使用時安裝 .nvmrc 指定的 Node 22
nvm use
npm install
npm run dev
```

- 開啟 http://localhost:5173
- 開發時 `/api` 與 `/ws` 會由 Vite 代理到後端 8000 埠，不需另外設定 CORS。
- 若瀏覽器打不開 `localhost`，可改用 `npm run dev -- --host 127.0.0.1`，並開啟 http://127.0.0.1:5173。

### 3. 使用方式

1. 老師開啟首頁 → 「我是老師 — 建立房間」，取得房間代碼與恢復碼。
2. 學生開啟首頁 → 「我是學生 — 加入房間」，輸入房間代碼與組名（例如「第 1 組」）。
3. 老師端畫面會即時列出已加入的組別與在線/離線狀態。

## 其他指令

```bash
# 前端正式建置
cd frontend && npm run build

# 重新產生設計圖 PNG（需安裝 plantuml：brew install plantuml）
plantuml -tpng diagrams/*.puml
```

## 環境變數（後端，皆選用）

| 變數 | 預設 | 說明 |
|------|------|------|
| `ROOM_IDLE_SECONDS` | `7200` | 房間閒置多久後自動結束（秒） |
| `ROOM_SCAN_SECONDS` | `30` | 閒置掃描間隔（秒） |

例如快速驗證閒置逾時：`ROOM_IDLE_SECONDS=30 ROOM_SCAN_SECONDS=5 uv run uvicorn app.main:app --port 8000`

## 文件

規格、計畫、介面契約與手動驗證步驟見 `specs/001-room-join/`；設計圖見 `diagrams/`。
