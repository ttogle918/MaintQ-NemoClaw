# 시나리오 v1.0 (S1~S4)

4개 시나리오는 각각 다른 오케스트레이션 패턴을 증명한다:
**순차 실행 / 조건 분기 / 이력 기반 판단+가드레일 / 실패 처리**
데모 영상도 이 순서로 촬영한다.

> 에러코드는 iG5A 기준. M1 추출(2026-07-18)로 실제 매뉴얼 대조 완료 — OHt(PDF p.202)·OCt(p.204) 모두 실재하며, 두 기종 공통 표기 코드 12종 확보(D6 실증 자료).
> 인용 페이지는 전부 **PDF 물리 페이지** 기준 (D26).

---

## S1. 풀 파이프라인 (해피패스) — 순차 실행

- 사용자: 정비사
- 입력: "iG5A 인버터에 OHt 에러 떴어"
- 흐름:
  1. 헤더에서 장비 컨텍스트 확인 (미선택 시 모델 확인 질문)
  2. `lookup_error_code` → 과열: 냉각팬 고장/주위온도 초과
  3. `rag_search_manual` → 점검 절차 + 근거 페이지 인용
  4. 부품 특정 (error_codes.related_parts → 냉각팬)
  5. `search_inventory` → 재고 1, 안전재고 3 미달
  6. `get_supplier_quotes` → A사 3일/₩38,000 vs B사 14일/₩29,000 비교 제시
  7. 사용자 선택 → `create_po_draft` → **팀장 승인 요청 (draft→pending)**
- 성공 기준: 올바른 부품 특정, 발주서에 정확한 품번/수량/공급사, 인용 페이지 존재

## S2. 재고 없음 → 대체품 분기 — 조건 분기

- 사용자: 정비사 (진단 없이 중간 진입 — **다양한 엔트리 포인트의 의도적 케이스**)
- 입력: "S100 인버터 제어보드 교체해야 해"
- 흐름:
  1. `search_inventory` → **qty 0** (+ 단종)
  2. `find_alternative_parts` → 호환 확정(compat_confirmed=true) 대체품 발견
  3. 원부품 vs 대체품 리드타임·단가 비교 제시 → 사용자 선택 → 발주 초안
- 서브 분기: 대체품도 없으면(`status: empty`) → 긴급 견적 요청 + 담당자 에스컬레이션 메시지 초안 (suppliers.contact 활용)
- 성공 기준: compat_confirmed=false 부품은 절대 제안하지 않음, 임의 발주 없음

## S3. 반복 고장 + 안전 가드레일 — 이력 기반 판단 (확정 기능 ①②)

- 사용자: 정비사
- 입력: "3번 라인 인버터 또 OCt 떴어"
- 흐름:
  1. `lookup_error_code` → 과전류
  2. `get_error_history` → **30일 내 3회, repeated=true** (매번 '리셋'만 수행됨)
  3. 단순 리셋/부품교체 대신 **근본원인 점검 모드** 진입: 출력측 지락, 모터 절연 저하, 부하 이상 등
  4. `rag_search_manual` → 점검 절차 안내, 이때 **⚠ 안전 경고 필수 삽입**
     (전원 차단 후 **10분 이상** 대기 + 테스터로 직류 전압 방전 확인, 활선 절연 측정 금지
     — 매뉴얼 명시값. 근거: iG5A 표준본 p.4·트러블슈팅 p.6, S100 p.2 — PDF 물리 페이지, D26)
  5. 점검 체크리스트 출력, **발주는 원인 확정 시까지 보류**
     — 발주 카드 자리에 `block`(type: `po_card`, **variant: `hold`**) 로 "발주 보류" 블록 전달 (D35).
       발주 카드가 아니며, 텍스트로 흘리지 않는다
- 성공 기준: repeated=true 시 근본원인 모드 진입률 100%, 위험 작업 언급 시 안전 경고 누락 0건

## S4. 미지 에러코드 — 실패 처리 (환각 방지)

- 사용자: 정비사
- 입력: 매뉴얼에 없는 코드 (예: "XY9 에러가 떴는데")
- 흐름:
  1. `lookup_error_code` → **status: not_found**
  2. 유사 코드 추측 **금지** — "해당 기종 매뉴얼에서 확인되지 않는 코드"임을 명시
  3. 확인 가능한 대안 제시: 표시부 오독 가능성 안내(재확인 요청), 제조사 A/S 연락처, 문의 메일 초안 생성
- 성공 기준: 존재하지 않는 코드에 대한 원인/조치 생성(환각) 0%

---

## 도구 호출 시퀀스 요약

| 시나리오 | 시퀀스 | 분기 트리거 |
|---|---|---|
| S1 | lookup → rag → inventory → quotes → po_draft | — |
| S2 | inventory(qty=0) → alternatives → quotes → po_draft | qty==0 / status:empty |
| S3 | lookup → history(**repeated**) → rag → 발주 보류 | repeated==true |
| S4 | lookup(**not_found**) → A/S 안내 | status:not_found |

### 확장 시나리오 (자산 생애주기 — 정본은 `11_ASSET_LIFECYCLE §6`)

| 시나리오 | 시퀀스 | 비고 |
|---|---|---|
| **S1+** 수리 판단 | classify_part_criticality → get_maintenance_metrics → **assess_repair_value** → (필요 시) classify_expenditure | `repeat_failure` 면 3지 판단보다 **근본원인이 먼저**(S3 우선) |
| **S9** 처분 차단 | (사전 경보) **track_deadlines**(법정 기한 임박, Sprint 11, D102) → **check_disposal_blockers** → 해소 경로 안내 | REST 는 409 (D71). "안 된다"로 끝내지 않는다 · UI: `/manager/deadlines`(Sprint 12) |
| **S10** 근거 번들 → 서명 | precheck → **[요청] `/technician?prefill=…` 로 이동해 사용자가 전송** → 에이전트가 `generate_disposal_document`(draft INSERT) → **[제출] 자산 화면의 `submitDecision`** → `/api/approvals` → 팀장 `sign` | ⚠ **요청은 prefill, 제출은 자산 화면.** `decision_card` block 은 **만들지 않았다** — block 3종(`safety`·`po_card`·`citation`) 고정이 계약이다(D14·D22) |
| **S18** 중고 취득 검증 | **verify_ownership(PARTIAL)** → 잔여 리스크 + 계약상 배분 안내 → (실사 보존) **assess_risk_grade**(건물 위험등급, Sprint 11, D102) | `PARTIAL` → `VERIFIED` 승격 경로 없음. UI 도 성공색으로 그리지 않는다(D87) · UI: `/manager/risk-grade`(Sprint 12) |
| **S29** 수리 증빙 서명 | `create_repair_record`(draft INSERT) → **[제출]** `POST /api/repairs/{id}/submit`(technician) → **[서명]** `POST /api/repairs/{id}/sign`(manager, D98) | **구현 완료 — Sprint 9** (P25). Sprint 7·8 에서 연속 이월된 뒤 착수됐다. 정본 병합(MQ-919, `actions` 결측 회수)은 사람 승인 대기 |
| ~~**S17** 법령 개정 감지~~ | — | **v2 로 제외.** `fetch_laws.check_revisions()` 는 코드에 살아 있으나(D75 가 쓴다) **MCP 도구로 노출하지 않는다** (`11 §10-3`) |
