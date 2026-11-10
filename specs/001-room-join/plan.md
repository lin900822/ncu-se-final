# Implementation Plan: 房間建立與學生加入

**Branch**: `001-room-join` | **Date**: 2026-11-10 | **Spec**: [spec.md](./spec.md)

**Input**: Feature specification from `/specs/001-room-join/spec.md`

## Summary

老師建立房間並取得房間代碼與老師專用恢復碼；學生以代碼與組名加入；老師端即時看到各組在線/離線狀態。
技術做法：後端以 FastAPI 提供少量 REST（建房、恢復、結束）與兩條 WebSocket（老師、學生），所有狀態
存在單一程序的記憶體中，後端為唯一事實來源；前端為 React + Vite + Tailwind CSS 的單頁應用，
斷線後自動重連並由後端推送完整快照還原畫面。依設計圖（`diagrams/`）拆分為房間服務、組別服務、
即時廣播通道、逾時排程與記憶體儲存。

## Technical Context

**Language/Version**: 後端 Python 3.12（由 uv 管理）；前端 TypeScript，Node.js 22 LTS（由 nvm 管理，`.nvmrc` 固定）

**Primary Dependencies**: 後端 FastAPI、uvicorn[standard]（含 WebSocket 支援）；前端 React 19、Vite、Tailwind CSS v4（`@tailwindcss/vite`）、react-router-dom；套件管理：後端 uv、前端 npm

**Storage**: 僅記憶體（程序內 dict + asyncio.Lock），不使用資料庫；程序重啟後房間全部消失（已接受，見 Assumptions）

**Testing**: 依使用者指示本階段不撰寫自動化測試；以 [quickstart.md](./quickstart.md) 的手動驗證情境驗收

**Target Platform**: 本機/單機伺服器（單一 uvicorn worker）；現代桌面與手機瀏覽器

**Project Type**: web-application（frontend + backend）

**Performance Goals**: 加入後 2 秒內老師端顯示（SC-003）；單房間 40 組、約 80 條連線

**Constraints**: 必須單一 worker（狀態在記憶體）；所有時間戳記為後端產生的 UTC；不蒐集學生個資

**Scale/Scope**: 單一課堂規模（數個房間、每房間 ≤ 40 組）；前端 3 個畫面（首頁、老師端、學生加入/等待）

## Constitution Check

*GATE: Must pass before Phase 0 research. Re-check after Phase 1 design.*

| 原則 / 約束 | 本階段判定 | 說明 |
|-------------|-----------|------|
| I 組別為唯一單位 | ✅ 通過 | 只有 Group 實體，不記錄個別學生（FR-010） |
| II 後端仲裁搶答 | ➖ 不適用 | 本階段無搶答；所有時間戳記仍由後端產生（UTC） |
| III 作答保密 | ✅ 通過 | 學生連線只收到自己的狀態；組別清單只推給持有老師憑證的連線（FR-009） |
| IV 防壟斷與仲裁 | ➖ 不適用 | 後續步驟 |
| V 回填與歷程 | ➖ 不適用 | 後續步驟 |
| VI PlantUML 設計優先 | ✅ 通過 | `diagrams/` 已有三張圖與 PNG，並已含澄清結果；實作後須驗證一致 |
| 即時同步與斷線還原 | ✅ 通過 | 連線建立即推送完整快照，後端為事實來源 |
| 隱私 | ✅ 通過 | 僅儲存組名 |
| 測試要求 | ✅ 通過（無衝突） | 憲法要求測試的對象為原則 II–V 的行為，本階段皆不適用；使用者指示不寫測試與之不衝突。後續含 II–V 的步驟須補測試 |
| 簡潔性 | ✅ 通過 | 無資料庫、無額外服務、無額外抽象層 |

**Post-Phase 1 重新檢查**：設計後仍全部通過，無需填寫 Complexity Tracking。

## Project Structure

### Documentation (this feature)

```text
specs/001-room-join/
├── plan.md
├── research.md
├── data-model.md
├── quickstart.md
├── contracts/
│   ├── rest-api.md
│   └── websocket.md
└── tasks.md             # 由 /speckit-tasks 產生
```

### Source Code (repository root)

```text
diagrams/                      # 既有 PlantUML 藍圖（component/class/sequence + PNG）

backend/
├── pyproject.toml             # uv 管理
├── .python-version
└── app/
    ├── main.py                # FastAPI 應用、CORS、啟動逾時排程
    ├── models.py              # Room、Group 資料類別與回應 schema
    ├── store.py               # 記憶體儲存（房間字典 + 鎖）
    ├── normalize.py           # 組名/房間代碼正規化
    ├── services/
    │   ├── rooms.py           # 房間服務：建立、恢復、結束、逾時
    │   └── groups.py          # 組別服務：加入、在線/離線、唯一性
    ├── realtime.py            # 即時廣播通道：連線登記與推送
    └── api/
        ├── rooms.py           # REST 路由
        └── ws.py              # 老師/學生 WebSocket 路由

frontend/
├── package.json
├── .nvmrc
├── vite.config.ts             # 開發時代理 /api 與 /ws 至後端
└── src/
    ├── main.tsx
    ├── index.css              # Tailwind 入口
    ├── App.tsx                # 路由
    ├── pages/
    │   ├── Home.tsx
    │   ├── TeacherRoom.tsx
    │   └── StudentJoin.tsx
    ├── hooks/
    │   └── useReconnectingSocket.ts
    └── lib/
        └── api.ts
```

**Structure Decision**: 採 Web application（前後端分離）。後端的檔案與設計圖組件一一對應：
房間服務 → `services/rooms.py`、組別服務 → `services/groups.py`、即時廣播通道 → `realtime.py`、
房間狀態儲存 → `store.py`、房間逾時排程 → `main.py` 啟動的背景任務。

## Complexity Tracking

無違反項目，不需填寫。
