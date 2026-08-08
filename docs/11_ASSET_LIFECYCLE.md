# 자산 생애주기 — 처분 · 법정 조건 · 근거 3계층

> ⚠️ **순서 주의.** 범위에는 포함되지만(D67), `00_MVP_SCOPE`의 기능 6종과 완료 기준 5개가 먼저다.
> S1~S4 관통이 끝난 뒤에 착수하는 것을 권장한다 — 이유는 §8.

**한 줄:** 기능 1~6번이 *무엇을 할지 판단한다*였다면, 7~12번은 **그 판단이 왜 그런지 증명하고 책임을 사람에게 귀속시킨다.**

기존 원칙의 연장선이지 새 원칙이 아니다:

| 기존 (1~6번) | 확장 (7~12번) |
|---|---|
| 정의=룩업 / 절차=RAG (**D1**) | 조문=룩업 / 적용=룰 (**D59**) |
| 근거 페이지 인용 100% | **근거 조문 인용 100%** |
| 도구에 UPDATE 권한 없음 (**D10**) | 근거 없는 룰은 **로드 자체가 거부** (**D61**) |
| `not_found`를 추측으로 메우지 않음 (S4) | `INSUFFICIENT_FACTS` ≠ `CLEAR` (**D62**) |
| 승인은 채팅 밖 큐에서 (**D18**) | 처분은 **서명** 없이 확정 불가 (**D63**) |

---

## 1. 왜 처분인가

설비는 사고 → 쓰고 → 판다. MVP는 "쓰는 동안"만 다룬다.

처분 시점에 그동안 쌓인 세무·법적 상태가 **한꺼번에 정산된다.** 그래서 처분은 단순한 레코드 삭제가 아니라 **매듭을 푸는 지점**이고, 여기서 시스템이 할 일이 생긴다.

그리고 실무상 **설비는 중고 거래가 활발하다** — 수명이 20~30년으로 길고 표준화돼 있으며, 신품 납기가 수개월~1년이라 급하면 중고가 유일 대안이다. 처분/취득이 예외가 아니라 일상이다. 배경은 `12_MAINT_VALUE §5`.

---

## 2. 근거 3계층 (★ 이 문서의 핵심)

LLM 응답 자체는 근거가 될 수 없다. 세 계층으로 분리한다.

```
계층 1 — 사실     법령 원문 스냅샷 (조문 단위 · 시행일 · 해시)   append-only, 수정 불가
      ↓
계층 2 — 해석     LLM/룰 적용 판단, 근거 ID 인용 강제            미인용 시 판정 거부
      ↓
계층 3 — 확정     사람 서명, 번들 해시 고정                      책임 귀속
```

| | 계층 1 (`laws/`) | 계층 2 (`rules/`) |
|---|---|---|
| 성격 | **사실** — 다툼의 여지 없음 | **해석** — 틀릴 수 있음 |
| 수정 | 불가 (append-only) | 가능 (`rule_version` 증가) |
| 출처 | law.go.kr 원문 | 우리가 작성 |
| 개정 시 | 새 레코드 + `effective_to` 마감 | 사람 재검토 후 서명 |

**섞으면 안 되는 이유:** 나중에 무엇이 사실이고 무엇이 판단이었는지 구분할 수 없다. 분리해두면 "조문은 그대로인데 해석을 v3로 갱신했다"가 기록된다. → **D60**

### 계층 1 — 법령 스냅샷

```json
{
  "law_ref_id": "KR-STTC-24",
  "law_name": "조세특례제한법", "article": "24",
  "title": "통합투자세액공제",
  "text": null,                    // 수집 전에는 null. 손으로 타이핑하지 않는다
  "fetch_status": "PENDING",
  "effective_from": null, "effective_to": null,
  "source_url": "https://www.law.go.kr/…",
  "text_hash": null,               // NFKC + 공백축약 정규화 후 sha256
  "verification_note": "조문 번호·제목도 검증 대상"
}
```

