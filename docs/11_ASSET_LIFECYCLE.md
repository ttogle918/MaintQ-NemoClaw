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

> **이 예시는 수집 *전* 의 형태다.** Sprint 7 MQ-701 실수집 이후 `KR-STTC-24` 의 실제 값은
> `fetch_status:"FETCHED"` · `text` 3,574자 · `effective_from:"2026-01-01"` · `text_hash` 채워짐이다.
> 형태를 남겨 두는 이유: **새로 등록하는 조문은 언제나 이 상태에서 시작**하고,
> 손으로 원문을 채우지 않는다는 규약이 그 순간에 걸린다.

- **조 단위로 쪼갠다.** 문서 통짜 저장은 인용 앵커를 만들 수 없다. 청킹과 형태는 같지만 목적이 검색이 아니라 **인용**이라는 게 요점이다.
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
  "decision_id": "DEC-0001",            // 채번 규약 `DEC-%04d`
  "evidence_bundle": {                  // ★ 3키가 아니라 **5키** (D83) — 정본은 04 §14
    "laws":      [{"law_ref_id": "KR-CIVIL-388", "effective_from": "2026-03-17",
                   "text_hash": "sha256:caf918cb…"}],
    "rules":     [{"rule_id": "LIEN-CONSENT", "rule_version": 2,
                   "rule_hash": "sha256:9630e235…"}],   // ← rule_hash (W6)
    "evaluated": [{"rule_id": "LIEN-CONSENT", "rule_version": 2,
                   "verdict": "TRIGGERED", "law_refs": ["KR-CIVIL-388"]},
                  {"rule_id": "SAFETY-INSPECTION", "rule_version": 2,
                   "verdict": "CLEAR", "law_refs": ["KR-OSHA-93"]}],   // ← 평가한 전 룰 (W7)
    "contracts": [{"contract_ref": "여신거래기본약관", "text_hash": null,
                   "hash_fixed": false, "note": "…"}],  // ← 해시로 고정되지 않는다
    "facts":     {"asset_id": "AST-L3-CONV", "acquired_at": "2020-02-10", "has_lien": true}
  },
  "bundle_hash": "sha256:9d1e…",
  "reviewed_by": "mgr-01",              // users FK (D41), ID 저장 (D36)
  "signed_at": "2026-08-04T14:22:30Z",  // UTC (D39)
  "override": true,
  "override_reason": "세액공제 추징 감수 — 신규 라인 일정 우선"
}
```

**5키가 3키에서 늘어난 이유** (Sprint 6 reviewer W6·W7):

- **`rule_hash`** — 계층 1은 `text_hash` 로 잠겨 있는데 계층 2는 `rule_version` **숫자로만** 잠겨
  있었다. 같은 버전 안에서 룰 본문이 in-place 로 바뀌어도 번들 해시가 그대로였다.
- **`evaluated[]`** — CLEAR 자산은 `laws`·`rules` 가 빈 배열이라 *"근거를 조회한 결과 해당 없음"* 과
  *"근거를 아예 안 봤다"* 가 번들에서 구분되지 않았다. **빈 근거도 사실이므로** 해시는 그대로 내고,
  무엇을 평가했는지는 이 키가 말한다.
- **`contracts[]`** — 계약 근거는 법제처 수집 대상이 아니라 원문이 저장소에 없다. `laws[]` 에 섞으면
  `LIEN-CONSENT` 가 걸린 자산의 번들이 **구조적으로 영원히 불가능**해진다. 그래서 분리하고
  `hash_fixed:false` 로 **고정되지 않았음을 드러낸다** — 숨기는 것보다 낫다.

**`override`가 핵심이다.** 추징을 감수하고 파는 건 정당한 경영 판단이다. 시스템은 막지 않는다 — **막았다는 사실과 뚫은 사람을 기록할 뿐이다.** 사유 미기재는 서명 거부(422). → **D63**

번들 해시 하나로 "이 결정이 참조한 모든 근거가 변조되지 않았다"가 검증된다. 법이 나중에 개정돼도 서명 시점 스냅샷이 그대로 재현된다.
번들 조립·해시 산출의 정확한 규약(정준 직렬화 4조건, `built_at` 을 번들 밖에 두는 이유)은 `04_MCP_TOOLS §14` 가 정본이다.

### 계층 1 기입은 2단계로 기록한다 (D75)

계층 1은 append-only라 **잃은 원문을 복구할 방법이 없다.** 그래서 개정본 덮어쓰기(`force=True`)는
**기입하기 전에** `pending_revisions/` 에 직전 원문 스냅샷을 먼저 확보한다.

| `applied` | 뜻 |
|---|---|
| `null` | 반영 시도 없음 (개정 감지만 됨) |
| `"intent"` | **기입 직전** — 스냅샷은 확보됐고 파일 기입은 아직 |
| `"confirmed"` | 기입 성공 후 승격 |

기입 성공 후 `_confirm_pending_revision` 이 **상태 3필드만** 전이한다(스냅샷 payload 불변).
Sprint 7 서명 큐는 **`requires_signature == true`** 로 필터한다.

- **순서를 반전하면(기입 후 기록)** 그 사이에 죽었을 때 **덮어쓴 원문의 직전 스냅샷이 통째로 사라진다.** "적용됨이라고만 남은 거짓 기록"보다 **원본 소실이 나쁘다.** 2단계는 기록이 항상 먼저 남고 상태만 정직하지 않은 채 멈춘다 — D55(재생본에 `replay` 표식)와 같은 "실패 사실도 남긴다" 태도다.
- **정체성 대조 키(`article`·`title`)가 응답에 없거나 비어 있으면 불일치와 동일하게 중단**한다. 한 문장으로 줄이면 **"대조할 값이 없는 것은 대조를 통과한 것이 아니다."** 단 선택적 필드(`effective_from`·`promulgation_no` 등)는 대상이 아니다 — 과잉 게이트면 Sprint 7 수집이 통째로 막힌다.

---

## 3. 룰 5종

> 🔄 **D77·D78 정합 반영분.** `required_facts` 는 **트리거·경계가 실제로 읽는 필드만** 담는다.
> 정합 전에는 5종 중 3종이 자기 트리거와 어긋나 있었고, 그 결과 처분 판정 5종 중
> `CONDITIONAL`·`CLEAR` 가 **어떤 시드로도 도달 불가**였다. 아래 `rule_version` 은 그 개정의 흔적이다.

| rule_id | 유형 | 근거 유형 | 판정 대상 | `required_facts` (현행) | `rule_version` |
|---|---|---|---|---|---|
| `TAX-CREDIT-2Y` | BLOCKING | LAW | 사후관리 기간 내 처분 → 추징 | `tax_credit_applied` · `acquired_at` · `disposal_date` | 1 |
| `LIEN-CONSENT` | BLOCKING | **CONTRACT** | 채권자 동의 없는 담보물 처분 | `has_lien` · `lien_creditor` | **2** |
| `INSURANCE-NOTIFY` | PRECONDITION | LAW | 부보 목적물 변동 통지 | **`insured`** | **3** |
| `VAT-INVOICE` | PRECONDITION | LAW | 매각 시 세금계산서 (폐기는 제외) | `disposal_mode` · **`vat_invoice_issued`** | **2** |
| `SAFETY-INSPECTION` | PRECONDITION | LAW | 이전 후 재검사 | `safety_inspection_target` · `disposal_mode` | **2** |

**무엇이 바뀌었나 (4종)**

| rule_id | 무엇이 틀려 있었나 | 어떻게 고쳤나 |
|---|---|---|
| `LIEN-CONSENT` | `lien_consent_ref` 를 `required_facts` 에 넣고 **동시에 `is_null` 로 트리거**했다 — 값이 없으면 `INSUFFICIENT_FACTS`, 있으면 트리거 안 함. **논리적으로 절대 발화하지 않는 룰** | `required_facts` 에서 빼고 `has_lien` **불리언**으로 판정 (D77 ⓐ) |
| `INSURANCE-NOTIFY` | 트리거가 읽는 `risk_grade_changed` 를 선언하지 않은 채, 원천이 F6 `risk_profile`(범위 밖)인 `risk_grade_before/after` 를 요구했다 | `assets.insured` 신설 + 트리거 첫 분기를 `policy_id is_not_null` → **`insured eq true`** (D78) |
| `VAT-INVOICE` | 트리거가 읽는 `vat_invoice_issued` 를 선언하지 않고, 자산 사실이 아닌 **거래 사실**(`sale_amount`·`buyer_biz_no`)을 요구했다 | 거래 사실을 빼고 `vat_invoice_issued` 를 선언. 이 값은 `build_facts` 가 **명시적 근거와 함께** 채운다(precheck 는 거래 성립 전이므로 미발행) |
| `SAFETY-INSPECTION` | — (트리거 정합) | `disposal_mode` 를 명시 선언 |

**세 원칙 (D77)**: ① **부재 자체가 트리거 조건인 필드는 선언하지 않는다**(선언하면 논리적으로 발화 불가)
② **시스템에 원천이 없는 사실은 요구하지 않는다** ③ 트리거가 읽지 않고 메시지·체크리스트에만 쓰는 사실도 요구하지 않는다.

**`evaluate_rule` 은 `required_facts` 미충족을 가장 먼저 `INSUFFICIENT_FACTS` 로 반환**하므로,
어긋난 룰 3종이 **모든 자산에서 항상 발동**해 우선순위상 자산 전체의 판정을 마비시켰다.
**D61 이 못 잡는 구멍**이다 — D61 은 "근거(법령)가 있는가"만 보고 **"요구하는 사실에 원천이 있는가"는 보지 않는다.**
D62 가 지키려던 것은 *실제로 모르는 사실*이지 **애초에 알 수 없게 설계된 사실**이 아니다 — 후자는 정직이 아니라 결함이다.

**회귀 2종을 `test_rules.py` 에 함께 둔다:**
- **발화 가능성(satisfiability, D77)** — 어떤 사실 조합으로도 `TRIGGERED` 될 수 없는 룰은 실패
- **해제 가능성(clearability, D78)** — 어떤 사실 조합으로도 해제될 수 없는 룰은 실패

로드 시점 검사가 아니라 회귀인 이유: "부재가 트리거인 필드"는 정당하게 미선언되므로 `load_rules()` 가
기계적으로 판별할 수 없다 — 발화 가능성은 사실 조합을 실제로 넣어 봐야 안다.

**`LIEN-CONSENT`만 `source_type: CONTRACT`인 이유:** 법령이 담보물 처분을 금지하는 게 아니라 여신거래약관이 기한이익 상실 사유로 정하는 구조다. 근거의 성격이 섞여 있다는 걸 필드로 드러냈다. 뭉뚱그리면 근거가 부정확해진다.

### 처분 시 플래그 3분류

| 분류 | 처분 시 동작 |
|---|---|
| **BLOCKING** | 처분 요청 거부(409) + 해소 조건 안내 |
| **PRECONDITION** | 체크리스트 표시, 완료 후 진행 |
| **AUTO_CLOSE** | 처분과 함께 자동 closed |

`409`를 쓰는 이유는 D38과 같다 — "권한이 없다(403)"와 "지금 상태에선 안 된다(409)"는 사용자가 할 행동이 다르고, 평가에서 권한 위반 판정에 법정 조건 미충족이 섞이면 안 된다.

### verdict 5종 → HTTP (D79·D71)

`BLOCKED` · `HOLD` · `INSUFFICIENT_FACTS` → **409** / `CONDITIONAL` · `CLEAR` → **200** /
룰 카탈로그 미적재 → **503** / 없는 자산 → 404 / enum 위반 → 422.
우선순위는 `blockers > holds > insufficient > preconds > CLEAR`.
엔드포인트는 `POST /api/assets/{id}/disposal/precheck`(**무저장**)이고 **역할 게이트가 없다** —
전체 계약은 `06_REPO_API §2.5` 가 정본이다.

**★ `CLEAR` 는 `SCRAP`·`TRANSFER` 에서만 나온다 (D78 부수 확정).**
`VAT-INVOICE` 가 `disposal_mode == "SALE"` 에서 `vat_invoice_issued=False` 를 확정 사실로 받으므로
**매각 precheck 은 정의상 최소 `CONDITIONAL`** 이다. 실측(`AST-L3-LIFT`): `SALE=CONDITIONAL` / `SCRAP=CLEAR` / `TRANSFER=CLEAR`.
**결함이 아니라 도메인 사실이다** — 이걸 버그로 보고 `VAT-INVOICE` 를 손대면 세금계산서 발행 의무가 판정에서 사라진다.

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

## 5. 도구 (확장분)

코어 7종은 그대로 두고 아래를 더한다. `04_MCP_TOOLS`의 status 계약(D9·D46)을 따르며,
**입출력 계약의 정본은 `04_MCP_TOOLS §8~§15`** 다(여기서 복제하지 않는다).
노출은 `MAINTQ_TOOLS_PROFILE=full` 에서만 (D69).

| 도구 | 성격 | 설명 | 계약 | 상태 |
|---|---|---|---|---|
| `check_disposal_blockers` | 읽기 | 처분 가능 여부 + 체크리스트 + 근거. **S9 진입점** | `04 §8` | 구현 |
| `verify_ownership` | 읽기 | 실사 9카테고리 항목별 상태 + 잔여 리스크 | `04 §9` | 구현 |
| `build_evidence_bundle` | 읽기 | 법령·룰·사실 묶고 해시 산출 (**5키** — D83) | `04 §14` | 구현 |
| `generate_disposal_document` | **쓰기** | 처분 승인서·진술보장서 draft. 근거는 번들에서 치환 | `04 §15` | **구현 (Sprint 7 · F3 완료)** |

`generate_disposal_document`는 `create_po_draft`와 **완전히 같은 패턴**이다 — draft만 생성, 확정은 승인 큐에서만, 신원은 서버 주입(D23·D37).
**쓰기 도구는 이제 2종이고, 승인 큐는 공유한다** — `GET /api/approvals` 가 `kind`(`po`|`disposal`|`repair`)로
발주서·처분서·수리 증빙을 한 큐에 담는다 (D85, `06 §2.7`). `repair` 는 현재 항상 0건(Sprint 8).

> ⚠ *"확장 도구에는 쓰기가 하나도 없다"* 는 이 문서의 옛 서술은 **거짓이 됐다.** 유지된 것은
> **UPDATE/DELETE 권한이 없다**는 사실이며(TEMP TRIGGER), 바뀐 것은 "쓰기가 없다"가 아니라
> **"쓰기가 draft 로 한정된다"** 이다. `build_evidence_bundle` 은 지금도 아무것도 쓰지 않는다.

### 🔴 데모·수동 체크리스트 재현 파라미터 — **`disposal_date` 없이는 재현되지 않는다**

verdict 는 `disposal_mode` 뿐 아니라 **`disposal_date` 에 따라 갈린다**(`TAX-CREDIT-2Y` 가
`months_since_acquisition` 을 읽고, 날짜가 없으면 D62 대로 **오늘로 대체하지 않고** 사실 부족으로 남긴다).
아래는 시드 DB 실측값이다 — 화면 시연 시 이 날짜를 그대로 넣어야 한다.

| 자산 | mode | `disposal_date` | verdict | 비고 |
|---|---|---|---|---|
| `AST-L3-CONV` | SALE | **`2021-06-01`** | `BLOCKED` (**blockers 2건**) | 체크리스트 ⓐ 가 요구하는 "BLOCKED 2건"은 **이 날짜에서만** 나온다 |
| `AST-L3-CONV` | SALE | `2026-09-01` | `BLOCKED` (blockers **1건**) | 세액공제 2년이 이미 지나 `TAX-CREDIT-2Y` 가 해제된다 |
| `AST-L3-CONV` | SALE | *(미입력)* | `BLOCKED` (blockers 1 · insufficient 1) | 날짜 부족이 `insufficient` 로 정직하게 남는다 |
| `AST-L4-WRAP` | SALE | **`2008-04-01`** | **`HOLD`** | 체크리스트 ⓑ("전문가 검토")는 **이 날짜에서만** 나온다 — 경계 구간 `review_band` |
| `AST-L4-WRAP` | SALE | `2026-09-01` | `CONDITIONAL` | ⚠ **HOLD 가 아니다.** 이 날짜로 시연하면 ⓑ 가 재현되지 않는다 |
| `AST-L4-DUST` | SALE | `2026-09-01` | `INSUFFICIENT_FACTS` | ⓒ — `tax_credit_applied` 가 NULL(모름) |
| `AST-L3-LIFT` | SCRAP | `2026-09-01` | `CLEAR` | ⓓ — **`CLEAR` 는 SCRAP·TRANSFER 에서만** 나온다 (D78 부수 확정) |

> ⚠⚠ **`acquired_at` 은 시드 실행 연도 기준 상대값이다.** `data/seed.py:1119` 가
> `date(today.year - age_years, month, day)` 로 만든다 — **다른 해에 재시드하면 위 날짜의 판정이
> 달라진다.** 위 표는 **2026년에 시드한 DB** 기준이며(`AST-L3-CONV` = `2020-02-10`,
> `AST-L4-WRAP` = `2006-06-01`), 재현이 안 되면 먼저 `SELECT asset_id, acquired_at FROM assets` 로
> 실제 취득일을 확인하고 경계(24개월 · `review_band [22,26]`)를 다시 계산할 것.
> ⛔ 재현이 안 된다고 룰이나 시드를 고치지 말 것 — **날짜 의존성 자체가 D62 가 만든 설계**다.

### `check_disposal_blockers` 출력

```json
{
  "status": "ok",
  "asset_id": "AST-L3-CONV",          // ★ 대상은 인버터가 아니라 호스트 설비다 (D68)
  "evaluated_at": "2026-08-09",
  "verdict": "BLOCKED",               // BLOCKED | HOLD | INSUFFICIENT_FACTS | CONDITIONAL | CLEAR (D79)
  "blockers": [{
    "rule_id": "TAX-CREDIT-2Y", "rule_version": 1,
    "label": "세액공제 사후관리 기간",
    "verdict": "TRIGGERED", "disposal_type": "BLOCKING",
    "citations": ["조세특례제한법 제24조(통합투자세액공제)"],
    "law_refs": ["KR-STTC-24"],
    "message": "…",
    "reasoning": "취득일 2025-03-01, 처분예정 2026-08-10 → 17개월, 24개월 미충족",
    "resolve_options": ["기간 경과 대기", "추징 감수 결정(override, 사유 필수)"],
    "requires_expert_review": true,
    "missing_facts": []
  }],
  "preconditions": [ … ], "holds": [ … ], "insufficient": [ … ],
  "disposal_mode": "SALE", "disposal_date": "2026-08-10",   // 판정 조건을 되싣는다 —
                                                            //   같은 자산도 mode·날짜로 판정이 갈린다
  "evidence_completeness": "LAW_TEXT_PENDING",              // COMPLETE | LAW_TEXT_PENDING
  "not_considered": ["생산 계획·대체 설비 확보", "시장 상황·매각 타이밍", "개별 계약 특약"],
  "disclaimer": "통상 사례 기준 목업 룰. 실제 적용에는 전문가 검토가 필요하다. 인용 조문의 원문은 아직 수집되지 않았으며 인용은 조문 번호·제목 기준이다."
}
```

**입력은 `asset_id` 또는 `equipment_id` 둘 중 하나**다. `equipment_id` 는 `equipment.asset_id` 로
해석되는 **입력 편의**일 뿐 판정 대상은 언제나 자산이다 — 호스트 자산이 없는 인버터(`INV-L1-01` 분전반)는
`no_host_asset` 이며 **"판정 결과 문제 없음"이 아니다.**

**`evidence_completeness` 는 원천이 둘이다** — `verdict`·버킷·인용은 **정본 파일**(`data/rules/{laws,rules}/*.json`)에서,
완전성 판정과 카탈로그 적재 게이트는 **DB 사본**에서 온다 (D60). 파일과 DB 를 섞어 판정을 조립하지 않는다.

> **현재값 (Sprint 7 MQ-701 실수집 이후)** — 위 출력 예시의 `evidence_completeness:"LAW_TEXT_PENDING"` 과
> disclaimer 의 "원문은 아직 수집되지 않았으며"는 **수집 전 상태**를 보인 것이다. **2026-08-13 부로
> 조문 8건이 전부 `FETCHED`** 이므로(마지막 `PENDING` 이던 `KR-CITA-ENF-31` 사람 승인 완료),
> **실 DB 정상값은 `COMPLETE`** 이며 disclaimer 에 `_LAW_PENDING_NOTE` 접미사가 붙지 않는다.
> 근거: `../data/analysis/law_fetch.md`
>
> ⚠ **이 경로가 죽은 것은 아니다** — 새 조문을 등록했는데 아직 안 받았을 때, 개정으로
> `pending_revisions` 가 열렸을 때 다시 발화한다. 회귀 `law_fetch_contract` 가 합성 응답으로 덮는다.
> `LAW_TEXT_PENDING` 경로는 **새 조문 등록 직후·개정 대기·정체성 대조 실패** 때 다시 발화한다.

---

## 6. 시나리오 (확장분)

`02_SCENARIOS`의 S1~S4는 그대로. 아래는 추가분이며 **S5~S8은 비워 두고 S9부터** 번호를 쓴다.

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

### S10 — 근거 번들 → 서명 (**Sprint 7 구현 · 실제 흐름**)

1. 자산 화면에서 처분 사전판정 (`POST /api/assets/{id}/disposal/precheck` — 무저장, D71)
2. **"이 자산의 처분서 초안" 버튼 → `/technician?prefill=…` 로 이동**해 채팅 컴포저에 문장을 채운다.
   ⛔ **자동 전송하지 않는다** — 사람이 무엇을 요청하는지 보고 눌러야 한다
3. 에이전트가 `generate_disposal_document` 호출 → 내부에서 `build_evidence_bundle`(5키·해시) →
   `decisions` 에 **`state='draft'` INSERT** (D10·D81)
4. **자산 화면의 "이 자산의 처분서 초안" 목록에서 `POST /api/decisions/{id}/submit`** → `pending`
5. 통합 승인 큐 `GET /api/approvals?kind=disposal` 에 표시 (D85)
6. 팀장이 검토 → `POST /api/decisions/{id}/sign` → **번들 재산출·해시 대조(D84)** → `signed`

> **⚠ 요청은 prefill(채팅), 제출은 자산 화면이다.**
> `generate_disposal_document` 는 **에이전트만** 부를 수 있어(D15·D10) 화면 버튼이 도구를 직접 못 부른다.
> 그리고 **`decision_card` block 은 만들지 않았다** — block 은 `safety`·`po_card`·`citation` **3종 고정**이
> 계약이다(D14·D22). 4번째 타입을 늘리는 것은 계약 변경이므로, `draft → pending` 구간을
> 자산 화면이 메운다. 신규 API 0 · 신규 SSE 소비 0.
> 기록: `06 §2.1`(초안 요청 경로) · `06 §2.6`(전이 API).

> **`build_evidence_bundle` 을 에이전트가 따로 부를 필요는 없다** — 3번에서 함수로 직접 호출된다.
> 번들 실패(`law_text_unavailable`·`asset_modified`·`asset_disappeared`)는 **그대로 전파되고
> draft 는 만들어지지 않는다.** 해시할 근거가 없는 서류는 계층 3의 존재 이유가 없기 때문이다.

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

## 7. 데이터 (확장분)

기존 코어 11개 테이블에 **7개를 더해 총 18개**다 (`05_DB_SCHEMA §11~§17` 이 정본).

```
assets  신규 ★ — 법정 조건 사실은 설비(인버터)가 아니라 자산에 붙는다 (D68)
  asset_id, name, category, line_id, building_id, status,
  acquired_at, acquisition_cost, book_value, cumulative_repair_cost,
  tax_credit_applied, has_lien, lien_creditor, lien_consent_ref,
  insured ★, policy_id, safety_inspection_target,
  last_inspection_date, inspection_valid_until,
  last_overhaul_at, controller_generation, parts_eol_flag

equipment 확장 — `asset_id` 1개뿐 (nullable FK)
  asset_id      ← 이 인버터가 구동하는 호스트 설비. NULL = 호스트 없음(분전반 등)

신규 테이블
  law_refs        법령 스냅샷 (append-only)      ※ 파일(git)이 정본 + SQLite 조회용 사본
  rules           해석 룰 (rule_version 관리)     ※ 위와 동일
  decisions       서명 레코드 (bundle_hash, override, override_reason)
  flags           법정 조건 플래그 (발생 → 이행 → 해소)
  repair_records  수리 증빙 (서명, append-only) — `12 §9`
  residual_curve  연차 버킷별 잔가율 (목업, D65·D74) — `12 §4`
```

> 🔄 **당초 "equipment 확장"이라 썼던 것을 D68 이 바로잡았다.**
> 처분·취득·자산가치의 대상은 인버터가 아니라 **인버터가 구동하는 호스트 설비**다 — 실측(중진공
> 중고설비 16,011건 중 인버터 **4건** / 공작기계 7,048건). `§1` 이 처분 서사의 근거로 든
> "수명 20~30년 · 신품 납기 수개월~1년"도 공작기계 특성이지 인버터가 아니다.
> **`equipment` 에 붙는 것은 `asset_id` 하나뿐**이고, 법정 조건 사실 컬럼은 전부 `assets` 로 갔다.
> 제약 3가지: ⓐ **기존 도구 7종의 계약·`equipment_id` 는 불변** ⓑ S3 반복고장 판정은 **인버터 단위 유지**
> (에러코드가 인버터의 것이므로 — 자산 단위는 *집계*만) ⓒ 호스트가 없는 인버터는 `asset_id` **NULL 허용**.

### `assets.insured` — 한 컬럼이 두 질문을 겸하면 안 된다 (D78)

`policy_id` 한 컬럼이 "부보돼 있는가"와 "증권 번호가 무엇인가"를 겸하고 있었다.
그래서 **"확인된 미부보"를 표현할 자리가 없었다** — 값이 있으면 항상 `TRIGGERED`, 없으면
`required_facts` 누락으로 `INSUFFICIENT_FACTS`. 즉 **`CLEAR` 가 어떤 사실 조합으로도 도달 불가**였다.

| `insured` | 뜻 | 판정 |
|---|---|---|
| `NULL` | **모름** | `INSUFFICIENT_FACTS` (미부보로 읽지 않는다 — D62) |
| `0` | **확인된 미부보** | 룰 미발화. 단 `verify_ownership` 은 무보험 위험을 `residual_risk` 에 남긴다 |
| `1` | 부보 | `INSURANCE-NOTIFY` 발화 (통지 의무) |

`policy_id` 는 **증권 식별자로만** 남는다.
`required_facts=[]` 로 비우는 안을 버린 이유: 키 부재를 "미부보"로 읽게 되어 "모른다"와 "없다"가 다시 섞인다.
이건 D77 ⓐ(`LIEN-CONSENT` 가 `has_lien` 불리언을 따로 둔 것)의 **거울상**이다.

`law_refs`·`rules`를 **파일로 두고 git에 커밋**하는 이유: 개정 이력이 커밋 로그로 남고 누가 언제 바꿨는지 자동 추적된다. 별도 이력 관리 코드가 필요 없다. **파일이 정본이고 SQLite 는 조회용 사본**이다 (D60) — 판정(`verdict`·인용)은 파일에서, 적재 게이트와 `fetch_status` 조회는 DB 사본에서 온다. 두 사본이 어긋나면 `data/seed.py` 자가검증 ⑬⑭ 가 먼저 잡는다. D19가 매뉴얼 원본을 manifest로 관리한 것과 같은 태도다.

`decisions.reviewed_by`는 `users` FK (D41), ID 저장 (D36), 시각은 UTC (D39).

---

## 8. 순서 · 단계

### 순서 제약 (범위는 넓히되 이건 지킨다)

- [ ] **S1~S4 관통과 완료 기준 5개가 먼저** (`00_MVP_SCOPE` 평가표)
- [ ] **M1 크리티컬 패스** — `error_codes` 승인, `related_parts` 검수
- [ ] 그다음 F1 — 나머지가 전부 이 위에 얹힌다

### 순서

| 단계 | 내용 | 상태 |
|---|---|---|
| **F1** 근거 계층 | 법령 스냅샷 수집 · 룰 5종 · 엔진 · 단위 테스트 | **완료** (Sprint 6·7). 조문 원문 **6/7 수집** — 남은 1건은 사람 승인 대기 |
| **F2** 처분 차단 | `check_disposal_blockers` → S9 | **완료** (Sprint 6). REST `POST /precheck` 포함 (D71) |
| **F3** 서명 | 번들·서면 생성·승인 큐 확장 → S10 | **완료 (Sprint 7)** — `build_evidence_bundle`(5키·D83) · `generate_disposal_document`(draft INSERT·D81) · `/api/decisions` 제출·서명·반려(D84) · 통합 큐 `/api/approvals`(D85) · 자산 처분 화면 |
| **F4** 취득 검증 | `verify_ownership` → S18 | **완료** (Sprint 6·7). REST `GET /api/assets/{id}/ownership` + 실사 화면 |

F1이 가장 크고 나머지는 그 위에 얇게 얹힌다. **F1만 해도 "근거를 남기는 에이전트"라는 서사는 성립한다.**

> **F3 이 "완료"인 기준**: `spikes/s10_smoke.py`(17건)가 **실 서버·실 MCP** 로
> `precheck → 도구 draft → submit → /api/approvals 노출 → 상세 → sign → state='signed'` 를 관통하고,
> `spikes/disposal_sign_contract.py`(26건)가 **9자산 × 3모드 27조합 전수**에서
> *BLOCKING 우회 0건 · 서명 없는 확정 0건* 을 4층 각각 독립으로 확인한다.
> ⚠ 남은 것: **처분 승인서·진술보장서 문안 사람 검수**(법적 효력이 있는 문서 — 안전 문구 D2 와 같은 성격).
> ✅ **2026-08-13 사람 검수 완료** — 출력에 `template_review_notice`(검수 완료 · D90)가 붙는다.

### 법령 수집 체크리스트 (실제 상태 — Sprint 7 MQ-701 실수집 이후)

- [x] law.go.kr OPEN API 이용 **신청·발급 완료** → `.env` 의 **`LAW_API_OC`**
  ⚠ 변수명에 "KEY" 가 들어가지 않는 이유 — 인증값은 API 키가 아니라 **신청 이메일 ID 앞부분**이다.
  구 변수명 폴백은 `data/rules/fetch_laws.py:41` **한 곳뿐**이며 문서·설정에는 남기지 않는다.
  값이 비어 있으면 법제처가 `필수입력요소 검증에 실패` 를 **HTTP 200 으로** 돌려준다 —
  `_get_json()` 이 `result` 키를 직접 보고 닫는 이유다. ⛔ **값 자체는 저장소 어디에도 적지 않는다**
- [x] **수집기(`fetch_from_api`) 완료 — Sprint 7 Stage 1.** 확정 형식은
  `MST` 조회(`display=100`·`search=1`·법령명 완전일치) → `JO` **6자리**(조4+가지2) → 조문번호·제목 대조.
  ⛔ **추측한 URL 파라미터 형식을 코드에 박지 않았다** — 위 값은 전부 실호출로 확인했다
  (`data/analysis/law_fetch.md §1`). `조문내용` 이 제목 한 줄뿐인 조문이 있어 `조문내용+항+호+목` 을
  **평탄화**해야 한다는 것도 실측으로 드러났다(§2)
- [x] **적용기(`apply_fetch`)는 완료** — 수집기(실호출)와 적용기(파일 조작)를 분리했으므로
  후자는 합성 픽스처로 검증된다. `'FILLED' | 'UNCHANGED' | 'REVISION_PENDING'`.
  최초 PENDING→FETCHED 는 in-place 기입, 이미 FETCHED 인데 해시가 다르면 **덮어쓰지 않고**
  `pending_revisions/`(append-only, D60·**D75**). 회귀: `spikes/law_fetch_contract.py`
- [x] **조문 참조 7건 등록 완료** (`KR-CITA-ENF-31` 포함. 손으로 원문을 채우지 않는다)
- [x] **6개 조문 원문 수집 완료** → `text`·`effective_from`·`promulgation_no`·`text_hash` 기입
  (`KR-VAT-32`·`KR-STTC-24`·`KR-STTC-146`·`KR-OSHA-93`·`KR-KCC-652`·`KR-CIVIL-388`)
- [ ] **`KR-CITA-ENF-31` — 사람 승인 대기.** 등록 제목 `즉시상각의제` vs API `조문제목` `즉시상각의 의제`
  (공백 1칸)로 **정체성 대조 실패 → `fetch_status:"PENDING"` 유지 · 파일 md5 불변**.
  `engine.normalize()` 는 NFKC + 공백 **축약**이라 이 차이는 정규화로 사라지지 않는다
  (사라졌다면 다른 조문을 같은 조문으로 읽는 것이라 더 위험하다). **중단이 정상 동작이다** (D75)
- [x] **조문 번호·제목 검증 로직 완료** — `IDENTITY_KEYS = ("article","title")` 누락 검사를
  불일치 검사보다 **먼저** 수행. `None`·`""`·공백 전부 누락으로 보고 중단 (D75)
- [ ] 하위 법령 추가 — 안전검사 대상 기계 목록(시행령·고시), 사후관리 기간(시행령)
- [ ] 개정 감지 → 영향 룰 역추적 → 사람 서명 흐름 (Sprint 7 서명 큐는 `requires_signature == true` 필터)

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

> **⚠ 셋 다 v2 다 — Sprint 7 에서 제외를 확정했다** (`07_BACKLOG`).
> 특히 **`detect_law_revision` 과 그 시나리오 S17 은 v2 로 제외됐다.**
> 그런데 **`fetch_laws.check_revisions()` 는 코드에 살아 있다** — `apply_fetch` 가
> "이미 FETCHED 인데 해시가 다르면 덮어쓰지 않고 `pending_revisions/` 로" 를 수행하는 데
> 이 함수가 쓰이기 때문이다(D75).
> **즉 개정 감지 로직은 존재하지만 MCP 도구로 노출하지 않는다.**
> 이 구분을 흐리면 *"도구가 있는데 왜 안 보이나"* 와 *"코드가 없는데 왜 문서에 있나"* 가
> 양쪽으로 생긴다. 노출하려면 `MAINTQ_TOOLS_PROFILE=full` 등록 + `04_MCP_TOOLS` 절 신설이
> 필요하며, 그건 계약 변경이다.

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
| **확장 8종의 입출력 계약 (정본)** | **`04_MCP_TOOLS §8~§15`** |
| **`/api/assets` REST · HTTP 매핑 (정본)** | **`06_REPO_API §2.5`** |
| **테이블 DDL (정본)** | **`05_DB_SCHEMA §11~§17`** |
| 왜 이렇게 정했는가 | `10_DECISIONS` D58~D65 · **D67~D69 · D71 · D73 · D75 · D77~D80** |
| 지금 만들지 않는 것 | `07_BACKLOG` P22~P28 (순서 제약) |
| 선행 범위 | `00_MVP_SCOPE` |
