# MCP 도구 스키마 v0.2
설비보전 AI 에이전트 · **읽기 도구 6종 + 쓰기 도구 1종 = 총 7종** (get_lead_time을 get_supplier_quotes로 흡수 — D8)

---

## 공통 설계 원칙

1. **description이 오케스트레이션의 절반이다.** 각 도구 설명에 "언제 사용 / 언제 사용 금지"를 명시한다. LLM의 도구 선택 품질은 스키마 설명 품질에 비례한다.
2. **실패도 구조화된 결과로 반환한다.** 예외를 던지지 않고 `status` 필드로 반환해 에이전트가 분기(S2, S4)할 수 있게 한다. `status: "ok" | "not_found" | "empty" | "error"`
3. **읽기/쓰기 도구를 분리한다.** 쓰기 도구는 `create_po_draft` 하나뿐이며, draft 상태만 생성 가능. 확정은 승인 큐(사람)에서만.
4. **model은 명시 파라미터.** enum으로 강제해 "같은 코드, 다른 의미" 오염을 스키마 수준에서 차단.

---

## 1. lookup_error_code — 에러코드 정확 조회 (룩업)

> 구조화 추출된 에러코드 표에서 exact match. RAG 아님.

**description 초안:** "인버터/PLC 에러코드의 공식 정의·원인·조치를 조회한다. 에러코드가 명확할 때 가장 먼저 사용. 코드가 표에 없으면 not_found를 반환하며, 이때 유사 코드를 추측하지 말 것."

```json
// input
{
  "model": "iG5A | S100",     // enum, required
  "code": "OHt"                // required — 대소문자 무관 매칭 (D25: 내부는 대문자 canonical)
}
// output
{
  "status": "ok",
  "code": "OHT",               // 대문자 canonical (D25)
  "display_code": "OHt",       // 키패드 원표기 보존 (D25)
  "error_name": "인버터 과열",
  "severity": "warning | fault | critical",
  "causes": ["냉각팬 고장", "주위 온도 초과", "..."],
  "actions": ["냉각팬 점검", "..."],
  "related_parts": ["FAN-IG5-01"],   // ★ 진단→부품 특정의 다리 (D12·D20). 이 값으로 search_inventory 호출
  "manual_page": 208
}
// status: "not_found" → S4 분기 트리거 (A/S 안내 + 문의 초안)
```

## 2. rag_search_manual — 매뉴얼 본문 RAG 검색

> 절차·배경 설명 등 서술형 정보. 코드 정의 조회에는 사용 금지(→ lookup).

**description 초안:** "매뉴얼 본문에서 점검 절차, 배선, 설치 조건 등 서술형 정보를 검색한다. 에러코드 정의 자체는 lookup_error_code를 사용할 것. model 필터 필수."

```json
// input
{ "model": "iG5A | S100", "query": "OCt 출력측 지락 점검 절차", "top_k": 3 }
// output
{
  "status": "ok",
  "chunks": [
    { "text": "...", "page": 212, "section": "6.3 보호기능" }
  ]
}
```

## 3. get_error_history — 에러 이력 조회 (확정 기능 ①)

```json
// input (전부 optional, 최소 1개)
{ "equipment_id": "INV-L3-01", "line_id": 3, "code": "OCt", "days": 30 }
// output
{
  "status": "ok",
  "count": 3,
  "repeated": true,            // count >= threshold(3) 이면 true
  "events": [
    { "date": "2026-07-01", "code": "OCt", "action_taken": "리셋", "part_replaced": null }
  ]
}
// repeated=true → 에이전트는 근본원인 모드로 전환해야 함 (S3)
```

## 4. search_inventory — 재고 조회

```json
// input (둘 중 하나)
{ "part_no": "FAN-IG5-01", "part_name": "냉각팬" }
// output
{
  "status": "ok",
  "items": [
    { "part_no": "FAN-IG5-01", "name": "냉각팬", "qty": 1,
      "safety_stock": 3, "location": "자재창고 A-12",
      "compatible_models": ["iG5A"],
      "discontinued": false }        // ★ 단종 여부 (D20) — S2 분기 판단 근거
  ]
}
// qty == 0 또는 discontinued == true → S2 분기 (find_alternative_parts 호출)
// qty < safety_stock → 부족분 포함 발주 제안
```

