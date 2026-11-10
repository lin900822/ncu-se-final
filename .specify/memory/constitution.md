<!--
Sync Impact Report
- Version change: (unversioned template) → 1.0.0
- Modified principles: none renamed; the pre-existing "PRINCIPLE_6 圖表生成" was kept
  and renumbered as VI. PlantUML 設計優先 (content preserved verbatim in substance)
- Added sections: Principles I–V, 技術與資料約束, 開發流程與品質關卡, Governance
- Removed sections: template placeholder examples/comments
- Follow-up TODOs: none. (GUIDANCE_FILE: no runtime guidance file exists yet; Governance
  points to the .specify/ spec artifacts instead.)
-->
# 課堂搶答數位化系統 (Guided Notes Race) Constitution

## Core Principles

### I. 組別為唯一作答與競爭單位
系統 MUST 以「組別」作為作答、競爭與計分的唯一單位；個別學生身分不得參與搶答仲裁。
題目 MUST 僅以題號管理（對應紙本學習單的空格順序），不得要求額外的題型分類或題目階層結構。
理由：紙本學習單以小組合作進行，單位一致可讓資料模型與課堂實況對應，並降低複雜度。

### II. 後端依送出時間仲裁搶答順位 (NON-NEGOTIABLE)
搶答順位 MUST 由後端以伺服器端收到送出的時間戳記決定；前端時間、客戶端回報時間一律不得
作為仲裁依據。同一題同一時刻的競態 MUST 以原子操作或等效的序列化機制處理，確保結果唯一、
可重現。已確定的順位不得被靜默改寫，任何變更 MUST 留下稽核紀錄。
理由：公平性是本系統的核心價值，唯有單一可信的時間來源才能令各組信服。

### III. 學生作答過程嚴格保密
在該題結算前，各組的草稿、已送出內容與送出狀態 MUST NOT 透過任何 API、WebSocket 事件或
畫面洩漏給其他組別。即時同步僅能廣播不含答案內容的事件（例如「某題已有組別送出」、
目前進度）。答案內容僅教師與該組本身可見，其餘組別僅能於結算後看到獲勝內容。
理由：若可見他組答案即可抄襲，將破壞競賽與學習目的。

### IV. 防壟斷的公平遞補與教師仲裁權
系統 MUST 內建防壟斷機制：單一組別可獲勝的題數 MUST 設有可配置上限，達上限後該組於後續
題目的送出順位 MUST 遞補給次順位組別。教師 MUST 擁有仲裁權，可判定答案不合格、重開題目
或指定獲勝組別；每一次教師仲裁 MUST 記錄操作者、時間與理由。遞補與仲裁規則 MUST 在活動
開始前公開，並於活動進行中不得更動。
理由：確保各組皆有參與機會，並以教師判斷維護答案品質。

### V. 精準回填與完整歷程留存
活動結束後，系統 MUST 將每題獲勝組別的答案依題號精準回填至原學習單對應空格，不得錯位、
遺漏或改寫答案文字。系統 MUST 同步產出完整搶答歷程數據（每次送出的組別、題號、伺服器時間、
結果、遞補與教師仲裁事件）並以可匯出格式（至少 CSV 或 JSON）留存。回填輸出與歷程數據 MUST
可互相核對。
理由：回填結果是教學成果，歷程數據供課後檢討與申訴查證。

### VI. PlantUML 設計優先 (Design-First with PlantUML)
- 規格制定階段：在 speckit.specify 階段，MUST 使用 PlantUML 語法生成組件圖 (Component
  diagram)、類別圖 (Class diagram) 與時序圖 (Sequence diagram)，檔案 (.puml) MUST 儲存於
  `./diagrams/` 目錄。
- 產物生成：檔案建立後，MUST 使用 PlantUML CLI（`java -jar plantuml.jar "./diagrams/*.puml"`）
  將所有 .puml 轉換為 PNG，輸出圖片 MUST 儲存於相同目錄。
- 規劃階段：speckit.plan 階段 MUST 以這些圖表作為主要藍圖，生成應用程式架構與組件。
- 實作階段：speckit.implement 階段完成程式碼生成後，MUST 執行驗證步驟，確保最終程式碼與
  圖表一致；不一致時 MUST 修正程式碼或更新圖表並重新產圖。

## 技術與資料約束

- 即時同步：全班畫面 MUST 透過即時通道（如 WebSocket/SSE）同步，且 MUST 在斷線重連後能由
  後端還原目前狀態，不得依賴客戶端本地狀態作為事實來源。
- 時間來源：所有仲裁相關時間戳記 MUST 由後端產生並以 UTC 儲存。
- 資料完整性：搶答送出紀錄 MUST 為僅追加 (append-only)；更正以新增事件表達，不得覆寫原紀錄。
- 隱私：系統僅儲存組別名稱與作答內容，MUST NOT 蒐集與課堂無關的學生個資。
- 學習單回填：回填範本與題號對應 MUST 在活動建立時驗證（題號數與空格數一致）。

## 開發流程與品質關卡

- 規格先於實作：功能 MUST 先經 `/speckit-specify` 與 `/speckit-plan`，並附 Principle VI 所要求的
  圖表，才可進入 `/speckit-tasks` 與 `/speckit-implement`。
- 測試要求：針對 Principle II（競態與順位）、III（資料不外洩）、IV（遞補與仲裁）、V（回填
  正確性）的行為，MUST 有自動化測試；同時送出的併發情境 MUST 被覆蓋。
- 審查關卡：每個 PR MUST 說明其符合或影響哪些原則；違反原則者不得合併，除非依 Governance
  程序取得豁免並記錄理由。
- 簡潔性：新增複雜度（額外服務、抽象層）MUST 有書面理由，且不得牴觸 Principle I。

## Governance

- 本 Constitution 優先於其他開發慣例；規格、計畫與任務文件與之衝突時，以本文件為準。
- 修訂程序：修訂 MUST 以書面提案（含理由與對既有規格/程式的影響與遷移計畫）提出，經專案
  成員共識核准後更新本文件，並於同一提交更新版本號與 Last Amended 日期。
- 版本政策（語意化版本）：MAJOR 為不相容的原則移除或重新定義；MINOR 為新增原則/章節或
  實質擴充；PATCH 為文字澄清與非語意修正。
- 合規審查：每次 `/speckit-plan` 的 Constitution Check 與每個 PR 審查 MUST 驗證合規；
  每個階段里程碑結束時 SHOULD 複查原則是否仍符合課堂實務。
- 執行期指引：以 `.specify/` 下的規格、計畫與任務產物作為日常開發指引。

**Version**: 1.0.0 | **Ratified**: 2026-11-10 | **Last Amended**: 2026-11-10
