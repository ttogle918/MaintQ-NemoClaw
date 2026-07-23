# MCP 도구 스키마 v0.2
설비보전 AI 에이전트 · **읽기 도구 6종 + 쓰기 도구 1종 = 총 7종**
(읽기 도구는 D8로 7→6종 — `get_lead_time`을 `get_supplier_quotes`에 흡수. 쓰기 1종을 더해 총계는 7종)

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
  "manual_page": 202                 // PDF 물리 페이지 (D26). iG5A 보호기능 표 = p.202~204
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
    { "text": "...", "page": 204, "section": "12.2 고장 대책" }
  ]
}
```

## 3. get_error_history — 에러 이력 조회 (확정 기능 ①)

```json
// input (전부 optional, 최소 1개)
{ "equipment_id": "INV-L3-01", "line_id": 3, "code": "OCt", "days": 30 }
// days 미지정 시 기본값 30 (상수 REPEAT_WINDOW_DAYS)
// line_id는 error_history에 없는 컬럼 — equipment 조인으로 해석
// output
{
  "status": "ok",
  "count": 3,
  "repeated": true,            // count >= REPEAT_THRESHOLD(3) 이면 true. 두 상수는 도구 모듈에 고정
  "events": [
    { "date": "2026-07-01", "code": "OCt", "action_taken": "리셋", "part_replaced": null }
  ]
}
// repeated=true → 에이전트는 근본원인 모드로 전환해야 함 (S3)
```

## 4. search_inventory — 재고 조회

**description 초안:** "부품의 재고·안전재고·단종 여부를 조회한다. part_no를 알면 part_no로, 사용자가 부품을 이름으로만 말했으면 part_name으로 조회할 것. **part_name으로 조회할 때는 model을 반드시 함께 지정**할 것 — 지정하지 않으면 다른 기종 부품이 섞여 나온다."

```json
// input (part_no·part_name 중 최소 1개 + model optional 필터 — D28)
{ "model": "iG5A | S100", "part_no": "FAN-IG5-01", "part_name": "냉각팬" }
// model 지정 시 parts.compatible_models에 해당 기종이 없는 부품은 결과에서 제외 (D28)
// part_no로 조회할 때는 part_no가 유일키이므로 model 생략 가능 (S1 경로)
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

**description 초안:** "부품의 공급사별 리드타임·단가·MOQ를 조회한다. 2개 이상이면 비교해 제시하고 사용자가 고르게 할 것(단독 결정 금지). **요청 수량이 어떤 공급사의 moq에 미달하면 그 사실을 견적 제시 단계에서 먼저 알릴 것** — MOQ 미달 상태로 발주 초안을 만들면 도구가 거부한다 (D31)."

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

**description 초안:** "발주서 '초안'을 생성한다. 확정이 아니다. 반드시 사용자가 부품·공급사를 확인한 후에만 호출할 것. reason에는 진단 근거를 **한 줄로** 요약하고, evidence에는 **어떤 현상을 보고 고장으로 판단했는지**(symptoms)와 근거가 된 도구 결과(basis), 기타 비고(notes)를 구조화해 남길 것. 에러코드로부터 시작된 진단이면 model·error_code를 함께 넣을 것 — 매뉴얼에 없는 코드는 거부된다. 단가는 파라미터가 아니다(서버가 조회해 채움). 수량이 공급사 MOQ에 미달하면 거부되므로 미달이면 먼저 사용자에게 수량 조정을 확인할 것."

