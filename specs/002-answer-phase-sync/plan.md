# Implementation Plan: 活動階段同步（開始／結束搶答）

**Branch**: `002-answer-phase-sync`（規格目錄；實際在 master 開發） | **Date**: 2026-11-10 | **Spec**: [spec.md](./spec.md)

**Input**: Feature specification from `/specs/002-answer-phase-sync/spec.md`

## Summary

在 Step 1 的房間上加入「階段」：`Waiting`（等待搶答）→ `Answering`（搶答中）→ `Ended`（已結束搶答），
老師可重複開始／結束。老師以 REST 觸發階段變更；後端在同步區段內更新 `Room.phase`、追加階段紀錄
（UTC），再把只含階段資訊的 `phase_changed` 事件廣播給同房間所有老師與學生連線。學生端依階段
解鎖／鎖定輸入框；加入、重新整理、重連時，後端在 `joined` 與老師 `snapshot` 內附上目前階段，前端以此
為準。學生 WebSocket 另加一個 `submit` 閘門：非 `Answering` 一律回 `PHASE_LOCKED`（本步驟不儲存
答案，實際送出留給 Step 3）。沿用 Step 1 的 FastAPI + 記憶體儲存 + React/Vite 架構，不新增服務。

## Technical Context

**Language/Version**: 後端 Python 3.12（uv）；前端 TypeScript，Node.js 22 LTS（沿用 Step 1）

**Primary Dependencies**: 沿用 FastAPI、uvicorn[standard]、React 19、Vite、Tailwind CSS v4、react-router-dom；新增開發依賴 pytest（見 Testing）

**Storage**: 沿用僅記憶體；`Room` 新增 `phase`、`round`、`phase_log`（僅追加 list）

**Testing**: 憲法要求原則 III（廣播不洩漏）行為須有自動化測試，且本步驟引入「後端拒絕鎖定中送出」的閘門，故新增少量 pytest（Starlette `TestClient` 的 REST + WebSocket）：階段轉換與冪等、非老師被拒、廣播內容僅含階段欄位、鎖定時 `submit` 被拒、重連快照階段正確。其餘以 [quickstart.md](./quickstart.md) 手動驗證

**Target Platform**: 本機/單機伺服器（單一 uvicorn worker）；現代桌面與手機瀏覽器

**Project Type**: web-application（frontend + backend）

**Performance Goals**: 開始/結束後 2 秒內 40 組學生端完成解鎖/鎖定（SC-002、SC-003）；廣播為單房間約 40 條連線的記憶體內迭代，無瓶頸

**Constraints**: 單一 worker；階段與時間戳記皆由後端產生（UTC）；廣播不含作答內容；階段變更在無 `await` 的同步區段完成（沿用 store.py 的原子性假設）

**Scale/Scope**: 單房間 ≤ 40 組；前端僅修改老師端與學生端兩個畫面

## Constitution Check

*GATE: Must pass before Phase 0 research. Re-check after Phase 1 design.*

| 原則 / 約束 | 本階段判定 | 說明 |
|-------------|-----------|------|
| I 組別為唯一單位 | ✅ 通過 | 階段屬於房間，對全班一體適用；不記錄個別學生 |
| II 後端仲裁搶答 | ✅ 通過（前置） | 尚無順位仲裁；但「能否作答」由後端階段決定（FR-007），階段時間為後端 UTC，為後續仲裁鋪路 |
| III 作答保密 | ✅ 通過 | `phase_changed` 只含 `phase`/`round`/`changedAt`，不含任何組別資料；學生連線仍收不到他組資料；有自動化測試 |
| IV 防壟斷與仲裁 | ➖ 不適用 | 後續步驟 |
| V 回填與歷程 | ➖ 不適用 | 後續步驟；本步驟的 `phase_log` 為歷程資料來源之一 |
| VI PlantUML 設計優先 | ✅ 通過 | `diagrams/` 已含階段（phase/PhaseChange、階段服務、開始/結束時序）並重新產圖；實作後須驗證一致 |
| 即時同步與斷線還原 | ✅ 通過 | 加入與老師連線一律回傳目前階段，後端為事實來源 |
| 資料完整性（append-only） | ✅ 通過 | 階段紀錄僅追加，不覆寫 |
| 時間來源 | ✅ 通過 | UTC、後端產生 |
| 隱私 | ✅ 通過 | 無新增個資 |
| 測試要求 | ✅ 通過 | 見 Testing；III 與鎖定閘門有測試 |
| 簡潔性 | ✅ 通過 | 無新服務；階段服務為 `services/phase.py` 單一模組；以 `round` 計數取代更複雜的題目模型 |

**Post-Phase 1 重新檢查**：設計後仍全部通過，無需填寫 Complexity Tracking。

## Project Structure

### Documentation (this feature)

```text
specs/002-answer-phase-sync/
├── plan.md
├── research.md
├── data-model.md
├── quickstart.md
├── contracts/
│   ├── rest-api.md
│   └── websocket.md
├── checklists/requirements.md
└── tasks.md             # 由 /speckit-tasks 產生
```

### Source Code (repository root)

```text
diagrams/                       # 已更新：class / component / sequence（含 PNG）

backend/
├── pyproject.toml              # 新增 dev 依賴 pytest
├── app/
│   ├── models.py               # 修改：Room 加 phase/round/phase_log；PhaseChange；錯誤碼 PHASE_LOCKED
│   ├── realtime.py             # 修改：新增 broadcast_to_students；send_student
│   ├── services/
│   │   ├── phase.py            # 新增：start_answering / end_answering / ensure_answering
│   │   ├── rooms.py            # 修改：snapshot 附 phase
│   │   └── groups.py           # （不變；joined 在 ws.py 附 phase）
│   └── api/
│       ├── rooms.py            # 修改：POST /{code}/phase/start、/phase/end
│       └── ws.py               # 修改：joined 附 phase；學生 submit 閘門
└── tests/
    ├── conftest.py
    └── test_phase.py

frontend/src/
├── lib/api.ts                  # 修改：startAnswering / endAnswering
└── pages/
    ├── TeacherRoom.tsx         # 修改：階段顯示與開始/結束按鈕；處理 phase_changed
    └── StudentJoin.tsx         # 修改：等待/搶答中/已結束；輸入框鎖定與 round 清空
```

**Structure Decision**: 沿用 Step 1 的前後端分離結構。圖中新增的「階段服務」對應 `services/phase.py`，
階段事件經既有「即時廣播通道」`realtime.py`；階段紀錄存於既有記憶體儲存中的 `Room`。

## Complexity Tracking

無違反項目，不需填寫。
