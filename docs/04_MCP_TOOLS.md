# MCP 도구 스키마 v0.3
설비보전 AI 에이전트 · **코어 7종(읽기 6 + 쓰기 1) + 확장 14종(읽기 12 + 쓰기 2) = 총 21종**

- 코어 읽기 도구는 D8로 7→6종 — `get_lead_time`을 `get_supplier_quotes`에 흡수. 쓰기 1종을 더해 코어 총계는 7종.
- 확장 도구 §8~§18(11종)은 자산 생애주기(처분·취득·자산가치·수리 증빙·기한/위험 감시) 담당이며 대상이
  **인버터가 아니라 호스트 설비(`assets`)** 다 (**D68**) — 단 `create_repair_record`(§16)는 예외로
  `equipment_id`(인버터) 를 직접 받는다 (D68 ⓑ, 수리는 인버터 단위).
- ⚠ **쓰기 도구는 이제 3종이다** — `create_po_draft`(§7) · **`generate_disposal_document`(§15, Sprint 7 신설)** ·
  **`create_repair_record`(§16, Sprint 9 신설, D98)**. 셋 다 draft INSERT 만 하며 UPDATE 권한이 없다
  (D10·D81·D98). 확장 도구에 쓰기가 하나도 없다는 이 문서의 옛 서술은 **거짓이 됐고 아래에서 정정했다**
  (실측: `mcp_server/server.py`).
- **`track_deadlines`(§17)·`assess_risk_grade`(§18)는 Sprint 11 신설 읽기 전용 도구다**(D102) — 기한·사고·
  위험 감시 계층의 사전 경보/실사 보존 확장이며, 어느 것도 쓰지 않는다.
- **`search_insurance_clause`(§19)·`assess_equipment_loan`(§20)는 Sprint 16 신설 읽기 전용 도구다**(D112) —
  자산 생애주기가 아니라 **A2A 외부 파트너**(InsuQ·FinAllQ) 응답 중계다. `mcp_server` → `backend` REST
  왕복이라는 앞의 11종과 다른 구조를 쓰며(§8~§18 처럼 `data/` 를 직접 import 하지 않는다, D15 유지),
  대상도 `asset_id`/`equipment_id` 가 아니라 자유 질의(`question`)·대출 조건이다.

### 프로파일 게이트 (D69)

도구 노출은 `MAINTQ_TOOLS_PROFILE` 환경변수가 결정한다.

| 프로파일 | 등록 도구 | 비고 |
|---|---|---|
| `core` | 코어 7종 (§1~§7) | **기본값** |
| `full` | 코어 7 + 확장 14 = 21종 (§1~§21) | `MAINTQ_TOOLS_PROFILE=full` 로 명시할 때만 |

> **실측** — `mcp_server/server.py` 의 `if TOOLS_PROFILE == "full":` 블록 안에 `@mcp.tool` 이
> **13개**다: `check_disposal_blockers`·`verify_ownership`·`classify_part_criticality`·
> `get_maintenance_metrics`·`classify_expenditure`·`assess_repair_value`·`build_evidence_bundle`·
> `generate_disposal_document`·**`create_repair_record`**(Sprint 9, D98)·**`track_deadlines`**·
> **`assess_risk_grade`**(Sprint 11, D102)·**`search_insurance_clause`**·**`assess_equipment_loan`**
> (Sprint 16, D112). `spikes/tools_profile_contract.py` 가 양방향으로 잠근다.

- **기본이 `core` 인 이유**: `eval/run_eval.py` 가 부모 env 를 상속해 MCP 서버를 띄우므로(D56), 기본이 `full` 이면 평가가 아무 표시 없이 확장 프롬프트로 돈다 — "수정 효과 vs 도구 증가 효과"가 영원히 분리되지 않는다.
- **enum 밖 값은 폴백하지 않고 죽는다.** 조용히 `core` 로 떨어지면 "어느 프로파일로 돌았는지 모르는 실행 결과"가 남는다.
- **시스템 프롬프트는 이 env 를 읽지 않는다.** 루프가 `client.list_tools()` 로 받은 **실제 도구 목록**으로 프롬프트를 조립한다(`build_system_prompt(tool_names=…)`) — 등록은 자식 프로세스(MCP), 프롬프트는 백엔드가 만들므로 같은 env 를 각자 해석하면 어긋난다. `GET /health` 는 등록 개수 실측치를 싣고 `tools_profile` 은 참고값으로만 둔다.
- **확장 도구는 사람용 REST 의 전제가 아니다.** `POST /api/assets/{id}/disposal/precheck`(§06 §2.5)는 `data.rules.engine` 을 직접 쓰므로 `core` 프로파일에서도 살아 있다 (D73).

---

## 공통 설계 원칙

1. **description이 오케스트레이션의 절반이다.** 각 도구 설명에 "언제 사용 / 언제 사용 금지"를 명시한다. LLM의 도구 선택 품질은 스키마 설명 품질에 비례한다.
   → 확장 13종의 `DESCRIPTION` 은 **각 도구 파일의 `DESCRIPTION` 상수가 정본**이다. 이 문서는 그것을 인용할 뿐 두 벌로 관리하지 않는다.
2. **실패도 구조화된 결과로 반환한다.** 예외를 던지지 않고 `status` 필드로 반환해 에이전트가 분기(S2, S4)할 수 있게 한다. `status: "ok" | "not_found" | "empty" | "error"`
3. **읽기/쓰기 도구를 분리한다.** 쓰기 도구는 **3종**(`create_po_draft` §7 · `generate_disposal_document` §15 · `create_repair_record` §16)이며 **셋 다 draft INSERT 만** 한다. 확정은 승인 큐(사람)에서만.
   - `build_evidence_bundle`(§14)은 **여전히 아무것도 쓰지 않는다** — 읽기 전용 커넥션만 갖는다(`build_evidence_bundle.py:320` `with read_only()`). 그러나 §15·§16 은 각각 `decisions`·`repair_records` 에 `state='draft'` 한 행을 INSERT 한다 (D81·D98).
   - 권한은 규율이 아니라 **커넥션이 잠근다**: `db.decision_writer()`·`db.repair_writer()` 의 TEMP TRIGGER 2개가 각각 `decisions`·`repair_records` UPDATE/DELETE 를 거부한다. §15·§16 은 `po_drafts` 전용인 `draft_writer()` 를 재사용하지 않는다(`generate_disposal_document.py:10-13`·`create_repair_record.py`).
4. **model은 명시 파라미터.** enum으로 강제해 "같은 코드, 다른 의미" 오염을 스키마 수준에서 차단.
5. **필수 파라미터에는 기본값을 두지 않는다 (D80).** 인자 누락은 도구 코드가 아니라 **MCP 스키마 검증(pydantic)이 앞단에서** 막는다 — 기본값을 두면 FastMCP 가 `required` 를 빼서 optional 로 노출하고, LLM 이 인자 없이 호출 → `invalid_input` → 재시도하는 낭비 루프가 생긴다. D9 는 **도구 로직의 실패**에 대한 규칙이지 호출 규약 위반에 대한 규칙이 아니다.
   ⚠ **예외 — either-or 파라미터**: "`asset_id` 또는 `equipment_id` 중 하나 필수"는 JSON Schema 로 표현되지 않는다. 그래서 해당 도구는 **둘 다 optional 로 두고 `DESCRIPTION` 이 그 사실을 말한다**(5종: `check_disposal_blockers`·`verify_ownership`·`get_maintenance_metrics`·`build_evidence_bundle`·`assess_risk_grade`(§18, `building_id`/`asset_id` 짝, Sprint 11)).
6. **확장 도구 §8~§18(11종)은 "모른다"를 값으로 표현한다.** 출력에 `disclaimer`(추정치·목업 고지)가 **항상** 실리고, 산출 불가는 `null` / `"insufficient_data"` / `UNVERIFIED` 로 남긴다. 0 이나 `"stable"` 로 메우지 않는다 (`11 §4` 불변식 6 · D62 · D65). ⚠ `not_considered[]` 은 §8~§14(읽기 도구)의 관행이다 — 쓰기 도구 §15·§16 은 이 필드를 싣지 않는다(승인 문서·수리 증빙은 "무엇을 안 봤는가"보다 "무엇을 확정했는가"가 우선이라 `disclaimer`·`expenditure_reason`/`documents_preview` 로 대신한다). ⚠ **§19·§20(신규 A2A 도구 2종, D112)은 이 규약 밖이다** — 외부 파트너(InsuQ·FinAllQ) 응답을 그대로 중계하는 구조라 `disclaimer`·`not_considered` 필드가 없다. 대신 확답을 못 받으면 `status:"error"` + `reason` 으로 "모른다"를 표현한다(D112).

---

## 1. lookup_error_code — 에러코드 정확 조회 (룩업)

> 구조화 추출된 에러코드 표에서 exact match. RAG 아님.

**description 초안:** "인버터/PLC 에러코드의 공식 정의·원인·조치를 조회한다. 에러코드가 명확할 때 가장 먼저 사용. 코드가 표에 없으면 not_found를 반환하며, 이때 유사 코드를 추측하지 말 것."