- **조 단위로 쪼갠다.** 문서 통짜 저장은 인용 앵커를 만들 수 없다. InsuQ가 약관을 조·항으로 청킹하는 것과 같은 발상이되, 목적이 검색이 아니라 **인용**이다.
- **해시는 정규화 후에.** 전각/반각·줄바꿈 변형으로 해시가 흔들리면 개정 감지가 오작동한다.
- **시점 조회는 `get_law_as_of(id, at)`** — 해당 시점 조문이 없으면 조용히 최신본을 주지 않고 **예외**. D50이 "0행을 not_found로 처리하면 지표가 가짜가 된다"고 판단한 것과 같은 논리다.

### 계층 2 — 해석 룰

```json
{
  "rule_id": "TAX-CREDIT-2Y",
  "disposal_type": "BLOCKING",
  "source_type": "LAW",                  // LAW | CONTRACT
  "law_refs": ["KR-STTC-24", "KR-STTC-146"],
  "interpretation": "…사후관리 기간 내 처분 시 공제세액 추징…",
  "required_facts": ["tax_credit_applied", "acquired_at", "disposal_date"],
  "trigger": {"all_of": [
    {"field": "tax_credit_applied", "op": "eq", "value": true},
    {"field": "months_since_acquisition", "op": "lt", "value": 24}
  ]},
  "boundary": {"field": "months_since_acquisition", "review_band": [22, 26],
               "on_boundary": "HOLD",
               "note": "기산일 해석(취득일 vs 사용개시일)에 따라 달라짐"},
  "confidence": "MEDIUM",
  "requires_expert_review": true,
  "rule_version": 1
}
```

### 계층 3 — 서명

```json
{
  "decision_id": "DEC-2026-0842",
  "evidence_bundle": {
    "laws":  [{"law_ref_id": "KR-STTC-24", "effective_from": "2025-01-01", "text_hash": "sha256:a3f2…"}],
    "rules": [{"rule_id": "TAX-CREDIT-2Y", "rule_version": 3}],
    "facts": {"acquired_at": "2025-03-01", "appraised_value": 42000000}
  },
  "bundle_hash": "sha256:9d1e…",
  "reviewed_by": "mgr-01",              // users FK (D41), ID 저장 (D36)
  "signed_at": "2026-08-04T14:22:30Z",  // UTC (D39)
  "override": true,
  "override_reason": "세액공제 추징 감수 — 신규 라인 일정 우선"
}
```

**`override`가 핵심이다.** 추징을 감수하고 파는 건 정당한 경영 판단이다. 시스템은 막지 않는다 — **막았다는 사실과 뚫은 사람을 기록할 뿐이다.** 사유 미기재는 서명 거부(422). → **D63**

번들 해시 하나로 "이 결정이 참조한 모든 근거가 변조되지 않았다"가 검증된다. 법이 나중에 개정돼도 서명 시점 스냅샷이 그대로 재현된다.

---

## 3. 룰 5종

| rule_id | 유형 | 근거 유형 | 판정 대상 |
|---|---|---|---|
| `TAX-CREDIT-2Y` | BLOCKING | LAW | 사후관리 기간 내 처분 → 추징 |
| `LIEN-CONSENT` | BLOCKING | **CONTRACT** | 채권자 동의 없는 담보물 처분 |
| `INSURANCE-NOTIFY` | PRECONDITION | LAW | 부보 목적물 변동 통지 |
| `VAT-INVOICE` | PRECONDITION | LAW | 매각 시 세금계산서 (폐기는 제외) |
| `SAFETY-INSPECTION` | PRECONDITION | LAW | 이전 후 재검사 |

**`LIEN-CONSENT`만 `source_type: CONTRACT`인 이유:** 법령이 담보물 처분을 금지하는 게 아니라 여신거래약관이 기한이익 상실 사유로 정하는 구조다. 근거의 성격이 섞여 있다는 걸 필드로 드러냈다. 뭉뚱그리면 근거가 부정확해진다.

### 처분 시 플래그 3분류