## 5. find_alternative_parts — 호환 대체품 검색

**description 초안:** "재고가 없거나 단종된 부품의 호환 대체품을 조회한다. compat_confirmed가 false인 부품은 사용자에게 제안하지 말 것."

```json
// input
{ "part_no": "PCB-S100-CTRL" }
// output
{
  "status": "ok",
  "alternatives": [
    { "part_no": "PCB-S100-CTRL-R2", "compat_confirmed": true,
      "note": "동일 사양 후속 리비전" }
  ]
}
// status: "empty" → 긴급 견적 + 에스컬레이션 분기 (S2 서브)
```

## 6. get_supplier_quotes — 공급사 견적 조회 (리드타임+단가+MOQ 통합)

```json
// input
{ "part_no": "FAN-IG5-01", "qty": 2 }
// output
{
  "status": "ok",
  "suppliers": [
    { "supplier_id": "SUP-A", "name": "A사", "lead_days": 3,
      "unit_price": 38000, "moq": 1 },
    { "supplier_id": "SUP-B", "name": "B사", "lead_days": 14,
      "unit_price": 29000, "moq": 10 }
  ]
}
// 2개 이상이면 비교 제시 후 사용자 선택 (에이전트 단독 결정 금지)
```

## 7. create_po_draft — 발주서 초안 생성 ⚠️ 유일한 쓰기 도구

**description 초안:** "발주서 '초안'을 생성한다. 확정이 아니다. 반드시 사용자가 부품·공급사를 확인한 후에만 호출할 것. reason에는 진단 근거를 요약해 남길 것."

```json
// input
{
  "part_no": "FAN-IG5-01",
  "qty": 2,
  "supplier_id": "SUP-A",
  "reason": "iG5A OHt 3회 반복, 냉각팬 고장 진단 (매뉴얼 p.208)",  // required
  "urgency": "urgent | normal"
}
// output
{ "status": "ok", "po_id": "PO-0117", "state": "draft" }
// state는 draft 고정. approved/rejected 전환은 승인 큐 API(사람)만 가능
// requested_by·session_id는 도구 파라미터가 아님 — 백엔드가 X-User 헤더·세션에서 서버 측 주입 (D23)
//   → 도구 스키마에 신원 필드가 없으므로 LLM이 신원을 위조할 경로 자체가 차단됨
```

---

## 설계 결정 기록

| # | 결정 | 이유 |
|---|------|------|
| 1 | 에러코드 조회를 룩업/RAG로 이원화 | exact match 문제에 RAG를 쓰면 오히려 부정확. 문제 성격별 도구 분리 |
| 2 | 실패를 status로 반환 | 예외 대신 구조화 반환 → 에이전트가 S2/S4 분기 가능 |
| 3 | get_lead_time을 get_supplier_quotes로 흡수 | 리드타임·단가·MOQ는 항상 함께 필요. 호출 2회 → 1회 |
| 4 | 쓰기 도구는 draft만 생성 | human-in-the-loop을 도구 권한 수준에서 강제 |
| 5 | reason 파라미터 필수화 | 발주서마다 진단 근거가 남아 승인자가 추적 가능 (화면 B 근거 카드의 데이터 소스) |
| 6 | lookup 출력에 related_parts, inventory 출력에 discontinued 포함 | 진단→부품 특정을 데이터 기반으로, 단종 분기를 계약 수준에서 지원 (D20) |
| 7 | 신원(requested_by)은 도구 파라미터가 아닌 서버 주입 | LLM 신원 위조 경로 차단 (D23) |

## 도구 ↔ 시나리오 매핑

| 시나리오 | 호출 시퀀스 |
|---|---|
| S1 해피패스 | lookup → rag_search → search_inventory → get_supplier_quotes → create_po_draft |
| S2 재고 없음 | search_inventory(qty=0) → find_alternative_parts → get_supplier_quotes → create_po_draft |
| S3 반복 고장 | lookup → **get_error_history(repeated)** → rag_search(근본원인) → 발주 보류 |
| S4 미지 코드 | lookup(**not_found**) → 추측 금지 → A/S 안내 |

## 다음 단계
목업 DB 스키마 — 이 도구들이 읽을 테이블: `05_DB_SCHEMA.md` 참조
