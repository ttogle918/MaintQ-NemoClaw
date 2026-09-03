# 사람 승인 문서 템플릿

결재에 올라가는 서류의 **양식**이다. 문안은 코드가 갖고(`render_*_document()` 패턴, D86 —
저장하지 않고 조회 시점에 렌더), 이 파일들은 **어떤 항목이 어느 자리에 들어가는지**를 고정한다.

| 파일 | 렌더 주체 | 상태 |
|---|---|---|
| `01_설비이상진단보고서.docx` | 진단 trace·evidence | D118 — MaintQ 렌더 대상 |
| `02_정비부품발주요청서.docx` | `po_drafts` | D118 — MaintQ 렌더 대상 |
| `03_자금집행요청서.docx` | `request-withdrawal` payload + 내부통제(D119) | D118 — MaintQ 렌더 대상 |
| `04_담보대출심사회신서.docx` | — | **D118 — MaintQ 구현 대상 아님**(FinAllQ 소관) |
| `05_설비처분승인서.docx` | `generate_disposal_document.render_documents()["approval"]` | 2026-09-03 신설 |
| `06_진술및보장서.docx` | 같은 함수 `["representation_warranty"]` | 2026-09-03 신설 |

## 05·06 — 처분 문서 2종 (2026-09-03 신설)

**기존 템플릿이 없어서 새로 만들었다.** 문안은 이미
`mcp_server/tools/generate_disposal_document.py::render_documents()` 가 갖고 있었고, 이
템플릿은 그 출력을 양식에 담을 자리를 정한 것이다 — **항목을 새로 발명하지 않았다.**

### 플레이스홀더 ↔ 코드 대응

`facts` 는 `evidence_bundle` 의 자산 사실이다(`build_evidence_bundle` 산출).

| 플레이스홀더 | 출처 |
|---|---|
| `{{ASSET_ID}}` `{{ACQUIRED_AT}}` `{{BUILDING_ID}}` | `facts.asset_id` · `acquired_at` · `building_id` |
| **`{{ASSET_STATUS}}`** | **`facts.status`** — 이름이 다르다. `STATUS` 는 문서 상태(`DOC_STATE`)와 헷갈려 자산임을 접두어로 밝혔다 |
| `{{DISPOSAL_MODE}}` `{{DISPOSAL_DATE}}` | `facts.disposal_mode` · `disposal_date` |
| `{{HAS_LIEN}}` `{{LIEN_CREDITOR}}` `{{LIEN_CONSENT_REF}}` | `facts.*` (앞의 것은 `_yn()` — 예/아니오) |
| `{{INSURED}}` `{{POLICY_ID}}` | `facts.*` |
| `{{SAFETY_INSPECTION_TARGET}}` `{{LAST_INSPECTION_DATE}}` `{{INSPECTION_VALID_UNTIL}}` | `facts.*` |
| `{{TAX_CREDIT_APPLIED}}` `{{MONTHS_SINCE_ACQUISITION}}` `{{VAT_INVOICE_ISSUED}}` | `facts.*` |
| `{{DECISION_ID}}` `{{DOC_STATE}}` `{{CREATED_AT}}` | `decisions` 행 |
| `{{VERDICT}}` `{{VERDICT_LINE}}` | 판정 + `_VERDICT_LINES` 설명 |
| `{{RULES_EVALUATED}}` `{{RULES_OPEN}}` `{{OPEN_CONDITIONS}}` | `bundle.evaluated` 집계 · `_open_condition_lines()` |
| `{{BUNDLE_HASH}}` | `bundle_hash` (D84) |
| `{{LAW_*}}` `{{RULE_*}}` `{{CONTRACT_*}}` | `_law_lines()` · `_rule_lines()` · `_contract_lines()` |
| `{{OVERRIDE}}` `{{OVERRIDE_REASON}}` `{{SIGNED_BY}}` `{{SIGNED_AT}}` | **서명 시** 사람이 채운다 — draft 에서는 미기재 |
| `{{REQUESTER_DEPT}}` `{{REQUESTER_NAME}}` `{{REQUEST_CHAIN_ID}}` | 신원·추적 (D23·D36·D94) |
| `{{TEMPLATE_REVIEW_NOTICE}}` | `data/doc_review.template_review_notice()` |

⛔ **`{{OVERRIDE}}`·`{{SIGNED_*}}` 를 도구가 채우지 않는다** (D81·D10). 초안에는 "미기재"로
남고 서명 화면에서만 기록된다 — 템플릿에 자리가 있다는 것이 도구가 채워도 된다는 뜻이 아니다.

### 고지 문구 3종은 양식에 **고정**돼 있다

문안이 코드에 있어도, 그 문구가 서류에서 빠질 수 있는 자리를 만들지 않는다:
1. "이 판정은 처분을 자동으로 차단하지 않는다 …" (`_NO_AUTO_BLOCK_LINE`)
2. "'확인되지 않음' 은 '해당 없음'이 아니다 …" (`_UNKNOWN_LINE`)
3. `{{TEMPLATE_REVIEW_NOTICE}}` — 사람 검수 전임을 밝히는 문구

### ⚠ 아직 하지 않은 것

**이 템플릿을 실제로 채워 `.docx` 를 만드는 코드는 없다.** 현재
`render_documents()` 는 **평문 미리보기 문자열**만 돌려준다(D86). 바이너리 생성은
`docs/07_BACKLOG.md` 「아이디어 주차장」의 "실제 .docx/.pdf 파일 생성" 항목이고,
**QMesh 프로젝트가 진행 중**이라 이 저장소에서 먼저 착수하지 않는다.
즉 05·06 은 **그 작업이 왔을 때 쓸 양식**이자, 지금은 "어떤 항목이 서류에 들어가야
하는가"의 정본이다.