| 분류 | 처분 시 동작 |
|---|---|
| **BLOCKING** | 처분 요청 거부(409) + 해소 조건 안내 |
| **PRECONDITION** | 체크리스트 표시, 완료 후 진행 |
| **AUTO_CLOSE** | 처분과 함께 자동 closed |

`409`를 쓰는 이유는 D38과 같다 — "권한이 없다(403)"와 "지금 상태에선 안 된다(409)"는 사용자가 할 행동이 다르고, 평가에서 권한 위반 판정에 법정 조건 미충족이 섞이면 안 된다.

---

## 4. 엔진이 강제하는 불변식

프롬프트가 아니라 **코드 구조**로 강제한다. D10이 "도구에 UPDATE 권한 자체를 주지 않는다"로 human-in-the-loop을 강제한 것과 같은 방식이다.

1. **근거 없는 룰은 로드 거부** — `law_refs`·`contract_refs`가 모두 비면 `RuleIntegrityError` (**D61**)
2. **미등록 법령 참조 거부** — `laws/`에 없는 ID를 참조하면 로드 실패
3. **경계 구간은 단정 금지** — `boundary.review_band` 안이면 `HOLD` (**D62**)
4. **사실 부족 ≠ 조건 미해당** — `INSUFFICIENT_FACTS`를 `CLEAR`와 구분 (**D62**)
5. **시점 조회 시 조용한 최신본 금지** — 없으면 예외
6. **고려하지 않은 것 명시** — 모든 결과에 `not_considered`, `disclaimer`

4번이 가장 중요하다. **"조건에 해당하지 않는다"와 "알 수 없다"는 다르다.** 사실을 모르는데 통과로 처리하면 그게 가장 위험한 버그다.

---

## 5. 도구 (Phase 2 추가분)

MVP 7종은 그대로 두고 아래를 더한다. `04_MCP_TOOLS`의 status 계약(D9·D46)을 따른다.

| 도구 | 성격 | 설명 |
|---|---|---|
| `check_disposal_blockers` | 읽기 | 처분 가능 여부 + 체크리스트 + 근거. **S9 진입점** |
| `build_evidence_bundle` | 읽기 | 법령·룰·사실 묶고 해시 산출 |
| `verify_ownership` | 읽기 | 권리관계 확인 항목별 상태 + 잔여 리스크 |
| `generate_disposal_document` | **쓰기** | 처분 승인서·진술보장서 draft. 근거 각주 자동 삽입 |

`generate_disposal_document`는 `create_po_draft`와 **완전히 같은 패턴**이다 — draft만 생성, 확정은 승인 큐에서만, 신원은 서버 주입(D23·D37). 쓰기 도구가 2종이 되지만 **승인 큐는 공유**한다(발주서·처분서·수리 증빙이 한 큐).

### `check_disposal_blockers` 출력

```json
{
  "equipment_id": "INV-L3-01",
  "verdict": "BLOCKED",              // BLOCKED | HOLD | CONDITIONAL | CLEAR
  "blockers": [{
    "rule_id": "TAX-CREDIT-2Y",
    "citations": ["조세특례제한법 제24조(통합투자세액공제)"],
    "law_refs": ["KR-STTC-24"],
    "reasoning": "취득일 2025-03-01, 처분예정 2026-08-10 → 17개월, 24개월 미충족",
    "resolve_options": ["기간 경과 대기", "추징 감수 결정(override, 사유 필수)"],
    "requires_expert_review": true
  }],
  "preconditions": [ … ], "holds": [ … ], "insufficient": [ … ],
  "not_considered": ["생산 계획·대체 설비 확보", "시장 상황·매각 타이밍", "개별 계약 특약"],
  "disclaimer": "통상 사례 기준 목업 룰. 실제 적용에는 전문가 검토가 필요하다."
}
```

---

## 6. 시나리오 (확장분)

`02_SCENARIOS`의 S1~S4는 그대로. 아래는 추가분이며 번호는 A2A 시나리오(S5~S8, QMesh 레포)와 겹치지 않게 S9부터 쓴다.