```json
// input
{
  "part_no": "FAN-IG5-01",
  "qty": 2,
  "supplier_id": "SUP-A",
  "reason": "iG5A OHt 3회 반복, 냉각팬 고장 진단 (매뉴얼 p.202)",  // required — 한 줄 요약
  "urgency": "urgent | normal",

  "model": "iG5A",        // error_code와 항상 짝. 둘 다 optional (D33)
  "error_code": "OHT",    // 대문자 canonical 2~4자. 실재하지 않는 코드는 FK가 거부
                          //   S2처럼 진단 없이 부품만 교체하는 발주는 둘 다 생략

  "evidence": {           // optional — 판단 근거 구조화 (D34). 화면 B 근거 카드의 상세 소스
    "symptoms": ["냉각팬 소음 증가", "3번 라인 2회 정지"],   // 어떤 현상을 보고 판단했는지
    "basis": [                                              // 판단을 뒷받침한 도구 결과
      { "tool": "lookup_error_code", "code": "OHT", "manual_page": 202 },
      { "tool": "get_error_history", "count": 3, "window_days": 30, "repeated": true }
    ],
    "notes": "야간조 정비사 육안 확인 — 팬 회전 불량"        // 자유 비고·기타 상황
  }
}
// output
{ "status": "ok", "po_id": "PO-0117", "state": "draft",
  "unit_price": 38000, "total": 76000 }   // 단가는 supplier_parts SELECT 스냅샷 (D31)
// state는 draft 고정. approved/rejected 전환은 승인 큐 API(사람)만 가능
// requested_by·session_id는 도구 파라미터가 아님 — 백엔드가 X-User 헤더·세션에서 서버 측 주입 (D23)
//   → 도구 스키마에 신원 필드가 없으므로 LLM이 신원을 위조할 경로 자체가 차단됨
//   → 주입 방법(D37): 도구는 신원 없이 INSERT하고, 백엔드가 같은 요청 안에서 stamp한다.
//     stamp는 requested_by가 NULL이고 state='draft'일 때만 1회 — 나중에 요청자를 바꿀 수
//     있으면 감사 추적이 무너지므로 덮어쓰기를 막는다 (backend/services/po.py)
// unit_price도 같은 논리로 파라미터가 아님 — 도구가 supplier_parts에서 조회해 스냅샷 (D31)
//   → LLM이 가격을 지어내 발주서에 적을 경로가 없음

// 매뉴얼에 없는 error_code로 호출 시 (D33) — FK가 거부
{ "status": "error", "reason": "unknown_error_code",
  "message": "iG5A 매뉴얼에서 확인되지 않는 코드입니다 (XY9). 코드 없이 발주하거나 표시부를 재확인하세요." }
// → LLM이 지어낸 코드가 발주 이력에 남을 경로가 없음. S4의 환각 방지가 발주 단계까지 이어짐

// MOQ 미달 시 (D31) — 자동으로 수량을 올리지 않는다
{ "status": "error",
  "reason": "moq_not_met",
  "message": "SUP-B의 최소 발주 수량은 10개입니다 (요청 2개). 수량을 조정하거나 다른 공급사를 선택하세요.",
  "moq": 10, "requested_qty": 2 }
// → 에이전트는 사용자에게 재확인. 임의 상향은 사람 승인 없이 발주 금액을 키우는 것이라 금지
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
| 8 | `search_inventory`에 model optional 필터 | part_name 자연어 조회(S2 진입)에서 기종 교차 오염 차단 (D28) |
| 9 | 단가도 도구 파라미터가 아닌 서버 조회 스냅샷 | 7과 같은 논리 — LLM이 가격을 지어낼 경로 차단 (D31) |
| 10 | MOQ 미달은 자동 상향이 아니라 거부 | 사람 승인 없이 발주 금액을 키우지 않음 (D31) |
| 11 | `(model, error_code)`를 발주서에 기록, FK로 실재 검증 | 발주↔에러코드 추적 + 지어낸 코드 차단 (D33) |
| 12 | `evidence` JSON — 관찰 현상·근거·비고 | 승인자가 대화를 안 읽고 "왜 지금 이 부품인가"를 판단 (D34) |

## 도구 ↔ 시나리오 매핑

| 시나리오 | 호출 시퀀스 |
|---|---|
| S1 해피패스 | lookup → rag_search → search_inventory → get_supplier_quotes → create_po_draft |
| S2 재고 없음 | search_inventory(qty=0) → find_alternative_parts → get_supplier_quotes → create_po_draft |
| S3 반복 고장 | lookup → **get_error_history(repeated)** → rag_search(근본원인) → 발주 보류 |
| S4 미지 코드 | lookup(**not_found**) → 추측 금지 → A/S 안내 |

## 다음 단계
목업 DB 스키마 — 이 도구들이 읽을 테이블: `05_DB_SCHEMA.md` 참조