```json
// input
{
  "model": "iG5A | S100 | IE5",     // enum, required (D109)
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
{ "model": "iG5A | S100 | IE5", "query": "OCt 출력측 지락 점검 절차", "top_k": 3 }
// output
{
  "status": "ok",
  "chunks": [
    { "text": "...", "page": 204, "section": "12.2 고장 대책" }
  ]
  // text 는 절단하지 않는다 (D53) — 길이 제한은 청킹 단계(MAX_CHARS=900)에서 이미 걸려 있다.
  //   중간에서 끊긴 절차 문단은 에이전트가 뒷부분을 지어낼 여지를 만든다 (환각률 0% 지표)
  // page 는 PDF 물리 페이지 무가공 (D26) — 인용률 판정이 이 값을 traces 와 대조한다
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
{ "model": "iG5A | S100 | IE5", "part_no": "FAN-IG5-01", "part_name": "냉각팬" }
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

## 7. create_po_draft — 발주서 초안 생성 ⚠️ 쓰기 도구 ①/2 (다른 하나는 §15)

**description 초안:** "발주서 '초안'을 생성한다. 확정이 아니다. 반드시 사용자가 부품·공급사를 확인한 후에만 호출할 것. reason에는 진단 근거를 **한 줄로** 요약하고, evidence에는 **어떤 현상을 보고 고장으로 판단했는지**(symptoms)와 근거가 된 도구 결과(basis), 기타 비고(notes)를 구조화해 남길 것. 에러코드로부터 시작된 진단이면 model·error_code를 함께 넣을 것 — 매뉴얼에 없는 코드는 거부된다. 단가는 파라미터가 아니다(서버가 조회해 채움). 수량이 공급사 MOQ에 미달하면 거부되므로 미달이면 먼저 사용자에게 수량 조정을 확인할 것."

> **이 도구의 계약(입출력·검증 규칙)은 D111 이후에도 무변경이다** — 다만 산출 로직(단가
> 스냅샷·MOQ 거부·에러코드 FK 검증)이 `data/po_draft.py` 공유 계층으로 옮겨졌고, 화면
> 경로(`POST /api/po`·`06_REPO_API.md §2.2`)가 이제 **같은 검증**을 거쳐 발주 초안을
> 만들 수 있다(P39 축소판 — 발주서만, D73·D101 패턴). 채팅 경로는 폐지되지 않고 병행한다.

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

# 확장 도구 §8~§18 (11종, 프로파일 `full` 에서만 등록 — D69)

> **대상이 다르다.** §1~§7 은 인버터(`equipment_id`)를 본다. §8~§14 는 인버터가 구동하는
> **호스트 설비(`asset_id`)** 를 본다 (**D68**). `equipment_id` 로 불러도 되지만 그건
> `equipment.asset_id` 로 해석되는 **입력 편의**일 뿐, 판정 대상은 언제나 자산이다.
> 호스트 자산이 없는 인버터(`INV-L1-01` 분전반)는 `no_host_asset` 이다 — "판정 결과 문제 없음"이 아니다.
> ⚠ **§16(`create_repair_record`)은 예외다** — 대상이 `asset_id` 가 아니라 **`equipment_id`(인버터)
> 그 자체**다. 수리는 인버터 단위로 남는다 (D68 ⓑ) — `assets` 로 해석·집계하는 건 `get_maintenance_metrics`
> 소관이다.
> ⚠ **§19·§20(신규 2종, Sprint 16, D112)은 이 절 밖이다** — 대상이 자산/설비가 아니라 A2A 외부
> 파트너 응답이라 아래 "공통 규약 4가지"·"대상이 다르다" 서술이 적용되지 않는다. 각 절 서두에서
> 별도로 명시한다.

**공통 규약 4가지 (§8~§14, 원칙적으로 §16 도 D9·D80 은 그대로 따른다)**

1. **읽기 전용.** `read_only()` 커넥션만 쓴다. 쓰기 경로가 코드에 없다 (D10).
   ⚠ **§15·§16 은 이 규약의 예외다** — 둘 다 draft 전용 쓰기 커넥션(`decision_writer()`·
   `repair_writer()`)을 가지며, 그 커넥션에는 UPDATE/DELETE 를 막는 TEMP TRIGGER 2개가 걸려
   "쓰기가 없다"가 아니라 "쓰기가 draft 로 한정된다"로 규약이 바뀐다 (D10·D81·D98).
2. **예외를 던지지 않는다.** 룰 엔진은 `RuleIntegrityError` 말고도 `KeyError`(미등록 법령 참조)·`TypeError`(`trigger` 파손)·`ValueError`(시점 밖 조문)를 던지므로 **광범위하게 포착해** `status:"error"` 로 닫는다 (D9·D46).
3. **`assets` 행을 판정기에 직접 넘기지 않는다.** 반드시 `engine.build_facts()` 를 경유한다 — 이 함수가 **NULL 컬럼의 키를 아예 만들지 않는다.** `dict(row)` 를 그대로 넘기면 NULL 이 "값 있음"으로 읽혀 `INSUFFICIENT_FACTS` 여야 할 자산이 조용히 `CLEAR` 가 된다 (D62). (§16 은 처분 판정기를 부르지 않으므로 이 규약 밖이다.)
4. **enum 은 폴백하지 않는다.** `disposal_mode` 는 `engine.DISPOSAL_MODES`(`SALE|SCRAP|TRANSFER`)가 단일 출처다. `'SELL'` 을 `'SALE'` 로 고쳐 주면 오타 하나가 `VAT-INVOICE` 트리거를 빗나가 `CONDITIONAL` 을 `CLEAR` 로 만든다. §16 의 `work_type`·`repair_scope`·`model` 도 같은 태도로 폴백하지 않는다.

---

## 8. check_disposal_blockers — 자산 처분의 법정 조건 판정 (S9 진입점)

**description (코드 정본 = `mcp_server/tools/check_disposal_blockers.py:DESCRIPTION`):**
> "설비 자산의 처분(매각·폐기·이전) 가능 여부를 법정 조건으로 판정한다. 처분·매각·폐기 이야기가 나오면 가장 먼저 호출할 것. 판정은 조문 근거와 함께 나오며, BLOCKED 면 처분을 진행하지 말고 해소 경로를 안내할 것. HOLD·INSUFFICIENT_FACTS 를 '문제 없음'으로 해석하지 말 것 — 각각 경계 구간과 사실 부족이다. 이 도구는 판정만 한다. 처분 확정은 사람의 서명으로만 이뤄진다."

```json
// input — asset_id · equipment_id 중 최소 1개 (원칙 5 either-or)
{
  "asset_id": "AST-L3-LIFT",      // optional
  "equipment_id": "INV-L3-01",    // optional — equipment.asset_id 로 해석 (D68)
  "disposal_mode": "SALE",        // optional, 기본 "SALE". enum SALE|SCRAP|TRANSFER
  "disposal_date": "2026-09-01"   // optional, ISO 날짜. 판독 불가면 invalid_input —
                                  //   모르는 날짜를 오늘로 대체하지 않는다 (D62)
}
// output
{
  "status": "ok",
  "asset_id": "AST-L3-LIFT",
  "evaluated_at": "2026-08-09",
  "verdict": "CONDITIONAL",       // ★ 5종 (D79) — 아래 표
  "blockers":      [ … ],         // 4버킷. 각 항목은 engine.Finding 의 dict
  "preconditions": [ … ],
  "holds":         [ … ],
  "insufficient":  [ … ],
  "disposal_mode": "SALE",        // 판정 조건을 결과에 되싣는다 — 같은 자산도 mode·날짜로
  "disposal_date": null,          //   판정이 갈리므로 이 둘 없이는 결과를 재현할 수 없다
  "evidence_completeness": "LAW_TEXT_PENDING",   // COMPLETE | LAW_TEXT_PENDING
  "not_considered": ["생산 계획·대체 설비 확보 여부", "시장 상황 및 매각 타이밍", "개별 계약의 특약 조항"],
  "disclaimer": "본 판정은 통상 사례 기준 목업 룰에 근거한다. … 인용 조문의 원문은 아직 수집되지 않았으며 인용은 조문 번호·제목 기준이다."
}
```

**버킷 항목(`engine.Finding`)의 필드** — 4버킷 공통:
`rule_id` · `label` · `verdict`(`TRIGGERED|HOLD|CLEAR|INSUFFICIENT_FACTS`) · `disposal_type`(`BLOCKING|PRECONDITION|AUTO_CLOSE`) · `citations[]` · `law_refs[]` · `message` · `resolve_options[]` · `reasoning` · `requires_expert_review` · `rule_version` · `missing_facts[]`

### verdict 5종과 우선순위 (D79)

```
blockers > holds > insufficient > preconds > CLEAR
```

| verdict | 뜻 | 사용자가 할 일 | HTTP (D71) |
|---|---|---|---|
| `BLOCKED` | BLOCKING 룰이 발화 | 사유 해소 또는 override(서명·사유 필수) | 409 |
| `HOLD` | 경계 구간(`review_band`) | **전문가 검토** | 409 |
| `INSUFFICIENT_FACTS` | 판정에 필요한 사실이 없음 | **데이터 입력** | 409 |
| `CONDITIONAL` | PRECONDITION 만 발화 | 체크리스트 이행 후 진행 | 200 |
| `CLEAR` | 아무 룰도 발화하지 않음 | 진행 | 200 |

- **`HOLD` 와 `INSUFFICIENT_FACTS` 를 합치면 안 되는 이유는 해소 경로가 정반대이기 때문이다** — 전자는 전문가 검토, 후자는 데이터 입력이다. 우선순위에서 `holds` 가 앞인 이유: 경계에 걸렸다는 건 룰이 **실제로 발화한** 양성 신호이고, 사실 누락은 판정 자체가 성립하지 않은 상태다.
- ⛔ **도구가 우선순위를 재계산하지 않는다.** 계산은 `engine.check_disposal_blockers()` 안에만 있다. 여기서 다시 조립하면 구 4종(`insufficient` 를 `HOLD` 에 흡수)으로 되돌아가는 회귀가 조용히 들어오고 D71 의 HTTP 매핑이 함께 깨진다.

### ★ `CLEAR` 는 `SCRAP`·`TRANSFER` 에서만 나온다 (D78 부수 확정)

`VAT-INVOICE` 는 `disposal_mode == "SALE"` 에서 `vat_invoice_issued=False` 가 **확정 사실**이므로
(precheck 는 거래 성립 전이라 세금계산서가 발행됐을 수 없다) 반드시 발화한다 → 매각 precheck 은
**정의상 최소 `CONDITIONAL`** 이다.

**이건 결함이 아니라 도메인 사실이다.** 실측(시드 9자산, `disposal_date=2026-09-01`):

```
AST-L3-LIFT   SALE=CONDITIONAL   SCRAP=CLEAR   TRANSFER=CLEAR
```

"매각인데 `CLEAR` 가 안 나온다"를 버그로 보고 `VAT-INVOICE` 를 손대면, 세금계산서 발행 의무가
판정에서 사라진다.

### `evidence_completeness` — 값의 원천이 둘이다 ⚠

| 무엇 | 원천 | 이유 |
|---|---|---|
| `verdict`·4버킷·`citations` | **정본 파일** `data/rules/{laws,rules}/*.json` (`engine.check_disposal_blockers()` 가 직접 읽는다) | 계층 1 은 파일이 정본이다 (D60) |
| `evidence_completeness`·룰 카탈로그 적재 게이트 | **DB 사본** (`engine.load_laws_from_db(con)`) | 적재 여부 확인과 `fetch_status` 조회 용도 |

파일과 DB 를 섞어 **판정을 조립하지 않는다.** 두 사본이 어긋나면 `data/seed.py` 자가검증 **⑬** 이 잡는다. ⚠ **`rules` 계층에는 대조 검사가 없다** — 검사 ⑭ 는 `len(rule_rows) == 5` 하드코딩 + 근거 무결성만 보므로 **룰 파일이 6개가 돼도 조용히 통과**한다(⑬ 이 `law_refs` 에서 막으려던 바로 그 시나리오다). D106 · `data/extracted/README.md §3④` 참조.
`LAW_TEXT_PENDING` 판정은 **판정에 실제로 쓰인 룰 카탈로그 전체의 법령 참조**를 본다 — 출력에 드러난 인용만 세면
전 룰이 `CLEAR` 인 자산에서 인용이 0건이 되어 `"COMPLETE"` 가 나오는데, 그건 조문을 수집했다는 뜻이 아니라
아무것도 발화하지 않았다는 뜻이다.

> **현재값 (Sprint 7 MQ-701 실수집 이후)** — 조문 7건 중 **6건 `FETCHED` · 1건 `PENDING`**(`KR-CITA-ENF-31`,
> 제목이 API 값과 불일치해 사람 승인 대기). 처분 룰 5종이 인용하는 조문은 그 6건에 모두 포함되므로
> **실 DB 판정은 `COMPLETE` 가 정상값**이고 `_LAW_PENDING_NOTE` 접미사는 붙지 않는다.
> **위** output 예시 블록의 `LAW_TEXT_PENDING`·disclaimer 접미사는 수집 **전** 상태를 보인 것이다.

**status / reason**

| status | reason | 언제 |
|---|---|---|
| `error` | `invalid_input` | 식별자가 문자열이 아님 / 둘 다 미지정 / `asset_id`·`equipment_id` 가 서로 다른 자산 / `disposal_mode` enum 밖 / `disposal_date` 판독 불가 |
| `error` | `rule_catalog_not_loaded` | `law_refs` 또는 `rules` 가 DB 에 0행. **`not_found` 가 아니다** — 0행을 "조건 없음"으로 주면 모든 자산이 `CLEAR` 로 통과한다 (D50) |
| `error` | `rule_integrity` | 근거 없는 룰이 카탈로그에 있다 (`RuleIntegrityError`, D61) |
| `error` | `engine_error` | **엔진 계약 위반을 명시적으로 확인한 자리에만.** 계약 밖 verdict 반환(`check_disposal_blockers.py:147`) / 계약 키 누락(`:162`). 모르는 판정을 통과로 포장하지 않는다 |
| `error` | `internal_error` | 그 밖의 예외를 `status` 로 닫는 마지막 그물 (`:209`, D9) |
| `error` | `db_error` | `sqlite3.Error`·`OSError` |

> **⚠ 어휘 통일 (MQ-712)** — 이전에는 `except Exception` 그물이 `engine_error` 를 냈고, 같은 실패를
> §14 `build_evidence_bundle` 은 `internal_error` 로 냈다. **같은 실패가 도구마다 다른 이름**이었다
> (§14 가 스스로 경고해 둔 상태 · MQ-705 가 MCP 도구 경유를 끊으면서 생겼다).
> **`internal_error` 로 통일했다.** 이유 둘: ⓐ 그 그물은 엔진 예외만 잡지 않는다(직렬화·타입 오류도
> 걸린다) — `engine_error` 라 부르면 **원인을 단정한 거짓 라벨**이 된다. ⓑ `internal_error` 는 이미
> 프로젝트 공통 어휘다(§9·§10·§12·§13·§14·§15 + `backend/services/ownership.py`).
> `engine_error` 는 **엔진이 계약을 깼음을 실제로 확인한 두 자리**에만 남고, 그 뜻은 §14 와 같다.
> `spikes/bundle_integrity.py ㉒` 가 `KeyError`·`TypeError`·`ValueError` 3종으로 두 도구 어휘 일치를 잠근다
> (뮤턴트로 되돌리면 FAIL 하는 것을 확인했다).
>
> ⚠ **남아 있는 비대칭 1건(고치지 않았다)**: DB 파일 부재를 §14 는 `db_missing`, §8 은 `db_error` 로 낸다
> — §8 에 `except FileNotFoundError` 절이 없어 `OSError` 절이 먼저 잡는다(`:195`). 새 reason 을 §8 계약에
> 추가하는 일이라 **MQ-712 범위 밖**이며, ㉒ 의 대조 대상도 아니다. 고치려면 계약 변경으로 다뤄야 한다.
| `not_found` | `unknown_equipment` | 등록되지 않은 설비 |
| `not_found` | `no_host_asset` | 설비에 연결된 호스트 자산이 없음 (분전반 등). 배전 위치는 거래 단위가 아니다 |
| `not_found` | `unknown_asset` | 등록되지 않은 자산 |

## 9. verify_ownership — 중고 설비 실사 체크리스트 (S18)

**description (코드 정본 = `verify_ownership.py:DESCRIPTION`):**
> "중고 설비를 사거나 팔기 전 실사 체크리스트 9개 카테고리를 판정한다. 권리관계(담보·리스·압류)·정비 이력·법정 요건·시장가 등 '이 설비를 믿고 거래해도 되는가'를 물을 때 호출할 것. 결과는 확인된 것과 확인되지 않은 것을 나눠서 준다. verdict 가 PARTIAL 이면 '대체로 안전'이 아니라 '미확인 항목이 남았다'는 뜻이며, PARTIAL 은 어떤 추가 확인으로도 VERIFIED 로 승격되지 않는다 — 사용자에게 안전하다고 말하지 말고 남은 항목과 계약상 배분(진술보장·특약)을 안내할 것. 이 도구는 외부 기관(등기·국세청)을 조회하지 않는다 — UNVERIFIED 항목을 추측으로 메우지 말 것. asset_id 또는 equipment_id 중 하나는 반드시 넘길 것 — 둘 다 비우면 조회 없이 거부된다. 설비(인버터) 식별자만 알면 equipment_id 로 호출하면 호스트 자산으로 해석된다."

```json
// input — 둘 중 하나 필수
{ "asset_id": "AST-L3-LIFT", "equipment_id": null }
// output
{
  "status": "ok",
  "asset_id": "AST-L3-LIFT",
  "verdict": "PARTIAL",           // VERIFIED | PARTIAL | UNVERIFIED
  "categories": [                 // ★ 항상 9개 전부. "해당 없음"이라고 빼지 않는다 —
    {                             //   빼면 "확인 안 한 것"이 화면에서 사라진다
      "category": "권리관계",
      "items": [
        { "item": "담보 설정 (사내 기록)", "state": "VERIFIED",
          "evidence": "사내 기록상 담보 설정 없음 (assets.has_lien=0)", "limit": null },
        { "item": "리스 여부", "state": "UNVERIFIED",
          "evidence": null, "limit": "원천 없음 — 리스는 동산담보등기 대상이 아니고 …" }
      ]
    }
    // 9종 고정·순서 고정: 물리적 상태 · 가동 이력 · 정비 이력 · 기술적 진부화 ·
    //                     권리관계 · 법정 요건 · 재무·회계 · 시장·가격 · 이전 비용
  ],
  "verified":   ["담보 설정 (사내 기록) — 사내 기록상 담보 설정 없음 (assets.has_lien=0)"],
  "unverified": ["리스 여부 — 원천 없음 — 리스는 동산담보등기 대상이 아니고 …"],
  "residual_risk": "제3자 담보권 존재 가능성 배제 불가 · … · 그 밖 미확인 항목 포함 총 31건 잔존",
  "mitigation":    "매도인 진술보장 + 손해배상 특약으로 계약상 배분 권고 · …",
  "not_considered": [ … 5종 고정 … ],
  "disclaimer": "이 결과는 확인된 것과 확인되지 않은 것을 구분해 보여줄 뿐, 이 자산이 안전하다고 말하지 않는다. …"
}
```

- **`item.evidence` 는 `VERIFIED` 일 때만, `item.limit` 은 `UNVERIFIED` 일 때만 채워진다.** 나머지는 `null`. 이유 없는 미확인은 만들지 않는다.
- **`PARTIAL` 은 승격 경로가 코드에 없다** (`11 §6`). `_verdict()` 는 항목 상태만 보고 호출자는 반환값을 **한 번만 대입**한다 — 이후 어떤 분기도 이 값을 바꾸지 않는다.
- **외부 기관을 런타임에 호출하지 않는다.** 등기·사업자등록·법인등기 항목은 전부 `UNVERIFIED` + "사전 수집 스냅샷 없음"이다. 요청마다 기관을 호출하면 "서명 시점 스냅샷 재현" 전제가 깨진다.
- **`insured` 3상태를 그대로 반영한다 (D78)**: 키 없음(NULL)=모름 → `UNVERIFIED` / `false`=확인된 미부보 → `VERIFIED`(**단 위험은 `residual_risk` 에 남는다**) / `true`=부보 → `VERIFIED`.
- 반복 고장 판정 기준은 `get_error_history` 의 `REPEAT_WINDOW_DAYS`·`REPEAT_THRESHOLD` 를 **재사용**한다 (D2·D29). 같은 현상에 도구마다 다른 문턱을 쓰면 같은 자산이 도구에 따라 다르게 판정된다.

**status / reason**

| status | reason | 언제 |
|---|---|---|
| `error` | `invalid_input` | 식별자가 문자열이 아님 / 둘 다 미지정 |
| `error` | `db_missing` | DB 파일 없음 (`FileNotFoundError`) |
| `error` | `db_error` | `sqlite3.Error` |
| `error` | `internal_error` | 그 밖의 예외 (엔진·파싱). **`ASSET_FACT_COLUMNS` 밖 컬럼을 `facts` 에서 읽으려 하면 가드가 여기로 떨어진다** — 사용자에게 거짓 서술이 가는 것보다 낫다 |
| `not_found` | `unknown_asset` / `unknown_equipment` / `no_host_asset` | §8과 동일 |

## 10. classify_part_criticality — 부품 등급 조회

**description (코드 정본 = `classify_part_criticality.py:DESCRIPTION`):**
> "부품이 핵심 부품(CRITICAL)인지 소모품(CONSUMABLE)인지 조회한다. 수리 여부·지출 성격(자본적/수익적)·잔존가치 판단의 입력이 필요할 때 사용할 것. 이 도구는 등록된 등급을 읽어올 뿐 추론하지 않는다 — 등급이 지정되지 않은 부품은 error(part_class_not_set)를 돌려주며, 이때 부품 이름이나 용도로 등급을 추측하지 말 것. 재고 수량·단가 조회에는 사용 금지(search_inventory·get_supplier_quotes 를 쓸 것). 반환되는 등급은 사람 검수 전 초안(reviewed=false)이므로 단정적으로 서술하지 말 것."

```json
// input — part_no 는 필수 (기본값 없음, D80)
{ "part_no": "FAN-IG5-01" }
// output
{
  "status": "ok",
  "part_no": "FAN-IG5-01",
  "part_class": "CRITICAL",              // CONSUMABLE | CRITICAL
  "basis": "parts.part_class (데이터 조회)",
  "name": "냉각팬 (iG5A 표준)", "category": "냉각",
  "discontinued": false,                 // D20 — 단종 분기 판단 근거
  "reviewed": false,                     // ★ 미검수 초안 플래그 (related_parts 와 같은 성격)
  "note": "part_class 는 미검수 초안",
  "not_considered": [ … 3종 … ],
  "disclaimer": "part_class 는 사람 검수를 거치지 않은 초안이다(reviewed=false). …"
}
```

**추론하지 않는다.** `parts.part_class` 를 그대로 읽어 돌려주는 단순 조회다. 도구가 등급을 추측하면
`assess_repair_value` 의 3지 판단이 근거를 잃는다 — D12 가 `related_parts` 에서 세운 태도의 복제다.

**status / reason**

| status | reason | 언제 |
|---|---|---|
| `error` | `invalid_input` | `part_no` 가 비어 있거나 문자열이 아님 |
| `error` | `part_class_not_set` | 등급 컬럼이 비어 있음. **여기서 추측하면 하류 3지 판단이 근거를 잃는다** |
| `error` | `part_class_invalid` | 등급이 허용값(`CONSUMABLE` \| `CRITICAL`) 밖. "모른다"이지 새 등급이 아니다 |
| `error` | `db_error` / `internal_error` | DB 예외 / 그 밖의 예외 |
| `not_found` | `unknown_part` | 등록되지 않은 부품 번호. **유사 부품번호를 추측해 돌려주지 않는다** |

## 11. get_maintenance_metrics — 자산 보전지표

**description (코드 정본 = `get_maintenance_metrics.py:DESCRIPTION`):**
> "설비 자산의 보전지표(MTBF·MTBF 추세·MTTR·가용도·예방보전 비율·누적 수리비·반복 고장 여부)를 조회한다. 수리할지 교체할지, 매각 시점인지 판단하기 전에 호출할 것. MTBF 는 가동시간이 아니라 달력 기준 평균 고장 간격(일)이며(mtbf_basis 확인), 값이 null 이거나 mtbf_trend 가 insufficient_data 면 **데이터가 부족한 것**이지 '문제 없음'이 아니다 — 그 상태로 좋다/나쁘다를 단정하지 말 것. repeat_failure=true 면 지표 비교보다 근본원인 점검이 먼저다. OEE 는 이 도구가 제공하지 않으며 거래·처분 판정에 쓰지 말 것. 부품 등급은 classify_part_criticality, 개별 에러 이력은 get_error_history 를 쓸 것."

```json
// input — asset_id · equipment_id 중 최소 1개
{ "asset_id": "AST-L3-LIFT", "equipment_id": null, "window_months": 24 }  // 기본 24
// output
{
  "status": "ok",                     // ★ 값이 null·insufficient_data 여도 도구는 성공이다
  "asset_id": "AST-L3-LIFT",          //   (데이터 부족 ≠ 도구 실패)
  "window_months": 24,
  "mtbf_days": 9.4,
  "mtbf_basis": "calendar_days",      // ★ D70 — 가동시간 기준이 아님을 계약 수준에서 고지
  "mtbf_trend": "insufficient_data",  // improving | stable | declining | insufficient_data
  "mttr_hours": null,                 // repair_records.downtime_hours 평균 (서명분만)
  "availability": null,               // MTBF[일] / (MTBF[일] + MTTR[시간]/24)
  "planned_ratio": null,              // PLANNED / (PLANNED + UNPLANNED), 서명분만
  "n_repairs_signed": 0, "n_repairs_unsigned": 0,
  "cumulative_repair_cost": 0, "acquisition_cost": null,
  "cumulative_repair_ratio": null,    // acquisition_cost 없으면 분모를 지어내지 않는다
  "repeat_failure": false,            // ★ 판정은 인버터 단위(D68 ⓑ), 집계는 asset 단위
  "excluded": [                       // 무엇을 계산에서 뺐는가 — 필드로 드러낸다
    "repair_records 에 수리 시각 컬럼이 없어 window_months 로 자를 수 없다 — MTTR·예방보전 비율·누적 수리비는 전 기간 집계다"
  ],
  "not_considered": [ "가동시간·스핀들 시간(원천 없음 — 달력 기준 MTBF 로 대체, D70)", "OEE(거래 판정 사용 금지 — D64)", … ],
  "disclaimer": "MTBF 는 가동시간이 아니라 달력 기준 평균 고장 간격이다(D70). … null 과 insufficient_data 는 '양호'가 아니라 '판단 근거 부족'이다."
}
```

- **MTBF 는 `window_months` 안 이벤트의 인접 간격(일) 평균**이다. 이벤트 2건 미만이면 간격 자체가 없으므로 `null` — 0 으로 채우면 "고장 간격 0일"이라는 최악의 신호가 되고, 큰 수로 채우면 없는 안정성이 생긴다.
- **`mtbf_trend` 는 `window_months` 와 무관하게 최근 12개월 vs 직전 12개월 고정 비교**다. 밴드 ±10%. 어느 한쪽이라도 이벤트 <2건이면 `insufficient_data` — ⛔ `"stable"` 로 대체하지 않는다.
- **OEE 는 계산도 출력도 하지 않는다** (D64). `not_considered` 에 금지 사유만 남긴다.
- 서명되지 않은 수리 레코드는 MTTR·예방보전 비율 **분모에서 전부 제외**하고 그 사실을 `excluded[]` 에 적는다 (`12 §11`).

**status / reason**

| status | reason | 언제 |
|---|---|---|
| `error` | `invalid_input` | 식별자가 문자열이 아님 / 둘 다 미지정 / `window_months` 가 양의 정수가 아님 |
| `error` | `db_error` | DB 예외 / 기준 시각(`datetime('now')`) 해석 실패 |
| `not_found` | `unknown_asset` / `unknown_equipment` / `no_host_asset` | §8과 동일 |

## 12. classify_expenditure — 수선 지출의 자본적/수익적 분류

**description (코드 정본 = `classify_expenditure.py:DESCRIPTION`):**
> "수선·개조 지출을 자본적 지출(CAPITAL)과 수익적 지출(REVENUE)로 분류한다. 수리비를 자산으로 올릴지 당기 비용으로 처리할지, 회계·세무 처리를 물을 때 사용할 것. part_class 는 추측하지 말고 classify_part_criticality 로 먼저 확인해 넣을 것. HOLD 는 실패가 아니라 '경계 사안이라 단정하지 않는다'는 판정이다 — CAPITAL·REVENUE 중 하나로 임의 해석하지 말고 세무 전문가 확인 필요를 그대로 전달할 것. 부품 재고 조회·발주에는 사용 금지(search_inventory·create_po_draft). 이 도구는 판정만 하며 전표 기표·세무 신고를 대신하지 않는다."

```json
// input — part_class·repair_scope·amount 는 필수(기본값 없음, D80). asset_id 만 optional
{
  "part_class": "CRITICAL",     // CONSUMABLE | CRITICAL
  "repair_scope": "OVERHAUL",   // RESTORE | UPGRADE | OVERHAUL | REPLACE_UNIT
  "amount": 8500000,            // 지출 금액(원), > 0
  "asset_id": "AST-L3-LIFT"     // optional — 주면 취득원가 대비 비율(20% 문턱)을 평가한다
}
// output
{
  "status": "ok",
  "verdict": "HOLD",                    // CAPITAL | REVENUE | HOLD
  "asset_id": "AST-L3-LIFT",
  "part_class": "CRITICAL", "repair_scope": "OVERHAUL", "amount": 8500000,
  "basis": "OVERHAUL",                  // 판정표의 어느 칸이 발화했는가
  "law_refs":  ["KR-CITA-ENF-31"],      // 법인세법 시행령 제31조 (즉시상각의제)
  "citations": ["법인세법 시행령 제31조(즉시상각의제)"],
  "reasoning": "오버홀은 통상 내용연수를 연장하는 … 취득원가를 알 수 없어 … 유보(HOLD)로 격상했다 (D62). 세무 전문가 확인이 필요하다.",
  "requires_expert_review": true,       // verdict == "HOLD" 와 동치
  "evidence_completeness": "LAW_TEXT_PENDING",   // COMPLETE | LAW_TEXT_PENDING
  "materiality": {
    "state": "UNKNOWN",                 // NOT_EVALUATED | UNKNOWN | BELOW_THRESHOLD | AT_OR_ABOVE_THRESHOLD
    "acquisition_cost": null, "ratio": null, "threshold": 0.2, "escalated": true
  },
  "evaluated_at": "2026-08-09",
  "not_considered": [ … 5종 … ],
  "disclaimer": "통상 사례 기준 목업 판정이다. … 인용한 조문의 원문은 아직 수집되지 않았으며(fetch_status=PENDING) …"
}
```

**판정표 (결정론적, 8조합 전부 명시)**

| repair_scope \ part_class | CONSUMABLE | CRITICAL |
|---|---|---|
| `UPGRADE` | CAPITAL | CAPITAL |
| `OVERHAUL` | CAPITAL | CAPITAL |
| `RESTORE` | REVENUE | **HOLD** (원상 회복 vs 내용연수 연장 — 실무 최대 논쟁) |
| `REPLACE_UNIT` | **HOLD** | **HOLD** (자산 대체로 볼 여지) |

**중요도(materiality) 격상** — `AT_OR_ABOVE_THRESHOLD`(취득원가의 20% 이상) 또는 `UNKNOWN`(취득원가를 모름)이면
기본 판정과 **무관하게 `HOLD` 로 격상**한다. `UNKNOWN` 을 "문턱 미만"으로 처리하지 않는 것이 D62다.
비교는 `Fraction` 정수 교차곱이다 — `amount / cost >= 0.20` 은 거대 정수에서 `OverflowError` 가 나고
0.2 의 이진 부동소수 오차가 문턱 정확히 20% 인 입력의 판정을 흔든다. `materiality.ratio` 는 **표시용**이며
판정 근거는 언제나 `materiality.state` 다.

**근거 검증이 판정보다 먼저다.** `KR-CITA-ENF-31` 이 `law_refs` 에 없으면 판정 자체를 하지 않는다
(D61 · `11 §4` 불변식 2). 다만 **조문 원문이 없다고 판정을 막지는 않는다** — 인용은 조문 번호·제목
기준이고 참조 무결성은 참조 대상의 존재로 이미 보장되므로, `evidence_completeness` 로 사실만 드러낸다.

⛔ 판정 규칙을 `data/rules/rules/` 에 두지 않는다 — 그 디렉토리는 **처분 플래그 전용**이고
(`disposal_type` 필수) `check_disposal_blockers` 가 디렉토리 전체를 로드하므로 지출 판정 룰을 넣으면
처분 판정에 섞여 들어간다.

**status / reason**

| status | reason | 언제 |
|---|---|---|
| `error` | `invalid_input` | `part_class`·`repair_scope` enum 밖 / `amount` 가 정수 아님·≤0 / `asset_id` 가 빈 문자열 |
| `error` | `law_ref_missing` | `KR-CITA-ENF-31` 이 `law_refs` 에 미등록. **근거 없는 지출 판정은 하지 않는다** (D61) |
| `error` | `law_not_effective` | 판정 시점에 유효한 조문이 없음. 조용히 최신본으로 대체하지 않는다 (`11 §4` 불변식 5) |
| `error` | `db_error` / `internal_error` | DB 예외 / 그 밖의 예외 |
| `not_found` | `unknown_asset` | `asset_id` 를 줬는데 등록되지 않은 자산 |

## 13. assess_repair_value — 수리 / 교체 / 현상매각 3지 판단 (S1+)

**description (코드 정본 = `assess_repair_value.py:DESCRIPTION`):**
> "고장 난 설비를 수리할지, 교체할지, 수리 없이 현상 매각할지를 판단한다. 수리비를 알고 있고 '고쳐 쓰는 게 나은가'를 물을 때 호출할 것. verdict 가 ROOT_CAUSE_FIRST 면 3지 선택지 자체가 없다 — 같은 고장이 반복되고 있다는 뜻이므로 수리·교체·매각 중 무엇도 권하지 말고 근본원인 점검을 먼저 안내하고 발주는 보류할 것. HOLD 는 '문제 없음'이 아니라 시장가를 산출할 원천이 없어 판단을 유보한 것이다 — 금액을 추정해 메우지 말 것. market_value_before·market_value_after·value_recovery 는 목업 잔가곡선 기반 추정치이며 실거래가가 아니다(estimates 참조) — 사용자에게 확정 금액처럼 말하지 말 것. repair_cost 는 이 도구가 검증하지 않는다. 부품 단가·리드타임은 get_supplier_quotes, 재고는 search_inventory, 지출의 세무 성격은 classify_expenditure 를 쓸 것. 처분 가능 여부(법정 조건)는 이 도구가 아니라 check_disposal_blockers 소관이다."

```json
// input — equipment_id·failed_part·repair_cost 필수(기본값 없음, D80), repair_scope 만 optional
{
  "equipment_id": "INV-L3-01",     // ★ 인버터를 받아 equipment.asset_id 로 해석한다 (D68)
  "failed_part": "FAN-IG5-01",
  "repair_cost": 8500000,          // > 0. 이 도구는 적정성을 검증하지 않는다
  "repair_scope": "RESTORE"        // optional, 기본 "RESTORE". RESTORE|UPGRADE|OVERHAUL|REPLACE_UNIT
}
// output
{
  "status": "ok",
  "asset_id": "AST-L3-CONV", "equipment_id": "INV-L3-01",
  "failed_part": "FAN-IG5-01", "part_class": "CRITICAL",
  "repair_cost": 8500000, "repair_scope": "RESTORE", "evaluated_at": "2026-08-09",
  "book_value": 40000000,
  "mtbf_trend": "insufficient_data", "repeat_failure": true,
  "cumulative_repair_ratio": 0.175, "parts_eol_flag": false,

  "age_years": 12, "age_bucket": "11-15", "residual_ratio": 0.29,   // ROOT_CAUSE_FIRST 분기에는 없음
  "market_value_before": null, "market_value_after": null,
  "value_recovery": null, "recovery_ratio": null,

  "verdict": "ROOT_CAUSE_FIRST",   // REPAIR_RECOMMENDED | REPLACE_RECOMMENDED | SELL_AS_IS | ROOT_CAUSE_FIRST | HOLD
  "reasoning": "직전 30일 안에 같은 설비에서 고장이 3회 이상 반복됐다. …",
  "alternatives": [],              // ★ ROOT_CAUSE_FIRST 에서는 빈 배열이 계약이다
  "estimates":   [],               // 값이 있는 추정 필드의 이름만 나열 (D65 — 문장이 아니라 필드로 고지)
  "assumptions": [],               // 잔가율·회복 계수의 출처·성격
  "not_considered": [ … 8종 + 분기별 추가 … ],
  "disclaimer": "시장가는 법정 기준내용연수 기반 목업 잔가곡선(D74) 추정치이며 실거래가가 아니다. …"
}
```

### ★ 판정 순서가 계약이다

```
0. repeat_failure == true                       → ROOT_CAUSE_FIRST   (다른 계산 전에 즉시 닫는다)
──────────────────────────────────────────────── 이하 _decide()
1. market_value_before is null                  → HOLD
2. parts_eol_flag == 1                          → REPLACE_RECOMMENDED
   cumulative_repair_ratio >= 0.5               → REPLACE_RECOMMENDED
3. mtbf_trend == "declining" ∧ repair_cost > market_value_after
                                                → SELL_AS_IS
4. recovery_ratio >= 1.0                        → REPAIR_RECOMMENDED
5. 어느 규칙도 발화하지 않음                     → HOLD
```

- **0번이 최우선인 이유**: 3지 선택지를 함께 주면 에이전트가 그중 하나를 고른다. 그래서 시장가·회복분을 **계산조차 하지 않고** `alternatives: []` 로 닫는다. S3 발주 보류(`po_card` variant `hold`, D35)가 그대로 적용된다 (D2 · `12 §11`).
- **1번이 2번보다 앞인 이유** ⚠ — 잔가 원천이 없는 상태에서 "교체하라"고 권하는 것도 근거 없는 판단이다. 이 순서 덕분에 **`residual_curve` 를 비우면 전 자산이 `HOLD`** 가 된다 — "값을 지어내지 않는다"의 기계적 증명이다. 반대 순서면 `residual_curve` 를 비웠을 때 도구가 값을 지어낸다.
- **2번이 회복 계산보다 앞인 이유**: 부품이 EOL 이면 이번 수리가 회수되더라도 다음 고장에서 부품을 구할 수 없다.
- **3과 4는 상호배타다** — 회복분 ≥ 수리비이면 수리비가 회복 후 시장가를 넘을 수 없다.
- **5번에서 새 verdict 를 만들거나 가까운 쪽으로 반올림하지 않는다.** 규칙이 침묵한 것을 결론으로 바꾸면 그게 지어내기다.

**시장가 산출 (D65·D74)** — `market_value_before = acquisition_cost × residual_ratio`.
`residual_curve` 는 **법정 기준내용연수 기반 목업 정률법 산출물**이고 실거래 데이터가 아니다.
연차 격자(`0-2/3-5/6-10/11-15/16-20/21-30`) 밖이거나 행이 없거나 `acquisition_cost` 가 NULL 이면
`null` → `HOLD`. ⛔ **인접 버킷으로 보간하지 않는다.**
회복분은 `CRITICAL` 부품 교체에만 적용하고 계수(`RESTORE 0.10 / REPLACE_UNIT 0.15 / UPGRADE 0.20 / OVERHAUL 0.25`)는
**계측이 아니라 코드 상수**다 — `assumptions[]` 로 고지한다. ⚠ 목업 곡선은 전 카테고리 값이 동일해
**`category` 는 조인 키일 뿐 판정에 영향을 주지 않는다.**

**하위 도구 실패를 삼키지 않는다.** `classify_part_criticality`·`get_maintenance_metrics` 중 하나라도
`status != "ok"` 면 그 `status`·`reason` 을 **그대로 전파**한다(§10·§11의 reason 이 그대로 나올 수 있다).
기본값으로 진행하면 없는 근거로 3지 판단을 하게 된다.

**status / reason**

| status | reason | 언제 |
|---|---|---|
| `error` | `invalid_input` | `equipment_id`·`failed_part` 가 빈 문자열 / `repair_cost` ≤ 0·해석 불가 / `repair_scope` enum 밖 (폴백 금지 — 모르는 scope 를 RESTORE 로 접으면 회복 계수가 조용히 바뀐다) |
| `error` | `db_error` | DB 예외 / 기준 일자(`date('now')`) 해석 실패 |
| `error` | `internal_error` | 그 밖의 예외 (`ASSET_FACT_COLUMNS` 가드 포함) |
| `not_found` | `unknown_equipment` / `no_host_asset` / `unknown_asset` | §8과 동일 |
| (전파) | §10·§11의 모든 reason | 하위 도구 실패를 그대로 되돌린다 |

## 14. build_evidence_bundle — 처분 판정의 근거 번들 + 해시 (S10 계층 3의 재료)

**description (코드 정본 = `build_evidence_bundle.py:DESCRIPTION`):**
> "처분 판정의 근거(법령 조문·해석 룰·판정에 쓰인 사실)를 하나로 묶고 해시로 고정한다. 매각·폐기 결정을 문서로 남기거나 결재·서명에 올릴 때 호출할 것. asset_id 또는 equipment_id **둘 중 하나는 반드시 넘겨야 한다** (둘 다 비우면 실패한다). 처분 예정일을 알면 disposal_date 를 함께 넘길 것 — 없으면 세액공제 조항이 사실 부족으로 남는다. 이 도구는 판정하지도 저장하지도 않는다. 판정은 check_disposal_blockers 가 하고, 번들의 저장·서명은 사람이 승인 화면에서 한다. law_text_unavailable 로 실패하면 조문 원문이 아직 수집되지 않았다는 뜻이며, '근거가 없다'가 아니라 '근거 원문을 아직 해시할 수 없다'는 뜻이다 — 판정 결과는 check_disposal_blockers 로 그대로 얻을 수 있다."

**번들은 3키가 아니라 5키다 (D83)** — 아래는 코드(`build_evidence_bundle.py:431-445`)와 대조한 실제 스키마다.

```json
// input — §8과 동일한 4개 (asset_id·equipment_id 중 하나 필수)
{ "asset_id": "AST-L3-CONV", "equipment_id": null,
  "disposal_mode": "SALE", "disposal_date": "2026-09-01" }
// output — 아래 값은 **실 DB 실행 결과**다 (해시만 축약)
{
  "status": "ok",
  "asset_id": "AST-L3-CONV",
  "evidence_bundle": {            // ★ 해시 대상은 **이 5키뿐**이다 (D83)
    // ① 4버킷에 실린 findings 의 law_refs **합집합만**. law_ref_id 정렬. 원문은 싣지 않고 해시로만 고정
    "laws": [
      {"law_ref_id": "KR-CIVIL-388", "effective_from": "2026-03-17", "text_hash": "sha256:caf918cb…"},
      {"law_ref_id": "KR-KCC-652",   "effective_from": "2026-07-23", "text_hash": "sha256:48de90a1…"},
      {"law_ref_id": "KR-VAT-32",    "effective_from": "…",          "text_hash": "sha256:…"}
    ],
    // ② 인용된 룰 + rule_hash (W6). (rule_id, rule_version) 정렬
    "rules": [
      {"rule_id": "INSURANCE-NOTIFY", "rule_version": 3, "rule_hash": "sha256:60e726ed…"},
      {"rule_id": "LIEN-CONSENT",     "rule_version": 2, "rule_hash": "sha256:9630e235…"},
      {"rule_id": "VAT-INVOICE",      "rule_version": 2, "rule_hash": "sha256:…"}
    ],
    // ③ **평가된 전 룰** (W7) — 인용되지 않은 CLEAR 룰도 전부 실린다. 정확히 이 4키뿐
    //    (text_hash 를 요구하지 않는다 — 요구하면 미수집 조문 1건이 전 자산의 서명 경로를 잠근다)
    "evaluated": [
      {"rule_id": "INSURANCE-NOTIFY",  "rule_version": 3, "verdict": "TRIGGERED", "law_refs": ["KR-KCC-652"]},
      {"rule_id": "LIEN-CONSENT",      "rule_version": 2, "verdict": "TRIGGERED", "law_refs": ["KR-CIVIL-388"]},
      {"rule_id": "SAFETY-INSPECTION", "rule_version": 2, "verdict": "CLEAR",     "law_refs": ["KR-OSHA-93"]},
      {"rule_id": "TAX-CREDIT-2Y",     "rule_version": 1, "verdict": "CLEAR",     "law_refs": ["KR-STTC-24","KR-STTC-146"]},
      {"rule_id": "VAT-INVOICE",       "rule_version": 2, "verdict": "TRIGGERED", "law_refs": ["KR-VAT-32"]}
    ],
    // ④ 인용된 룰의 contract_refs. contract_ref 정렬. **해시로 고정되지 않는다**
    "contracts": [
      {"contract_ref": "근저당권설정계약서", "text_hash": null, "hash_fixed": false,
       "note": "계약 조항 원문 원천이 저장소에 없다 — 이 근거는 해시로 고정되지 않는다"},
      {"contract_ref": "여신거래기본약관",   "text_hash": null, "hash_fixed": false, "note": "…"}
    ],
    // ⑤ 엔진이 돌려준 facts_used **그대로**. 재조립 금지 (W5). NULL 컬럼은 키 자체가 없다 (D62)
    "facts": {"asset_id": "AST-L3-CONV", "building_id": "BLD-C", "status": "IN_USE",
              "acquired_at": "2020-02-10", "tax_credit_applied": true, "has_lien": true,
              "lien_creditor": "한빛은행 여신부", "insured": true, "policy_id": "POL-2026-FIRE-01",
              "safety_inspection_target": false, "disposal_mode": "SALE",
              "vat_invoice_issued": false, "disposal_date": "2026-09-01",
              "months_since_acquisition": 78}
  },
  "bundle_hash": "sha256:9d1e…",
  "hash_spec": "sha256/nfkc-ws/canonical-json-v1",   // ★ 번들 **밖** (N1) — 아래 설명
  "verdict": "BLOCKED",             // 판정 주체가 낸 값을 그대로 옮긴다 (재계산 금지)
  "not_considered": ["생산 계획·대체 설비 확보 여부", "시장 상황 및 매각 타이밍", "개별 계약의 특약 조항"],
  "built_at": "2026-08-09T05:12:44Z",   // ★ 번들 밖
  "disclaimer": "이 번들은 판정 시점의 근거 스냅샷이며 판정 자체가 아니다. …"
}
```

**5키가 각각 무엇을 막는가**

| 키 | 범위 | 없으면 무엇이 무너지나 |
|---|---|---|
| `laws[]` | 4버킷 findings 의 `law_refs` **합집합만** | `text_hash` 없는 항목이 섞이면 *해시할 사실이 없는 번들*이 된다 → `law_text_unavailable` 게이트 대상 |
| `rules[]` | 인용된 룰 + **`rule_hash`** | 계층 1은 `text_hash` 로 잠겼는데 계층 2가 `rule_version` 숫자로만 잠겨 있었다 — **같은 버전 안에서 룰 본문이 in-place 로 바뀌어도 번들 해시가 그대로**였다 (W6) |
| `evaluated[]` | **평가된 전 룰**의 4키 | CLEAR 자산은 `laws`·`rules` 가 비어 *"근거를 조회한 결과 해당 없음"* 과 *"근거를 아예 안 봤다"* 가 구분되지 않는다 (W7) |
| `contracts[]` | 인용된 룰의 `contract_refs` | 계약 근거가 있었다는 사실 자체가 사라진다. `hash_fixed:false` 로 **고정되지 않았음을 드러낸다** |
| `facts` | 엔진의 `facts_used` **그대로** | 재조립하면 "엔진이 본 값"과 "번들에 실린 값"이 갈린다 (W5 의 facts 축) |

**`rule_hash` 산출 규약** (`build_evidence_bundle.rule_hash()` · `RULE_HASH_FIELDS`)

```python
rule_hash = engine.text_hash(canonical_json({f: getattr(rule, f) for f in RULE_HASH_FIELDS}))
```

`RULE_HASH_FIELDS` 는 **판정에 영향을 주는 16필드**다: `rule_id` · `rule_version` · `label` · `category` ·
`disposal_type` · `source_type` · `law_refs` · `contract_refs` · `interpretation` · `required_facts` ·
`trigger` · `boundary` · `message` · `resolve_options` · `confidence` · `requires_expert_review`.

- ⛔ `authored_by`·`reviewed_at`·`revision_note` 는 **제외**한다. 룰 JSON 에는 있지만 판정 입력이 아닌
  메타데이터라, 넣으면 *"검토자 이름 오타 수정"* 이 서명 검증에서 **근거 변조**로 보고된다.
  셋은 `engine.Rule` dataclass 에도 실리지 않으므로 이 제외는 구조와도 일치한다.
- `bundle_hash` 와 **같은 함수**(`canonical_json` + `engine.text_hash`)를 쓴다. 재구현 금지.

**⛔ `contracts[]` 는 `law_text_unavailable` 검사 대상이 **아니다****

계약 조항은 법제처 수집 대상이 아니다. 검사에 넣으면 `LIEN-CONSENT`(여신거래기본약관 인용)가 걸린
자산의 번들이 **구조적으로 영원히 불가능**해진다 — 수집으로 해소될 수 없는 실패다.
그래서 `_cited_law_ref_ids()` 는 `law_refs` 만 모으고 `contract_refs` 는 건드리지 않는다
(`build_evidence_bundle.py:274-286`).

### `bundle_hash` 산출 규약 (Sprint 7 서명 검증이 **같은 함수를 그대로 써야 한다**)

```python
canonical_json(bundle) = json.dumps(bundle, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
bundle_hash            = engine.text_hash(canonical_json(bundle))   # "sha256:…"
```

네 가지를 **전부** 고정해야 "같은 사실 → 같은 해시"가 성립한다:

1. `sort_keys=True` — dict 는 삽입 순서를 보존하므로, 고정하지 않으면 `facts` 를 만든 순서만 달라도 다른 해시가 난다.
2. `separators=(",", ":")` — 기본 구분자는 `", "`·`": "` 라 공백이 들어간다.
   ⚠ **이건 "두 방어선을 겹쳐 둔 것"이 아니라 필수 규약이다.** `engine.normalize()` 는
   `" ".join(text.split())` 이라 공백을 **지우는 게 아니라 하나로 접는다**(`engine.py:29-32`) —
   즉 구분자 차이(`{"a":1}` vs `{"a": 1}`)는 정규화로 **흡수되지 않는다.**
3. `ensure_ascii=False` — 한글을 `\uXXXX` 로 이스케이프하면 같은 문자열이 두 표현을 갖는다. NFKC 는 이스케이프 시퀀스를 되돌리지 못한다.
4. `engine.text_hash()` **재구현 금지** — NFKC + 공백 정규화가 계층 1 조문 해시와 **같은 규칙**이어야 한다.

⚠ `built_at`·`evaluated_at`·**`hash_spec`** 은 **번들 밖**이다. `built_at` 을 안에 넣으면 같은 사실도
호출할 때마다 해시가 달라져 "근거가 변조되지 않았음"을 증명할 수 없다. **`hash_spec` 을 안에 넣으면
스펙 문자열을 한 글자 고치는 순간 과거 서명이 전부 깨진다**(N1). `not_considered` 도 같은 이유로 밖이다 —
목록 문구가 바뀔 때마다 "근거가 변조됐다"는 오탐이 난다.
⚠ **리스트 4종(`laws`·`rules`·`evaluated`·`contracts`)은 순서가 해시에 영향을 준다.** `sort_keys` 는
리스트를 정렬하지 않으므로 조립 시점에 명시적으로 정렬한다 — `laws`→`law_ref_id`,
`rules`·`evaluated`→`(rule_id, rule_version)`, `contracts`→`contract_ref`. 룰 유일키에 `rule_version` 을
포함하는 이유: 개정본이 공존할 수 있고 **서명은 그때 그 버전에 대해 이뤄진 것**이다 (D60).
⚠ **해시 동일 ≠ 바이트 동일** (N1). 기준은 *NFKC + 공백 정규화 후 동일* 이며, 그 사실을 번들 밖의
`hash_spec` 과 `disclaimer` 로 드러낸다. `spikes/bundle_integrity.py ⑩` 이 전각/연속 공백 변형으로 확인한다.

### 미수집 조문이 하나라도 있으면 **의도적으로 거부**한다

거부 자체는 **설계된 동작**이다 — 원문 없는 근거를 해시하면 해시할 사실이 없는 번들이 나온다.

> **현재값 (MQ-701 실수집 이후)** — 조문 6건이 `FETCHED` 로 채워져 **9자산 × `SALE`/`SCRAP` 18조합이
> 전부 `status:"ok"`, `law_text_unavailable` 0건**이다. 아래 예시는 수집 **전** 응답이며,
> 이 경로는 남은 1건(`KR-CITA-ENF-31`)을 인용하는 룰이 생기거나 조문이 재수집 대기로 돌아갈 때 다시 발화한다.

```json
{ "status": "error", "reason": "law_text_unavailable",
  "message": "인용 조문의 원문이 아직 수집되지 않아 근거 번들을 만들 수 없습니다 (미수집 3건: …)",
  "asset_id": "AST-L3-LIFT",
  "missing_law_refs": ["KR-STTC-146", "KR-STTC-24", "KR-VAT-32"] }
```

`text_hash` 가 null 인 항목을 조용히 넣고 해시하면 **해시할 사실이 없는 번들**이 나온다.
**막는 것은 판정이 아니라 서명용 증빙 생성뿐**이다 — 판정은 `check_disposal_blockers` 가
`LAW_TEXT_PENDING` 으로 정직하게 표시하고 답을 준다.
계약 근거(`contract_refs`, 예: 여신거래기본약관)는 조문이 아니므로 이 검사 대상이 **아니다** —
포함하면 애초에 법제처 수집 대상이 아닌 근거가 영원히 실패를 만든다.

**status / reason**

| status | reason | 언제 |
|---|---|---|
| `error` | `law_text_unavailable` | 인용 조문 중 `is_fetched ∧ text_hash` 를 만족하지 않는 것이 있음. `missing_law_refs[]` 로 이름을 댄다 |
| `error` | **`asset_modified`** | **N2 — 판정 후 번들 조립 사이에 자산 행이 바뀜.** 판정 전·후로 자산 행을 두 번 읽고 `facts` 지문을 대조한다(`:459`). 번들은 *한 시점의 사실*에 대한 서명 재료이므로, 조립 도중 사실이 움직였으면 그 번들은 **어느 시점도 증명하지 못한다** — 조용히 이전 스냅샷으로 해시를 내면 서명이 이미 지난 사실에 걸린다 |
| `error` | `asset_disappeared` | 판정 직후 자산 행을 다시 읽지 못함(외부 재시드 등). 사실 없이 번들을 만들지 않는다 |
| `error` | `invalid_input` | `disposal_mode` enum 밖 / 식별자 비문자열 / 둘 다 미지정 / `disposal_date` 판독 불가. §8 과 **같은 reason·같은 문구**다(`_asset_ref` 공용) |
| `error` | `rule_catalog_not_loaded` | `law_refs` 또는 `rules` 가 DB 에 0행 (D50) |
| `error` | `rule_integrity` | `RuleIntegrityError` (D61) |
| `error` | `engine_error` | **엔진 계약 위반을 확인한 자리.** 계약 키 누락 / 계약 밖 verdict / 인용 룰을 카탈로그에서 못 찾음 / 4버킷↔`evaluated` 재평가 불일치 / `laws_used` ↔ `evaluated` 조문 합집합 불일치 (`:360`·`:367`·`:384`·`:418`·`:425`) |
| `error` | `db_missing` / `db_error` / `internal_error` | DB 파일 없음 / DB 예외 / 그 밖(직렬화·엔진 예외)을 닫는 마지막 그물 |
| `not_found` | `unknown_asset` / `unknown_equipment` / `no_host_asset` | §8 과 동일 (`_asset_ref` 공용) |

> **⚠ "§8 에 위임한다"는 서술은 거짓이었다 — 정정한다 (D82·W5).**
> 이 도구는 **MCP 도구 `check_disposal_blockers` 를 부르지 않는다.** `engine.load_laws_from_db()` 로
> 계층 1·2 사본을 한 번만 읽고 그 객체를 `engine.check_disposal_blockers(facts, laws=…, rules=…)` 에
> **주입**한다(`build_evidence_bundle.py:320-355`). 도구를 경유하면 인용 집합은 *파일 사본* 판정에서,
> `text_hash` 는 *DB 사본* 에서 와 **"판정이 본 조문"과 "해시로 고정한 조문"이 갈린다.**
> 실무적 이유도 있다 — §8 출력은 13키로 화이트리스트 고정돼 `facts_used`·`laws_used` 가 애초에 나오지 않는다.
> `spikes/bundle_integrity.py ⑲` 가 import 문과 자식 프로세스 `sys.modules` 양쪽으로 이 분리를 잠근다.
> 그래서 §8 과 어휘가 같은 것은 **위임이 아니라 `_asset_ref` 공용 모듈 덕분**이며, 그 일치는
> ⑳(입력·해석 8케이스)·㉒(엔진 예외 3종)가 직접 대조한다.

---

## 15. generate_disposal_document — 처분 승인서·진술보장서 **초안** (S10 계층 3의 입구) ⚠️ 두 번째 쓰기 도구

**description (코드 정본 = `generate_disposal_document.py:DESCRIPTION`):**
> "설비 자산의 처분 승인서·진술보장서 '초안'을 생성한다. 확정이 아니다. 반드시 check_disposal_blockers 로 판정을 먼저 확인한 뒤 사용자가 처분을 결정한 후에만 호출할 것. 판정이 BLOCKED·HOLD·INSUFFICIENT_FACTS 여도 초안은 만들어진다 — 그 사실이 초안에 기록되고, 차단을 뚫을지는 팀장이 승인 화면에서 사유와 함께 결정한다. 너는 override 를 요청하거나 사유를 대신 작성할 수 없다 — 그 파라미터가 없다. 근거 조문 원문이 아직 수집되지 않았으면 초안 생성이 거부된다 — 해시할 근거가 없는 서류는 만들지 않는다."

```json
// input — reason 은 **필수**(기본값 없음, D80). asset_id·equipment_id 중 하나 필수
{
  "reason": "라인 개편으로 유휴화된 컨베이어를 매각",   // ★ required
  "asset_id": "AST-L3-CONV",      // optional (either-or)
  "equipment_id": null,           // optional (either-or)
  "disposal_mode": "SALE",        // optional, 기본 "SALE". enum SALE|SCRAP|TRANSFER
  "disposal_date": "2026-09-01"   // optional, ISO 날짜
}
// output
{
  "status": "ok",
  "decision_id": "DEC-0001",              // 채번 규약 `DEC-%04d` (create_po_draft 와 같은 패턴)
  "state": "draft",                       // ★ 리터럴. 파라미터가 아니다
  "decision_type": "DISPOSAL",
  "asset_id": "AST-L3-CONV",
  "verdict_at_signing": "BLOCKED",        // draft 시점 판정. 서명 시 백엔드가 재산출해 덮는다 (D84)
  "bundle_hash": "sha256:9d1e…",
  "override": false,                      // ★ 항상 false — 이 값을 바꿀 파라미터가 없다 (D81)
  "next_step": "이 초안은 확정이 아니다. 팀장 승인 큐에서 서명해야 처분이 확정된다.",
  "documents_preview": {                  // ★ 저장하지 않는다 (D86). 정식 렌더는 GET /api/decisions/{id}
    "approval": "[설비 처분 승인서 — 초안] …",
    "representation_warranty": "[진술 및 보장서 — 초안] …"
  },
  "template_reviewed": true,              // ★ D90 — 문구가 아니라 이 값으로 UI 톤을 정한다
  "template_review_notice": "문안 사람 검수 완료 (2026-08-13)"
}
```

> 🔑 **키 이름이 `unreviewed_template_notice` → `template_review_notice` 로 바뀌었다 (D90, 2026-08-13).**
> 문안 검수가 끝나 값이 *"검수 완료"* 가 되는데 키 이름에 `unreviewed` 가 남으면 자기모순이다.
> 두 값 모두 `data/doc_review.py` 에서 나온다 — `backend` 와 `mcp_server` 가 **같은 모듈**을
> 읽는다(D73). ⛔ 어느 쪽에도 문구를 리터럴로 두지 않는다.
> **검수가 끝나도 줄은 사라지지 않는다** — 법적 문서라 "언제 검수했는가"가 남아야 한다.

### ★ 이 도구가 지키는 경계 (전부 코드로 확인 가능)

| 결정 | 무엇을 | 어디서 |
|---|---|---|
| **D10** | `decisions` 에 `state='draft'` **INSERT 만**. UPDATE/DELETE 권한 자체가 없다 | `db.decision_writer()` 의 TEMP TRIGGER 2개. ⛔ `po_drafts` 전용 `draft_writer()` 를 재사용하지 않는다 — 그걸로 `decisions` 를 만지면 **잠금 없이 쓰는 것**이 된다 |
| **D81** | `override`·`override_reason`·`reviewed_by` 가 **파라미터에 없다** | `server.py:332-346` 시그니처. 스키마에 키가 없으므로 LLM 이 *"추징을 감수하고 매각한다"* 같은 사유를 지어내 BLOCKING 을 뚫는 호출이 **구조적으로 불가능**하다. `:325` 에서 `0, NULL, NULL, NULL, 'draft'` 를 **리터럴로 박는다** |
| **D63** | **BLOCKED 여도 draft 는 정상 생성된다** | 막으면 사용자는 시스템 밖에서 처분하고 **기록만 사라진다.** 출력은 "차단됐다"가 아니라 "차단된 채로 결재에 올라간다" |
| **D23·D37** | `requested_by`·`session_id` 도 파라미터가 아니다 | INSERT 직후 백엔드가 stamp 한다 (`create_po_draft` 와 같은 패턴) |
| **D80** | `reason` 에 기본값을 두지 않는다 | 승인자가 판단 근거를 추적할 수 있어야 한다 |
| **D86** | `documents_preview` 를 **저장하지 않는다** | 저장하면 템플릿이 바뀔 때 저장본이 조용히 낡는다. 정식 렌더는 `GET /api/decisions/{id}` 가 응답 조립 시점에 번들에서 만든다 |
| **D2 태도** | 문안은 **코드 상수**다 — LLM 이 생성하지 않는다 | 진술보장서는 법적 효력이 있는 문서다. 안전 문구와 같은 성격으로 템플릿에 번들 값만 치환하고, 검수 상태를 `template_review_notice` 로 **출력과 문서 본문 양쪽에** 싣는다 (2026-08-13 검수 완료 · D90) |
| **D62** | 사실이 번들에 없으면 `"확인되지 않음"` 으로 적는다 | 빈칸으로 두면 "해당 없음"으로 읽힌다 |

### 근거 없는 서류는 만들지 않는다 — §14 실패의 **그대로 전파**

번들 생성은 `build_evidence_bundle` 을 **함수로 직접 호출**하고, 실패하면 그 `status`·`reason` 을
손대지 않고 그대로 돌려준다. **INSERT 는 번들이 성공한 뒤에만 시작한다** — 실패했다고 말하는 것으로
끝나면 안 되고 **아무것도 쓰지 않아야** 하기 때문이다.

- `law_text_unavailable` → **draft 미생성.** 해시할 조문 원문이 없는 서류는 "이 결정이 참조한 근거가
  이후 변조되지 않았음"을 증명하지 못한다 — 계층 3의 존재 이유가 통째로 사라진다.
- `asset_modified`·`asset_disappeared` → 판정과 서류의 사실이 어긋난 상태다. 역시 미생성.

**status / reason**

| status | reason | 언제 |
|---|---|---|
| `error` | `reason_required` | `reason` 이 문자열이 아니거나 공백. **번들보다 먼저** 본다 — 거부할 입력으로 DB 를 열 이유가 없다 (`create_po_draft` 와 같은 어휘) |
| `error` | `integrity` | FK·CHECK·TEMP TRIGGER(D10) 위반. 계약 위반이므로 그대로 드러낸다 |
| `error` | `db_error` / `db_missing` / `internal_error` | DB 예외 / DB 파일 없음 / 그 밖 |
| (전파) | **§14 의 모든 status·reason** | `law_text_unavailable`·`asset_modified`·`asset_disappeared`·`invalid_input`·`rule_catalog_not_loaded`·`rule_integrity`·`engine_error`·`unknown_asset`·`unknown_equipment`·`no_host_asset`. **여기서 다시 포장하지 않는다** — 포장하면 같은 실패가 도구마다 다른 이름을 갖는다 |

> ⚠ **`documents_preview` 렌더는 INSERT 뒤 `try` 블록 안**에서 한다(`:341`). 문안 조립 버그가 도구를
> 죽이면 D9 가 깨지기 때문이다.
> ⚠ 직렬화는 `canonical_json` 결과를 **그대로** 저장한다(`:315`). 다시 직렬화하면 키 순서·구분자가 달라져
> 서명 시 해시 재대조(D84)가 깨진다.

---

## 16. create_repair_record — 수리 증빙 초안 생성 (S29) ⚠️ 세 번째 쓰기 도구 (D98)

**description (코드 정본 = `create_repair_record.py:DESCRIPTION`):**
> "수리 작업의 증빙 '초안'을 생성한다. 확정이 아니다. 수리가 끝난 뒤 무엇을 어떻게 고쳤는지(작업유형·수리범위·비용·교체 부품)를 기록할 때 호출할 것. 이 초안은 팀장이 서명해야 정식 증빙이 되며, 서명 전에는 get_maintenance_metrics 의 보전지표에 들어가지 않는다. 교체한 부품 품번을 정확히 넣을 것 — 등록되지 않은 품번은 거부된다(unknown_part). 지출의 자본적/수익적 분류(expenditure_class)는 시스템이 자동 산출한다 — 파라미터로 받지 않으며 네가 추측하거나 지어내지 말 것. 에러코드로부터 시작된 수리이면 model·error_code 를 함께 넣을 것 — 매뉴얼에 없는 코드는 거부된다."

`create_po_draft`(§7)·`generate_disposal_document`(§15)와 **같은 패턴**이다: draft 만
INSERT 하고, 확정(서명)은 사람 전용 API 소관이며, 신원은 백엔드가 stamp 한다. 대상은 §8~§14 의
`asset_id` 가 아니라 **`equipment_id`(인버터) 그 자체**다 — 수리는 인버터 단위로 남는다(D68 ⓑ).

```json
// input — equipment_id·work_type·repair_scope·cost·parts 는 필수(기본값 없음, D80)
{
  "equipment_id": "INV-L3-01",
  "work_type": "UNPLANNED",             // PLANNED | UNPLANNED — 미기재 거부 (12 §7)
  "repair_scope": "RESTORE",            // RESTORE|UPGRADE|OVERHAUL|REPLACE_UNIT
  "cost": 850000,                       // > 0 인 정수
  "parts": [{"part_no": "FAN-IG5-01", "serial": "SN-88214", "qty": 2}],  // 1건 이상
  "downtime_hours": 6.5,                // optional. MTTR 의 유일한 원천 (12 §9)
  "model": "iG5A", "error_code": "OHT", // optional (짝). enum(D6·D13) + FK 검증(D33)
  "note": "냉각팬 교체"                  // optional
}
// output
{
  "status": "ok",
  "repair_id": "RPR-2413",              // 채번 RPR-%04d — 시드 2401~2412 다음
  "state": "draft",                     // ★ 리터럴. 파라미터가 아니다
  "equipment_id": "INV-L3-01", "work_type": "UNPLANNED",
  "part_class": "CRITICAL",             // parts 테이블 조회 결과. 파라미터가 아니다
  "expenditure_class": "REVENUE",       // data/maint_value.expenditure() 산출. 파라미터가 아니다
  "expenditure_reason": "…",            // 산출 근거 (HOLD 도 정상 값이다)
  "cost": 850000, "downtime_hours": 6.5,
  "record_hash": null,                  // 서명 시 백엔드가 계산한다 (D84 태도)
  "next_step": "이 기록은 확정이 아니다. 제출 후 팀장이 서명해야 증빙이 된다.",
  "disclaimer": "…"                     // 지출 분류는 회계 판단의 참고값이라는 고지 (D65 태도)
}
```

### 핵심 로직

1. **입력 검증 → 조회 → 산출 → INSERT** 순서. 거부할 입력으로 DB 를 열지 않는다 (`create_po_draft`·`generate_disposal_document` 와 같은 어휘).
2. `parts[*].part_no` 를 `parts` 테이블에서 전부 조회한다. 하나라도 없으면 `error`/`unknown_part`(+`missing[]`) — LLM 이 지어낸 품번이 정비 이력에 남을 경로를 막는다(D33 이 에러코드에 건 방어를 부품에도 건다).
3. `part_class` 산출: 조회한 부품 중 **하나라도 `CRITICAL` 이면 `CRITICAL`**, 전부 `CONSUMABLE` 이면 `CONSUMABLE`, 값이 없는 부품이 섞이면 **`NULL`**(0·임의값으로 메우지 않는다) — 그 사유는 `expenditure_reason` 에 실린다.
4. `expenditure_class` 산출: `data/maint_value.expenditure(con, part_class=…, repair_scope=…, amount=cost)`. **`HOLD` 는 실패가 아니라 판정**이므로 그대로 저장한다(DDL CHECK 가 허용). `part_class` 가 NULL 이면 지출 분류도 **NULL**이고, `expenditure()` 자체가 `status != "ok"` 를 돌려주면 **그대로 전파**하고 INSERT 하지 않는다(§13 이 하위 도구 실패를 삼키지 않는 것과 같은 태도).
5. `(model, error_code)` 는 짝이거나 둘 다 NULL. `model` 은 enum(`iG5A`|`S100`|`IE5`) 강제(D6·D13·D109). `error_code` 는 대문자 canonical로 저장하되 **사전 조회를 하지 않는다** — `create_po_draft` 와 달리 실재 검증은 INSERT 시점의 FK(`(model, error_code) REFERENCES error_codes(model, code)`)에 맡기고, 위반은 `status:"error", reason:"integrity"` 로 그대로 드러난다.
6. `db.repair_writer()` 로 **INSERT 만**. `state='draft'`, `performed_by`/`verified_by`/`signed_at`/`record_hash`/`requested_by`/`session_id` 는 **NULL 리터럴**로 박는다(파라미터로 받지 않는다).
7. `repair_id` 채번: `data/repair_record.next_repair_id()` → `data/txn.next_sequential_id()` **한 곳**만 거친다 (D126). 출력 형식 `RPR-%04d` 는 그대로이고 **경쟁만** 없앴다 — `pg_advisory_xact_lock` 으로 직렬화하고, 후보는 `^RPR-[0-9]+$` 에 맞는 행만, 정렬은 사전순이 아니라 **수치**로 한다. ⛔ 옛 `SELECT max(...)` 사본을 이 도구에 다시 만들지 말 것 — `spikes/db_concurrency.py ㉑` 이 정적 검사로 막는다(초기 서술이었던 *"동시성 방어는 새로 만들지 않는다(P19)"* 는 D126 이 대체했다).
8. `server.py` 등록은 `if TOOLS_PROFILE == "full":` 블록 안에만.

**status / reason**

| status | reason | 언제 |
|---|---|---|
| `error` | `invalid_input` | `equipment_id` 빈 문자열 / `work_type`·`repair_scope` enum 밖 / `cost` ≤0·해석 불가 / `downtime_hours` 음수·해석 불가 / `parts` 가 빈 배열이거나 항목에 `part_no` 없음 / `note` 가 문자열이 아님 |
| `error` | `model_code_pair` | `model`·`error_code` 가 한쪽만 있음 (D33) |
| `error` | `invalid_model` | `model` 이 `iG5A`\|`S100`\|`IE5` 밖 (D6·D13·D109) |
| `not_found` | `unknown_equipment` | 등록되지 않은 설비 |
| `not_found` | `unknown_part` | `parts[*].part_no` 중 `parts` 테이블에 없는 것이 있음. `missing[]` 로 이름을 댄다 |
| `error` | `integrity` | FK((model,error_code))·CHECK·TEMP TRIGGER(D10) 위반. 매뉴얼에 없는 `error_code` 로 부르면 여기서 걸린다(사전 조회 없음) |
| `error` | `db_missing` / `db_error` / `internal_error` | DB 파일 없음 / DB 예외 / 그 밖(D9) |
| (전파) | `data/maint_value.expenditure()` 의 `error`/`not_found` 계열 reason | `part_class` 확정 후 지출 산출이 실패하면 그대로 전파하고 INSERT 하지 않는다 |

**지켜야 할 결정**: D98(전용 writer·프로파일·비파라미터 목록) · D10(draft INSERT 만) · D9(status 반환) ·
D80(필수 기본값 없음) · D12 태도(등급을 추측하지 않는다) · D13·D33(복합키 FK) · D6(model enum) ·
D23·D37(신원 서버 stamp — 이 도구는 아무것도 stamp하지 않고 NULL 로 둔다) · D65(고지) · D69·D88(프로파일)

---

## 17. track_deadlines — 법정 기한(세액공제 사후관리·안전검사) 사전 경보 (S9, Sprint 11, D102)

**description (코드 정본 = `track_deadlines.py:DESCRIPTION`):**
> "자산의 법정 기한(투자세액공제 사후관리 24개월·안전검사 유효기한)이 임박했거나 이미 지났는지 조회한다. 처분·매각을 검토하기 전에 먼저 호출할 것 — 세액공제 사후관리 기간 안에 처분하면 추징 리스크가 있고, 안전검사가 만료된 자산은 가동 자체가 제한될 수 있다. window_days 안에 들어오는 항목만 UPCOMING 으로 표시하며, 안전검사는 만료 후에도 OVERDUE 로 항상 포함한다. 기본 호출(window_days=180)에서 0건이 나올 수 있다 — 이는 실패가 아니라 그 기간 안에 임박한 기한이 없다는 뜻이다(추측으로 채우지 말 것, D62). 처분 차단 여부 자체는 이 도구가 아니라 check_disposal_blockers 를 쓸 것."

읽기 전용이다 — 아무것도 쓰지 않는다. 대상은 §8~§14 와 같은 호스트 자산(`asset_id`)이다(D68).
로직 정본은 `data/deadlines.py`(D101) — 이 도구는 커넥션(`read_only()`)만 갖는 얇은 래퍼다.

```json
// input — 둘 다 optional
{ "asset_id": "AST-L2-SPDL", "window_days": 500 }   // 기본 180
// output
{
  "status": "ok",
  "evaluated_at": "2026-08-18",
  "window_days": 500,
  "items": [
    {
      "asset_id": "AST-L2-SPDL",
      "type": "SAFETY-INSPECTION",           // TAX-CREDIT-2Y | SAFETY-INSPECTION
      "law_refs": ["KR-OSHA-93", "KR-OSHA-ENR-126"],
      "due_date": "2027-11-18",
      "days_remaining": 457,                 // OVERDUE 는 음수
      "state": "UPCOMING",                   // UPCOMING | IN_REVIEW_BAND | OVERDUE
      "message": "…",                        // 룰 카탈로그 message (하드코딩 없음, D101)
      "resolve_options": ["직전 검사증 사본 첨부", "매수측 재검사 계획 확인"]
    }
  ],
  "not_considered": [],                      // NULL 컬럼으로 판정 제외된 자산 사유 (D62)
  "disclaimer": "TAX-CREDIT-2Y 는 취득일 기준 통상 24개월 사후관리 기간의 해석이며 …"
}
```

### 핵심 로직

1. **두 갈래 스캔** — TAX-CREDIT-2Y(`assets.tax_credit_applied=1`, 취득 후 24개월)·
   SAFETY-INSPECTION(`assets.safety_inspection_target=1 AND inspection_valid_until IS NOT NULL`).
   경계 구간(`review_band`)은 하드코딩하지 않고 `data.rules.engine.load_rules()` 로 로드한다(D101).
2. TAX-CREDIT-2Y 는 `months_since_acquisition >= review_band[1]` 이면 정직하게 제외(D62), 경계 구간 안이면
   `IN_REVIEW_BAND`, 그 아래이면서 잔여일 `<= window_days` 면 `UPCOMING`.
3. SAFETY-INSPECTION 은 `due_date < today` 면 **window 무관하게 항상** `OVERDUE`(만료 후가 더 위험하다),
   그 외 잔여일 `<= window_days` 면 `UPCOMING`.
4. `days_remaining` 오름차순 정렬(음수인 `OVERDUE` 가 최상단). `asset_id` 필터 시 두 경로 모두 그 자산만.
5. **기본 호출(`window_days=180`)이 0건인 것 자체는 실패가 아니다** — 9자산 전부가 취득 후 24개월을 넘겼고
   `AST-L2-SPDL` 의 잔여 457일은 기본 window 밖이라, 정직한 0건이 정상 결과다(D62).

**status / reason**

| status | reason | 언제 |
|---|---|---|
| `error` | `invalid_input` | `asset_id` 가 빈 문자열 / `window_days` 가 0 이상 정수로 해석 안 됨 |
| `not_found` | `unknown_asset` | 등록되지 않은 자산 |
| `error` | `rule_catalog_not_loaded` | 룰 카탈로그 미적재 또는 `TAX-CREDIT-2Y`/`SAFETY-INSPECTION` 룰 자체가 없음(D50 어휘 재사용) — "기한 없음"과 "판정 근거 자체가 없음"을 구분한다 |
| `error` | `db_missing` / `db_error` / `internal_error` | DB 파일 없음 / DB 예외 / 그 밖(D9) |

**지켜야 할 결정**: D101(룰 카탈로그가 정본, 임계값 하드코딩 금지) · D73(데이터 계층 import 허용, D15 위반 아님) ·
D62(모름과 없음의 구분, 0건은 정직한 결과) · D9(status 반환) · D50(미적재 어휘 재사용) · D80(파라미터 규약) ·
D69·D88(프로파일)

---

## 18. assess_risk_grade — 건물 단위 위험 프로파일 등급 산출 (S18, Sprint 11, D102)

**description (코드 정본 = `assess_risk_grade.py:DESCRIPTION`):**
> "건물(building_id) 단위의 위험 프로파일(화기 취급·위험물 보관량·수전용량)로 위험등급을 산출하고, 마지막으로 저장된 등급과 달라졌는지(changed) 알려준다. 중고 취득 실사·처분 리스크 판단 시 building_id 또는 asset_id 중 하나로 호출할 것(asset_id 는 자산의 building_id 로 자동 해석된다). 3속성 중 하나라도 미확인이면 current_grade 는 null 이다 — 이때 등급을 추측해 채우지 말 것(D62). changed:true 는 재산정이 필요하다는 신호일 뿐 이 도구가 risk_profile 을 갱신하지는 않는다. 산출 등급은 통상 기준 목업 산식이며 실제 화재·환경 규제상 위험평가를 대체하지 않는다(disclaimer 참조)."

읽기 전용이다 — **아무것도 쓰지 않는다**. `risk_profile.risk_grade` 를 갱신하는 경로는 이 도구를
포함한 어떤 MCP 도구에도 없다(절대 규칙 1). `changed:true` 는 알림 정보일 뿐 자동 반영이 아니다.
로직 정본은 `data/risk_grade.py`(D101) — 이 도구는 커넥션(`read_only()`)만 갖는 얇은 래퍼다.

```json
// input — building_id · asset_id 중 하나만 (원칙 5 either-or)
{ "building_id": "BLD-C", "asset_id": null }
// output
{
  "status": "ok",
  "building_id": "BLD-C",
  "facts": {
    "fire_handling": "HIGH", "hazmat_volume": "MEDIUM", "power_capacity": "MEDIUM",
    "product_type": "도장·코팅 공정품 (인화성 도료 취급)"   // 점수화 안 함, 정보성
  },
  "current_grade": "HIGH",                 // null 이면 3속성 중 미확인 있음 (D62)
  "stored_grade": "LOW",
  "stored_grade_updated_at": "2025-06-18",
  "changed": true,                         // current != stored. 저장은 하지 않는다
  "grade_scale": ["LOW", "MEDIUM", "HIGH"],
  "rationale": "화기 취급 HIGH·위험물 보관량 MEDIUM·수전용량 MEDIUM → 점수 7 → HIGH",
  "not_considered": [],
  "disclaimer": "이 등급은 통상 기준 목업 산식이다. 실제 화재·환경 규제상 위험평가를 대체하지 않는다."
}
```

### 핵심 로직

1. `building_id`·`asset_id` **either-or**(D80 예외 패턴, 원칙 5). `asset_id` 를 주면
   `assets.building_id` 로 해석한다.
2. `risk_profile` 을 조회한다 — 없으면 `not_found`/`unknown_building`.
3. 3속성(`fire_handling`·`hazmat_volume`·`power_capacity`) 중 하나라도 NULL 이면 `current_grade:null` +
   `not_considered` 에 사유(추측 금지, D62). `product_type` 은 점수화하지 않는 정보성 필드다.
4. 셋 다 있으면 `GRADE_ORDER`(LOW=1/MEDIUM=2/HIGH=3) 합산 →
   `<=4 LOW / 5~6 MEDIUM / >=7 HIGH`(이 값의 정본은 `data/risk_grade.py`, 사본을 두지 않는다).
5. `changed = current_grade is not None and current_grade != stored_grade`. `stored_grade` 가 NULL 이면
   "최초 산출"이라 `changed:false`.
6. **아무것도 쓰지 않는다** — `risk_profile.risk_grade` UPDATE 경로 자체가 도구에 없다(절대 규칙 1).

**status / reason**

| status | reason | 언제 |
|---|---|---|
| `error` | `invalid_input` | `building_id`·`asset_id` 둘 다 없거나 둘 다 있음 / 문자열이 아님 |
| `not_found` | `unknown_asset` | `asset_id` 로 조회했는데 등록되지 않은 자산 |
| `not_found` | `no_building` | 자산은 있으나 `building_id` 가 비어 있음 |
| `not_found` | `unknown_building` | 위험 프로파일이 등록되지 않은 건물 |
| `error` | `db_missing` / `db_error` / `internal_error` | DB 파일 없음 / DB 예외 / 그 밖(D9) |

**지켜야 할 결정**: D101(임계값·GRADE_ORDER 정본은 이 모듈, 사본 금지) · D65(고지) · D62(모름과 없음의 구분,
추측 금지) · D10(아무것도 쓰지 않는다) · D9(status 반환) · D80(either-or 예외 패턴) · D69·D88(프로파일)

---

## 19. search_insurance_clause — InsuQ 약관 보장 여부 조회 (신규, D112)

**description (코드 정본 = `search_insurance_clause.py:DESCRIPTION`):**
> "화재보험 등 보험 약관의 보장 여부를 InsuQ(외부 보험 파트너)에 문의한다. 정비사가 설비 고장·손해의
> 보험 보장 여부를 명시적으로 물을 때만 호출할 것. MaintQ 매뉴얼 근거가 아니라 외부 파트너의 응답이므로
> 결과를 그대로 전달하고 추측을 덧붙이지 말 것. 실패 시 확답을 못 얻었다는 사실을 정직하게 알릴 것."

⚠ **§8~§18 과 구조가 다르다.** 이 도구는 `data/`(엔진·룰 카탈로그)를 직접 읽지 않는다 — `mcp_server`
프로세스에서 **backend REST**(`POST /api/a2a/lookup-clause`)를 `httpx` 로 동기 호출하고 그 응답을
그대로 전달할 뿐이다. mcp_server 는 여전히 `backend.a2a`·A2A 자격증명을 모른다(D15·D93 유지) — 이
도구가 아는 것은 `MAINTQ_BACKEND_BASE_URL`(`.env.example`, MQ-1603) 하나뿐이다. 대상도
`asset_id`/`equipment_id` 가 아니라 자유 질의(`question`)다.

```json
// input
{ "question": "화재로 인한 인버터 손해가 보험으로 보장되나요?" }   // required — 공백이면 거부 (D80)
// output (성공 — InsuQ skill_status == "completed")
{
  "status": "ok",
  "skill_status": "completed",     // InsuQ 프로토콜 자체의 어휘(completed|input-required|rejected) 보존
  "verdict": "...",                // InsuQ 응답 그대로 — 이 문서가 값을 규정하지 않는다
  "answer": "...",
  "evidence": ["..."],
  "request_chain_id": "CHAIN-CLAUSE-xxxxxxxx"   // SSE tool_result.a2a_chain_id 로 이어진다 (D113)
  // ...(백엔드 응답의 나머지 키를 그대로 보존 — D76 구조 보존 정신)
}
```

### 핵심 로직

1. 입력 검증 — `question` 이 빈 문자열/공백이면 `question_required`(D80: 인자 누락 자체는 MCP 스키마가
   앞단에서 막지만, 공백 문자열은 코드가 막는다).
2. `base_url = os.environ.get("MAINTQ_BACKEND_BASE_URL") or "http://localhost:8000"` 로 백엔드 REST 를
   호출한다 — **`MAINTQ_A2A_` 접두어를 쓰지 않는다**, 그 접두어는 `backend/a2a/` 자격증명 전용이다(D93).
3. `resp.status_code == 200` 이고 `data.get("status") == "completed"` 일 때만 성공(`status:"ok"`)으로
   매핑한다. InsuQ 가 `input-required`·`rejected` 를 돌려주면(확답 아님) `status:"error", reason:"no_answer"`
   — 확답을 안 줬는데 `ok` 로 위장하면 절대 규칙 6("미지에 유사 코드 추측 금지")과 같은 종류의 환각이 된다.
4. 백엔드가 `502`/`503`/`504` 를 반환 → `upstream_unavailable`(InsuQ A2A 어댑터 자체에 응답을 못 받음).
   그 외 `httpx.HTTPError`(백엔드 프로세스 자체에 못 닿음) → `backend_unreachable`. 둘을 구분하는 이유는
   재시도 대상이 다르기 때문이다 — 전자는 파트너 문제, 후자는 MaintQ 배포 문제다.

### 엣지 케이스

- `MAINTQ_BACKEND_BASE_URL` 미설정 → `http://localhost:8000` 폴백(백엔드·MCP 서브프로세스 로컬
  co-location 전제, `MAINTQ_MCP_AUTOSTART` 기본 동작과 같은 가정).
- InsuQ 로컬 어댑터가 미기동이면 백엔드 `POST /api/a2a/lookup-clause` 자체가 502/504 를 낸다 — 이
  경로는 **정상 실패**다(현재 로컬·배포 어디서도 200 을 못 본 것이 실측, `status.html`).

**status / reason**

| status | reason | 언제 |
|---|---|---|
| `error` | `question_required` | `question` 이 비어 있거나 공백 |
| `error` | `timeout` | `httpx.TimeoutException`(12.0초) |
| `error` | `backend_unreachable` | 백엔드 프로세스 자체에 연결 실패(연결 거부 등) — A2A 파트너가 아니라 MaintQ 백엔드에 못 닿은 경우 |
| `error` | `upstream_unavailable` | 백엔드가 502/503/504 반환 — InsuQ A2A 어댑터에 응답을 못 받음 |
| `error` | `no_answer` | InsuQ `skill_status` 가 `input-required`/`rejected` — 확답 아님 |
| `error` | `unexpected_status` | InsuQ `skill_status` 가 `completed`/`input-required`/`rejected` 밖의 값 |
| `error` | `invalid_response` | 백엔드 응답 본문이 JSON 파싱 불가 |
| `error` | `a2a_error` | 그 외 HTTP 상태코드. `message` 는 응답 `detail` 또는 본문 앞 200자 |

**지켜야 할 결정**: D15·D93(mcp_server 는 `backend.a2a`·`MAINTQ_A2A_*` 를 참조하지 않는다 —
`MAINTQ_BACKEND_BASE_URL` 이라는 다른 이름의 env 를 쓴다) · D9(status 반환) · D80(필수 파라미터
기본값 없음) · D69·D88(`full` 프로파일 전용 — `core` 에 넣으면 `eval/run_eval.py` 의
`tools > CORE_TOOL_COUNT(=7)` 게이트가 깨진다) · D113(SSE `a2a_chain_id`) · D114(`GET /api/a2a/history` 로 원문 조회)

---

## 20. assess_equipment_loan — FinAllQ 설비 담보 대출 사전판정 (확장 S8 — A2A_Q 2026-08-14 스냅샷 번호,
2026-08-23 사용자 지도 기준으로는 S4, D112)

**description (코드 정본 = `assess_equipment_loan.py:DESCRIPTION`):**
> "설비를 담보로 한 대출 사전판정을 FinAllQ(외부 금융 파트너, 내부적으로 InsuQ 2차 조회 포함)에
> 문의한다. 사용자가 설비 담보 대출을 명시적으로 물을 때만 호출할 것. 현재 파트너 쪽 연동이 아직
> 준비되지 않아 실패 응답이 정상적으로 나올 수 있다 — 실패를 오류로 취급하지 말고 결과를 있는 그대로
> 전달할 것."

⚠ **§19 와 같은 구조다** — `mcp_server` → backend REST(`POST /api/a2a/assess-loan`) 왕복이며
`data/`(엔진·룰 카탈로그)를 직접 읽지 않는다(D15·D93). 대상도 자산이 아니라 대출 조건(금액·목적·담보
건물 ID)이다.

```json
// input — 셋 다 필수(기본값 없음, D80)
{
  "loan_amount": 50000000,           // > 0, bool 은 숫자로 취급하지 않는다
  "purpose": "설비 교체 자금",
  "collateral_building_id": "BLD-C"
}
// output (성공 — FinAllQ skill_status == "completed")
{
  "status": "ok",
  "skill_status": "completed",
  "verdict": "...",                  // FinAllQ 응답 그대로
  "request_chain_id": "CHAIN-LOAN-xxxxxxxx"
  // ...(백엔드 응답의 나머지 키를 그대로 보존)
}
```

### 핵심 로직

§19 와 **동일 패턴**이며 차이는 URL(`/api/a2a/assess-loan`)·입력 파라미터·payload 키뿐이다.

1. 입력 검증 — `loan_amount` 가 숫자가 아니거나(`bool` 포함) `<= 0` / `purpose` 공백 /
   `collateral_building_id` 공백 → `invalid_input`(D80).
2. §19 와 같은 `MAINTQ_BACKEND_BASE_URL` 을 쓴다(같은 env, 다른 경로).
3. `skill_status == "completed"` 만 성공. 그 외(`input-required`·`rejected`) → `no_answer`, 그 밖 값 →
   `unexpected_status`.
4. 백엔드가 502/503/504 반환 → `upstream_unavailable`.

### 엣지 케이스

- **502/504 가 정상 경로다** — FinAllQ 는 내부적으로 InsuQ 2차 조회를 거치는데, 이 2차홉이 아직
  준비되지 않아 실측(로컬·배포 어디서나, `status.html`)상 `assess-loan` 은 거의 항상
  `upstream_unavailable` 로 끝난다. 버그가 아니라 현재 연동 상태다 — `DESCRIPTION` 이 에이전트에게
  이 사실을 미리 알려 실패를 오류로 취급하지 않게 한다.
- `loan_amount` 가 `bool`(`True`/`False`)이면 `invalid_input` — `isinstance(x, bool)` 을 먼저 걸러
  `True`(=1)가 유효한 금액으로 통과하는 것을 막는다.

**status / reason**

| status | reason | 언제 |
|---|---|---|
| `error` | `invalid_input` | `loan_amount` ≤0·숫자 아님(`bool` 포함) / `purpose` 공백 / `collateral_building_id` 공백 |
| `error` | `timeout` | `httpx.TimeoutException`(12.0초) |
| `error` | `backend_unreachable` | 백엔드 프로세스 자체에 연결 실패 |
| `error` | `upstream_unavailable` | 백엔드가 502/503/504 반환 — **현재 실측상 이 경로가 정상값이다** |
| `error` | `no_answer` | FinAllQ `skill_status` 가 `input-required`/`rejected` |
| `error` | `unexpected_status` | FinAllQ `skill_status` 가 3값 밖 |
| `error` | `invalid_response` | 백엔드 응답 본문이 JSON 파싱 불가 |
| `error` | `a2a_error` | 그 외 HTTP 상태코드 |

**지켜야 할 결정**: D15·D93(§19 와 동일) · D9(status 반환) · D80(필수 파라미터 기본값 없음) ·
D69·D88(`full` 전용) · D113·D114(§19 와 동일)

---

## 21. get_document_facts — 결재 문서 필드 조회 (읽기 전용, D125)

**결재 문서에 실제로 찍힐 값을 문서 양식의 자리 이름 그대로** 돌려준다. 에이전트가
"이 발주서에 뭐라고 적혀 있나" · "어느 항목이 비었나" 를 **짚어서** 말할 수 있게 하는 것이
목적이다 — 그래서 업무 값이 아니라 **템플릿 자리**를 준다.

⛔ **이 도구는 아무것도 쓰지 않는다** (절대규칙 1 · D10). `read_only()` 만 쓰고
`draft_writer()`·`decision_writer()`·`repair_writer()` 를 부르지 않는다.

### 입력

| 파라미터 | 타입 | 필수 | 설명 |
|---|---|---|---|
| `doc_type` | `str` | ✅ | `po` (발주: 01·02) \| `disposal` (처분: 05·06) |
| `ref_id` | `str` | ✅ | 발주 ID(`PO-0117`) 또는 처분 결정 ID(`DEC-0007`) |

둘 다 **기본값이 없다** (D80) — 인자 누락은 MCP 스키마가 앞단에서 막는다.

### 출력

```jsonc
{
  "status": "ok",
  "doc_type": "po",
  "ref_id": "PO-0117",
  "fields": {                     // 템플릿 자리 이름 → 값 (문자열)
    "01": { "DOC_NO": "DIAG-PO-0117", "ERROR_CODE": "E-011", ... },   // 37자리
    "02": { "PO_REQUEST_NO": "PO-0117", "TOTAL_AMOUNT": "158,400", ... }  // 36자리
  },
  "withheld": ["APPROVER_NAME", "MANAGER_NAME", "OVERRIDE", "SIGNED_BY", ...],  // 16키
  "unavailable": { "03": "내부통제 판정(D119)은 재무 승인 경로에서만 산출됩니다..." },
  "correction_hint": "이 도구는 조회만 합니다. 값이 틀렸다면 create_po_draft 로 ..."
}
```

실패: `{"status":"error", "reason":"invalid_input"|"not_found"|"db_error"|"db_missing", "message":"..."}` (D9)

### `withheld` 와 `unavailable` 은 다른 사실이다 (D62)

| 키 | 뜻 |
|---|---|
| `withheld` | 값은 **있지만 도구에 주지 않는다** — 신원·서명 16키 (D23·D37·D81) |
| `unavailable` | 값의 **원천이 없다** — 그 문서가 성립하지 않는다 |

합치면 에이전트가 *"요청자 이름이 시스템에 없다"* 고 말하게 되는데 **그건 거짓이다.**
`data/doc_fields.py` 는 `withheld` 자리를 애초에 **만들지 않고**, docx 다운로드
엔드포인트만 DB 에서 읽어 얹는다.

`unavailable` 에 들어가는 경우:
- **`03`** — 항상. 내부통제 판정(D119)은 재무 승인 경로에서만 산출되고, `create_po_draft`
  로 새 draft 를 넣어도 달라지지 않는 **교정 경로가 없는 값**이다
- **`01`** — 그 발주에 `error_code_def` 가 없을 때(에러코드 진단에서 시작하지 않은 발주).
  빈 칸투성이 문서를 만들지 않는다 — 미리보기도 같은 조건에서 `null` 이다

### 교정은 이 도구가 아니다 (D10·D125)

```
읽기      get_document_facts        ← 현재 값 조회 (UPDATE 없음)
교정      create_po_draft           ← 새 draft INSERT (원래 열려 있다)
사람      PATCH /api/po · /api/repairs · /api/decisions   ← 화면에서 직접 수정 (P39·D111)
docx      GET .../documents/{doc}.docx                     ← 다운로드 시점 렌더 (D86·D124)
```

**지켜야 할 결정**: D10(쓰기 금지) · D23·D37·D81(신원·서명 비노출) · D62(withheld ≠ unavailable) ·
D9(status 반환) · D80(필수 파라미터 기본값 없음) · D69·D88(`full` 전용) · D124(필드맵 공유 계층)

---

## 확장 도구 reason 색인 (한눈에)

| reason | 나오는 도구 | 성격 |
|---|---|---|
| `invalid_input` | 8·9·11·12·13·14·**16**·**20** (→15 전파) | 호출 값이 잘못됨 (누락은 MCP 스키마가 앞단에서 막는다 — D80) |
| `unknown_asset` | 8·9·11·12·13·14 (→15 전파) | `not_found` |
| `unknown_equipment` | 8·9·11·13·14·**16** (→15 전파) | `not_found` |
| `no_host_asset` | 8·9·11·13·14 (→15 전파) | `not_found` — 호스트 자산 미지정. **"문제 없음"이 아니다** (§16 은 `asset_id` 를 안 보므로 이 reason 이 없다) |
| `unknown_part` | 10 (→13 전파) · **16(독립)** | `not_found` — §16 은 §10 을 경유하지 않고 `parts` 테이블을 직접 조회한다 |
| `part_class_not_set` / `part_class_invalid` | 10 (→13 전파) | 등급 미등록 / 허용값 밖. §16 은 이 reason 대신 `part_class:null` + `expenditure_reason` 으로 "모른다"를 표현한다(값을 거부하지 않는다) |
| **`model_code_pair`** / **`invalid_model`** | 코어 §7 · **16** | `(model, error_code)` 불일치 / `model` enum 밖. §16 은 §7 과 같은 어휘를 재사용한다(사본을 새로 만들지 않는다) |
| `rule_catalog_not_loaded` | 8·14 (→15 전파) | 카탈로그 0행. `not_found` 로 주면 전 자산이 `CLEAR` (D50) |
| `rule_integrity` | 8·14 (→15 전파) | 근거 없는 룰 (D61) |
| `law_ref_missing` | 12 (→**16** 전파, `part_class` 확정 시) | 근거 조문 미등록 → 판정 자체를 하지 않음 |
| `law_not_effective` | 12 (→**16** 전파) | 시점 밖 조문. 최신본 대체 금지 |
| `law_text_unavailable` | 14 (→15 전파) | 조문 원문 미수집 → 번들 생성 거부 (MQ-701 수집 후 **실 DB 에서는 미발화**). **15 는 이때 draft 를 만들지 않는다** |
| `asset_disappeared` | 14 (→15 전파) | 판정 직후 자산 행 소실 |
| **`asset_modified`** | 14 (→15 전파) | **N2** — 판정 후 조립 사이에 자산 행이 바뀜. 한 시점의 사실을 증명하지 못하는 번들은 만들지 않는다 |
| `engine_error` | 8·14 (→15 전파) | **엔진 계약 위반을 확인한 자리에만** — 계약 밖 verdict · 계약 키 누락 · 재평가 불일치. ⛔ 일반 예외 그물이 아니다 |
| **`reason_required`** | **15** | `reason` 미기재. 코어 §7 `create_po_draft` 와 같은 어휘 |
| **`integrity`** | **15·16** | FK·CHECK·TEMP TRIGGER(D10) 위반. 코어 §7 과 같은 어휘. **16 은 이 reason 뒤에 사전 조회가 없다** — 매뉴얼에 없는 `error_code` 는 여기서 걸린다 |
| `db_missing` | 9·14·15·**16** | DB 파일 없음. ⚠ 8 은 이 자리에서 `db_error` 를 낸다(§8 표의 비대칭 주 참조) |
| `db_error` | 8·9·10·11·12·13·14·15·**16** | DB 예외 |
| `internal_error` | **8**·9·10·12·13·14·15·**16** | 그 밖의 예외를 status 로 닫는 마지막 그물 (D9). **MQ-712 에서 8 이 `engine_error` → `internal_error` 로 통일됐다** |

**§19·§20 전용 reason (D112)** — 8~18 의 전파 사슬 밖이다. 둘 다 §7·§16 처럼 사전 조회가 없고, `data/`
가 아니라 backend REST 응답 자체에서 실패를 판정한다.

| reason | 나오는 도구 | 성격 |
|---|---|---|
| `question_required` | **19(독립)** | `question` 공백. §20 에는 없다(그 대신 `invalid_input`) |
| `timeout` | **19·20** | `httpx.TimeoutException`(12.0초) |
| `backend_unreachable` | **19·20** | MaintQ 백엔드 프로세스 자체에 연결 실패 — A2A 파트너 실패와 구분 |
| `upstream_unavailable` | **19·20** | 백엔드가 502/503/504 반환. §20 은 이 값이 **실측상 정상 경로**(2차홉 미비) |
| `no_answer` | **19·20** | 파트너 `skill_status` 가 `input-required`/`rejected` — 확답 아님 |
| `unexpected_status` | **19·20** | 파트너 `skill_status` 가 3값 밖 |
| `invalid_response` | **19·20** | 백엔드 응답 본문 JSON 파싱 불가 |
| `a2a_error` | **19·20** | 그 외 HTTP 상태코드 |

> **코어 7종의 reason** (참고): `invalid_model` · `code_required` · `catalog_not_loaded` · `malformed_row` ·
> `query_required` · `index_not_built` · `search_failed` · `invalid_line_id` · `invalid_days` ·
> `reason_required` · `model_code_pair` · `unknown_error_code` · `no_quote` · `moq_not_met` · `integrity` ·
> `invalid_input` · `db_error`.

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
| 13 | 확장 도구를 `MAINTQ_TOOLS_PROFILE` 로 게이트, 기본 `core` | 도구를 7종 늘린 뒤 평가를 돌리면 "수정 효과 vs 도구 증가 효과"를 분리할 수 없다. 프롬프트는 env 가 아니라 `list_tools()` 실측 목록으로 조립 (D69) |
| 14 | 확장 도구의 대상은 `asset_id` (호스트 설비) | 인버터는 중고 거래 대상이 아니라 부품에 가깝다 — 실측(중진공 16,011건 중 인버터 4건). 기존 7종 계약은 무변경 (D68) |
| 15 | 필수 파라미터에 기본값 없음, either-or 는 `DESCRIPTION` 이 말한다 | 기본값을 두면 FastMCP 가 optional 로 노출해 "인자 없이 호출 → invalid_input → 재시도" 루프가 생긴다. 잘못된 호출을 처리하는 것보다 만들 수 없게 하는 편이 낫다 (D80) |
| 16 | `check_disposal_blockers` verdict 5종, 우선순위는 엔진에만 | `HOLD`(전문가 검토)와 `INSUFFICIENT_FACTS`(데이터 입력)는 해소 경로가 정반대다. 도구가 재조립하면 구 4종으로 되돌아가는 회귀가 조용히 들어온다 (D79·D71) |
| 17 | `assess_repair_value` 는 **HOLD 를 EOL 보다 먼저** 본다 | 잔가 원천이 없는데 "교체하라"고 권하는 것도 근거 없는 판단이다. 이 순서라야 "`residual_curve` 를 비우면 전 자산 HOLD"가 성립한다 — 값을 지어내지 않음의 기계적 증명 |
| 18 | `build_evidence_bundle` 은 미수집 조문이 있으면 거부 | 해시할 원문이 없는 번들은 무결성을 증명하지 못한다. 막는 것은 판정이 아니라 **서명용 증빙 생성뿐**이다 (D60·`11 §2`) |
| 19 | ~~확장 도구도 쓰기가 하나도 없다~~ → **Sprint 7 에서 뒤집혔다.** `generate_disposal_document`(§15)가 `decisions` 에 **draft INSERT** 를 한다 | 유지된 것: **UPDATE/DELETE 권한은 여전히 없다**(TEMP TRIGGER 2개). 서명·상태 전이는 사람 전용 API 소관 그대로다 (D10·D81). 바뀐 것은 "쓰기가 없다"가 아니라 "쓰기가 draft 로 한정된다" — `create_po_draft` 가 4스프린트간 지켜 온 패턴을 복제했을 뿐이다 |
| 20 | `generate_disposal_document` 스키마에 `override` 키를 두지 않는다 | 스키마에 키가 없으면 LLM 이 BLOCKING 을 뚫는 사유를 지어내 호출하는 경로가 **구조적으로** 막힌다 — D23(신원)·D31(단가)을 뺀 것과 같은 이유. 예외 적용은 서명 API 가 `X-User` 와 함께 받는다 (D81) |
| 21 | 엔진 예외 어휘를 `internal_error` 로 통일 (MQ-712) | `except Exception` 그물은 엔진 예외만 잡지 않는다 — `engine_error` 라 부르면 원인을 단정한 거짓 라벨이 되고, 같은 실패가 §8·§14 에서 다른 이름을 가졌다. `engine_error` 는 **엔진 계약 위반을 실제로 확인한 자리**에만 남는다 |
| 22 | 세 번째 쓰기 도구 `create_repair_record`(§16)는 `repair_records` **전용** `repair_writer()` 커넥션을 갖는다 (D98, MQ-906) | `draft_writer()`·`decision_writer()` 를 재사용하면 다른 테이블 전용 트리거가 걸린 커넥션으로 `repair_records` 를 만지는 셈이라 잠금이 없는 채로 쓰는 것이 된다. `part_class`·`expenditure_class` 도 파라미터가 아니다 — 회계 판정을 LLM 이 지어낼 경로를 막는다(D31·D81 과 같은 이유). API 계약(`kind:"repair"`)은 D85 가 이미 예약해 둔 값이라 바뀌는 게 없다 |
| 23 | `tool_result` SSE 이벤트에 선택 필드 `a2a_chain_id` 추가(D113) + `GET /api/a2a/history` 신설(D114, Sprint 16) | §19·§20 은 InsuQ/FinAllQ 응답을 실시간 스트림엔 상관관계 키만 흘리고 원문은 별도 조회 API 에서 연다 — `block` 4번째 타입·`summary` 문자열 욱여넣기·SSE 이벤트 5번째 타입은 전부 D14·D22·D26·D32 위반이라 기각했다. 전문은 `10_DECISIONS.md` D113·D114 참조 |

## 도구 ↔ 시나리오 매핑

| 시나리오 | 호출 시퀀스 |
|---|---|
| S1 해피패스 | lookup → rag_search → search_inventory → get_supplier_quotes → create_po_draft |
| S2 재고 없음 | search_inventory(qty=0) → find_alternative_parts → get_supplier_quotes → create_po_draft |
| S3 반복 고장 | lookup → **get_error_history(repeated)** → rag_search(근본원인) → 발주 보류 |
| S4 미지 코드 | lookup(**not_found**) → 추측 금지 → A/S 안내 |
| **S1+** 수리 판단 (확장) | classify_part_criticality → get_maintenance_metrics → **assess_repair_value** → (필요 시) classify_expenditure |
| **S9** 처분 차단 (확장) | (사전 경보) **track_deadlines**(§17, 법정 기한 임박 확인, Sprint 11) → **check_disposal_blockers(BLOCKED/HOLD/INSUFFICIENT_FACTS)** → 해소 경로 안내 (REST 는 409, D71) |
| **S10** 근거 번들 → 서명 (확장) | check_disposal_blockers → **generate_disposal_document**(내부에서 `build_evidence_bundle` 호출 → `decisions` draft INSERT) → 사람이 자산 화면에서 `POST /api/decisions/{id}/submit` → 승인 큐 → `POST /api/decisions/{id}/sign`. ⚠ **`build_evidence_bundle` 을 에이전트가 따로 부를 필요는 없다** — §15 가 함수로 직접 호출한다 |
| **S18** 중고 취득 검증 (확장) | **verify_ownership(PARTIAL)** → 잔여 리스크 + 계약상 배분 안내 → (실사 보존) **assess_risk_grade**(§18, 건물 위험등급, Sprint 11) |
| **S29** 수리 증빙 (확장) | (수리 완료 후) **create_repair_record**(§16, `expenditure_class` 자동 산출) → `decisions` 와 마찬가지로 사람이 승인 큐에서 서명 → 서명분만 `get_maintenance_metrics` 지표에 반영 |
| 신규 InsuQ 상담 | **search_insurance_clause**(§19, 사용자 명시 질의 시에만, D112) → InsuQ 응답을 그대로 전달 → 후속 조회는 `GET /api/a2a/history`(D114) |
| S8/S4 FinAllQ 담보대출 | **assess_equipment_loan**(§20, 사용자 명시 질의 시에만, 현재 실패가 정상, D112 — A2A_Q 2026-08-14 스냅샷 번호로는 S8, 2026-08-23 사용자 지도 기준으로는 S4) → 후속 조회는 `GET /api/a2a/history`(D114) |

## 다음 단계
목업 DB 스키마 — 이 도구들이 읽을 테이블: `05_DB_SCHEMA.md` 참조