| # | 시나리오 | 패턴 | 분기 트리거 |
|---|---|---|---|
| S9 | 처분 요청 → 법정 조건 검사 → 차단 | 법정 가드레일 | `verdict == "BLOCKED"` |
| S10 | 근거 번들 → 서면 생성 → 서명 확정 | 책임 귀속 | 서명 이벤트 |
| S18 | 중고 매수 권리관계 검증 | 불완전 정보 처리 | `verdict == "PARTIAL"` |

### S9 — 처분 요청 → 차단

1. 담당자가 설비 매각 요청
2. `check_disposal_blockers` → BLOCKING 2건 + 근거 조문
3. 409 반환 + 사유·근거·해소 경로 제시

**거부하되 이유와 해소 경로를 함께 준다.** "안 됩니다"로 끝내지 않는 건 S4(미지 코드 → A/S 안내)와 같은 태도다.

### S10 — 근거 번들 → 서명

1. 실사 데이터 입력
2. `build_evidence_bundle` → 계층 1+2 묶고 해시
3. `generate_disposal_document` → 승인서·진술보장서 draft, 근거 각주 삽입
4. 팀장 승인 큐에 표시 (기존 큐 재사용)
5. 검토 → 서명 → 번들 해시 고정 → 확정

### S18 — 중고 매수 권리관계 검증

**동산은 등기가 없다.** 점유가 곧 권리 외관이라, 공장에 놓여 있고 매일 쓰고 있으면 소유자로 보인다. 운용리스는 특히 그렇다 — 담당자가 바뀌면 리스라는 사실 자체를 모르기도 한다.

| 확인 수단 | 확인 범위 | 한계 |
|---|---|---|
| 동산담보등기 조회 | 법인·상호등기 사업자의 담보 설정 | **리스는 등기 대상 아님** |
| 리스사 명판·자산 스티커 | 물리적 확인 | 제거 가능 |
| 취득 세금계산서 원본 | 매입 사실 | 리스면 애초에 없음 |
| 고정자산대장 등재 | 자산 계상 확인 | 운용리스는 원래 미계상 |
| 제조사 시리얼 조회 | 최초 출하처 | 협조 여부에 달림 |

```json
{
  "verdict": "PARTIAL",
  "verified":   ["동산담보등기 조회 — 설정 없음", "세금계산서 원본 확인"],
  "unverified": ["리스 여부 — 제조사 조회 미회신"],
  "residual_risk": "리스 물건일 가능성 배제 불가",
  "mitigation": "진술보장 + 손해배상 특약으로 계약상 배분 권고"
}
```

**시스템이 "안전합니다"라고 말하지 않는다.** 무엇을 확인했고 무엇이 남았는지를 말한다. `PARTIAL`은 `VERIFIED`로 승격될 수 없다.

---

## 7. 데이터 (Phase 2 추가분)

`05_DB_SCHEMA`의 11개 테이블에 더한다.

```
equipment 확장
  tax_credit_applied, acquired_at, has_lien, lien_creditor,
  lien_consent_ref, policy_id, safety_inspection_target,
  last_inspection_date, status

신규 테이블
  law_refs     법령 스냅샷 (append-only)      ※ 파일(git) + SQLite 적재
  rules        해석 룰 (rule_version 관리)
  decisions    서명 레코드 (bundle_hash, override, override_reason)
  flags        법정 조건 플래그 (발생 → 이행 → 해소)
```

`law_refs`·`rules`를 **파일로 두고 git에 커밋**하는 이유: 개정 이력이 커밋 로그로 남고 누가 언제 바꿨는지 자동 추적된다. 별도 이력 관리 코드가 필요 없다. 실행 시 SQLite에 적재해 조회한다. D19가 매뉴얼 원본을 manifest로 관리한 것과 같은 태도다.

`decisions.reviewed_by`는 `users` FK (D41), ID 저장 (D36), 시각은 UTC (D39).

---

## 8. 순서 · 단계

### 순서 제약 (범위는 넓히되 이건 지킨다)

