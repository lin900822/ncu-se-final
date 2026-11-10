# Phase 0 Research: 房間建立與學生加入

本階段無未解的 NEEDS CLARIFICATION；以下記錄技術選型與關鍵設計決定。

## 1. 即時通道：WebSocket（而非 SSE 或輪詢）
- **Decision**: 老師與學生各一條 WebSocket，由 FastAPI 原生支援。
- **Rationale**: 在線/離線以「連線是否存在」判定，WebSocket 的開閉與 ping/pong 逾時剛好提供此訊號；
  SSE 無法讓伺服器可靠得知學生端離線。後續步驟的搶答也需要雙向通訊。
- **Alternatives**: SSE + REST（學生離線判定需額外心跳）；輪詢（延遲與負載較差，違反 2 秒目標的穩定性）。

## 2. 學生加入走 WebSocket 首則訊息（而非先 REST 再 WS）
- **Decision**: 學生連上 `/ws/student` 後送出 `join`，後端在單一事件迴圈中同步完成「驗證房間 → 正規化組名
  → 檢查在線 → 標記在線」。
- **Rationale**: 「在線時拒絕」(FR-005) 與「同時加入同組名只產生一個組別」(Edge Case) 需原子判定；
  先 REST 再開 WS 會有兩步之間的競態。asyncio 單執行緒內無 `await` 的臨界區即為原子。
- **Alternatives**: REST 加入後發 session token（多一組憑證與競態處理，無額外好處）。

## 3. 在線/離線判定與異常斷線
- **Decision**: 在線 = 該組有一條已通過 `join` 的開啟中連線。uvicorn 啟用 WebSocket ping（間隔 10 秒、
  逾時 10 秒）以偵測異常斷線；前端遇到「該組目前在線」時於重新整理場景自動退避重試（約 2 秒間隔，最多 5 次）。
- **Rationale**: 對應 Story 4 情境 2（異常斷線尚未被判定離線時暫時拒絕）。
- **Alternatives**: 後來者取代舊連線（已於澄清中被否決）。

## 4. 老師身分：憑證 + 恢復碼
- **Decision**: 建房時產生 `teacherToken`（隨機 32 位元組 URL-safe）與 `recoveryCode`（10 碼、去除易混淆字元）。
  token 存於老師瀏覽器 `localStorage`；換裝置以恢復碼呼叫 recover，換發新 token 並使舊 token 失效。
  房間代碼不具任何老師權限（FR-012）。
- **Rationale**: 不需帳號系統；兩者分離避免學生靠投影的房間代碼冒充老師。
- **Alternatives**: 老師帳號登入（超出本階段範圍）。

## 5. 房間代碼與組名正規化
- **Decision**: 房間代碼 6 碼，字元集為大寫字母與數字並排除 `0 O 1 I L`；輸入時去空白並轉大寫。
  組名比對用 `NFKC` 正規化 → 移除所有空白 → `casefold`；顯示用名稱保留首次加入時去除前後空白的原文。
  長度上限 20 字元（以正規化前、去除前後空白後計）。
- **Rationale**: `NFKC` 讓「第１組」=「第 1 組」；移除內部空白使「第1組」=「第 1 組」，符合課堂直覺。
- **Alternatives**: 僅 `strip`（無法滿足全半形規則）。

## 6. 房間逾時（閒置 2 小時）
- **Decision**: 背景 asyncio 任務每 30 秒掃描；房間 `lastActivityAt` 於任何連線建立、斷開或訊息時更新，
  且只要房間仍有開啟中連線即視為活動中。滿 2 小時無活動則結束（`closedReason = IdleTimeout`）。
  已結束的房間保留於記憶體 24 小時以便顯示「已結束」，之後清除。
- **Rationale**: 對應 FR-013；課堂中老師端一直開著不應被誤關。

## 7. 前端
- **Decision**: React + Vite + TypeScript + Tailwind CSS v4 + react-router-dom；Node 22 LTS（目前本機為 Node 18，
  Vite 7 需要 Node 20.19+，故以 `.nvmrc` 指定並用 nvm 切換）。開發時 Vite 代理 `/api`、`/ws` 到
  `localhost:8000`，避免 CORS。`useReconnectingSocket` 負責指數退避重連；重連後等待後端快照覆蓋畫面狀態。
- **Alternatives**: Next.js（SSR 對本專案無益）。

## 8. 後端執行與限制
- **Decision**: `uv run uvicorn app.main:app`，**單一 worker**；狀態放於模組層級的 `Store`，以 `asyncio.Lock` 保護
  會跨 `await` 的操作。
- **Rationale**: 記憶體儲存無法跨程序共享；多 worker 會讓房間不一致。
