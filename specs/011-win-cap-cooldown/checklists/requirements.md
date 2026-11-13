# Specification Quality Checklist: 公平機制：獲勝上限與冷卻限制

**Purpose**: Validate specification completeness and quality before proceeding to planning
**Created**: 2026-11-11
**Feature**: [spec.md](../spec.md)

## Content Quality

- [x] No implementation details (languages, frameworks, APIs)
- [x] Focused on user value and business needs
- [x] Written for non-technical stakeholders
- [x] All mandatory sections completed

## Requirement Completeness

- [x] No [NEEDS CLARIFICATION] markers remain
- [x] Requirements are testable and unambiguous
- [x] Success criteria are measurable
- [x] Success criteria are technology-agnostic (no implementation details)
- [x] All acceptance scenarios are defined
- [x] Edge cases are identified
- [x] Scope is clearly bounded
- [x] Dependencies and assumptions identified

## Feature Readiness

- [x] All functional requirements have clear acceptance criteria
- [x] User scenarios cover primary flows
- [x] Feature meets measurable outcomes defined in Success Criteria
- [x] No implementation details leak into specification

## Notes

- 第 1 輪驗證即全數通過；未留下 [NEEDS CLARIFICATION]，以下決定以合理預設寫入 Assumptions，可用 `/speckit-clarify` 調整（**建議優先釐清前三項**）：
  1. **全員不符資格時保留**：所有有效送出者都達上限或冷卻中時，由名次最前者保留該題（不讓題目懸空、回填不出現空格）。
  2. **冷卻的定義**：從「該組上一次取得題目」那筆送出的收到時間起算；被讓位或被駁回的送出不啟動冷卻；選用、預設關閉。
  3. **題組計入上限**：題組取得計 N 題，只看「取得前題數是否小於上限」，因此題組可能使該組略超過上限一次。
  4. 分配依後端處理序由先到後逐筆判定（「成功搶得 2 題後」＝依處理序較早取得的兩個單位）。
  5. 達上限的組別仍可送出，系統不阻擋，只決定誰取得首選資格；學生在結算前看不到任何分配資訊。
  6. 規則在建立房間時設定、之後固定；預設不設上限、不設冷卻；每輪重新計算。
- **老師駁回會連動**：駁回使該組空出名額，可能讓原本讓位的另一題改回該組，其他題目的獲勝者隨之改變（FR-011、FR-013）；老師端須能看出受影響的題目。
- **向下相容**：沒有設定公平規則的房間，所有結果與 Step 9 完全相同（SC-010）。
- 因為結果、看板、匯出與回填都共用同一處「有效結果」推導（Step 9），本功能不需要各自處理公平規則。
- 憲章對照：原則 IV 本步驟實作「單一組別可獲勝題數上限，達上限後後續題目的順位遞補給次順位組別」，並於活動開始前公開規則、進行中不更動；防壟斷落實後，原則 IV 的「教師仲裁」（Step 9）與「獲勝上限」兩項皆已具備，仍未做的是「重開題目」與「指定獲勝組別」（FR-017）。原則 II：原始答案、時間、名次永不改寫。原則 III：結算前學生端無分配資訊。
- 憲章原則 VI：`diagrams/*.puml` 已更新（類別圖新增 FairnessRule 與 EffectiveResult 狀態、組件圖新增公平規則、時序圖新增建立房間時的規則驗證與結算時的逐筆判定），PNG 已重新產生。