- [ ] **S1~S4 관통과 완료 기준 5개가 먼저** (`00_MVP_SCOPE` 평가표)
- [ ] **M1 크리티컬 패스** — `error_codes` 승인, `related_parts` 검수
- [ ] 그다음 F1 — 나머지가 전부 이 위에 얹힌다

### 순서

| 단계 | 내용 |
|---|---|
| **F1** 근거 계층 | 법령 스냅샷 수집 · 룰 5종 · 엔진 · 단위 테스트 |
| **F2** 처분 차단 | `check_disposal_blockers` → S9 |
| **F3** 서명 | 번들·서면 생성·승인 큐 확장 → S10 |
| **F4** 취득 검증 | `verify_ownership` → S18 |

F1이 가장 크고 나머지는 그 위에 얇게 얹힌다. **F1만 해도 "근거를 남기는 에이전트"라는 서사는 성립한다.**

### 법령 수집 체크리스트

- [ ] law.go.kr OPEN API 이용 신청 → `LAW_API_KEY`
- [ ] 6개 조문 수집 → `text`·`effective_from`·`text_hash` 채우기
- [ ] **조문 번호·제목 검증** — 개정으로 바뀌므로 응답과 대조
- [ ] 하위 법령 추가 — 안전검사 대상 기계 목록(시행령·고시), 사후관리 기간(시행령)
- [ ] 개정 감지 → 영향 룰 역추적 → 사람 서명 흐름

> **조문 원문을 손으로 타이핑하지 않는다.** 그 순간 "출처 있는 사실"이 아니라 "누가 적은 텍스트"가 되어 계층 1의 존재 이유가 무너진다.

---

## 9. 한계

- 룰은 **통상 사례 기준 목업**이다. 실제 세무·법무 판단을 대체하지 않는다.
- 경계를 어디로 잡을지 **자체가 해석**이다. `boundary.note`에 근거를 남긴다.
- `requires_expert_review: true`인 룰은 UI에서 전문가 확인 안내를 함께 표시한다.
- 시장가·감정가 추정은 공개 데이터가 부족하다 → `12_MAINT_VALUE §4` 참조, 추정치 고지 필수 (**D65**).

---

## 10. 확장 데이터 — 기한 · 사고 · 위험 프로파일

> 룰 카탈로그를 만들면서 드러난 **자체 공백**이다. 아래 넷은 새 아이디어가 아니라
> **이미 있는 룰과 시나리오가 요구하는데 저장할 자리가 없는 것들**이다.

### 10-1. 왜 필요한가 — 기존 룰이 요구하는데 자리가 없다

| 요구하는 쪽 | 무엇이 없나 |
|---|---|
| `TAX-CREDIT-2Y` (§3) | `months_since_acquisition` 을 쓰고 `review_band [22, 26]` 경계까지 있는데, **기한이 다가오는 걸 미리 알 방법이 없다.** 물어봐야만 안다 — 24개월을 하루 넘겨 팔면 추징이다 |
| `SAFETY-INSPECTION` (§3) | `last_inspection_date` 를 요구한다. 검사 주기는 설치 후 3년·이후 2년이고 **미이행이면 사용 자체가 불가**인데 추적 장치가 없다 |
| `12 §1` 자산가치 | *"충돌·사고 이력은 마이너스다 — 베드·주축 정렬이 영구히 틀어지면 정밀도가 회복되지 않는다"* 고 써 뒀는데 **사고를 기록할 테이블이 없다.** `error_history` 는 에러코드 트립이지 물리적 사고가 아니다 |
| `verify_ownership` (§5·§6 S18) | 9개 카테고리를 확인한 **결과를 남길 자리가 없다.** 매번 처음부터 다시 확인하게 된다 |

### 10-2. 신규 테이블 4종

```
deadlines          기한 추적 — 시점을 관리한다
  deadline_id, decision_id, type, due_date, status, reminder_sent_at

incidents          물리적 사고 이력 (error_history 와 별개)
  incident_id, equipment_id, type, occurred_at, book_value_at_loss

ownership_checks   권리관계·실사 확인 항목 (S18 결과 보존)
  check_id, equipment_id, check_item, status, evidence_ref, checked_at

risk_profile       건물 단위 속성
  building_id, fire_handling, hazmat_volume, power_capacity,
  product_type, risk_grade, risk_grade_updated_at
```

**`risk_profile` 이 건물 단위인 이유:** `equipment.location` 은 `"3번 조립라인 반송 컨베이어"`
같은 **문자열**이라 건물 자체의 조건을 담을 자리가 없다. 그런데 `SAFETY-INSPECTION` 대상 판정과
`12 §6` 실사 체크리스트의 '법정 요건' 카테고리(안전검사·안전인증·환경 규제)는 **건물 조건에
걸린다.** 넷 중 내부 활용도가 가장 낮으므로 **후순위**로 둔다.

**`deadlines` 와 `flags`(§3)는 성격이 다르다** — `flags` 는 *상태*(발생 → 이행 → 해소)를,
`deadlines` 는 *시점*을 관리한다. 같은 사안이 양쪽에 각각 걸린다: `LIEN-CONSENT` 는 flag,
"세액공제 사후관리 24개월"은 deadline.

### 10-3. 도구 3종 추가

| 도구 | 성격 | 무엇을 푸는가 |
|---|---|---|
| `track_deadlines` | 읽기 | **가장 값이 크다.** 기한 임박 항목 조회 → `TAX-CREDIT-2Y` 경계 구간(22~26개월)에 들어가기 전에 알려 준다. 지금은 처분을 요청해야만 BLOCKED 를 알게 된다 |
| `detect_law_revision` | 읽기 | 해시 비교 + 영향 룰 역추적. **`fetch_laws.py` 의 `check_revisions()` 가 이미 하는 일**을 도구로 노출하는 것이라 새로 만들 로직이 거의 없다 |
| `assess_risk_grade` | 읽기 | 위험 프로파일 → 등급 + 변동 판정 |

`verify_ownership`(§5)은 그대로 재사용한다 — `ownership_checks` 가 생겨도 **판정 스키마
(`PARTIAL` / `VERIFIED` 구분)는 바꾸지 않는다.**

### 10-4. 기존 구조와의 접점

- **`detect_law_revision` 은 계층 1 append-only 가 실제로 작동하는 지점이다.** §2가 *"왜
  수정 불가인가"* 였다면 이건 *"그래서 개정될 땐 어떻게 하는가"* 의 답이다 — 새 레코드를
  쌓고 이전 것에 `effective_to` 를 찍는다. 자동 반영하지 않고 `pending_revisions` 로 넘겨
  사람 서명을 받는 흐름은 `fetch_laws.py` 에 이미 있다.
- **`incidents` 는 `12 §1` 의 감점 신호를 완성한다.** 지금은 반복 고장(`repeated`)만 감점
  근거인데, 충돌·사고는 그보다 무겁고 회복이 안 되는 종류다.
- **`ownership_checks` 가 있어야 `PARTIAL` 이 의미를 갖는다.** 무엇을 확인했고 무엇이
  남았는지를 다음 사람이 이어받을 수 있어야 한다 — 안 남기면 매번 처음부터다.

### 10-5. 순서

`§8` 의 F1~F4 **뒤**에 온다. 넷 다 F1(근거 계층)이 없으면 근거를 붙일 수 없다.

| 단계 | 내용 |
|---|---|
| **F5** 기한·사고 | `deadlines` · `incidents` + `track_deadlines`. **F1~F4 중 가장 값이 큰 후속** — 기존 룰이 이미 요구하는 것을 채운다 |
| **F6** 실사 보존·위험 | `ownership_checks` · `risk_profile` + `assess_risk_grade` · `detect_law_revision` |

---

## 관련 문서

| 목적 | 문서 |
|---|---|
| 보전지표 · 수리 이력 · 중고 거래 배경 | `12_MAINT_VALUE` |
| 왜 이렇게 정했는가 | `10_DECISIONS` D58~D65 · **D67** |
| 지금 만들지 않는 것 | `07_BACKLOG` P22~P27 (순서 제약) |
| 선행 범위 | `00_MVP_SCOPE` |
