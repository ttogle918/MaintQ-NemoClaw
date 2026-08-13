# MaintQ — A2A 계약 참조 (외부, QMesh 예정)

> 이 문서는 **참조용 인덱스**다. 실제 스키마 원본은 `A2A_Q`(QMesh 허브 레포)
> `docs/schemas/`, `docs/agent_cards/`에 있고 여기서는 복제하지 않는다 — 원본이
> 바뀌면 이 문서가 아니라 A2A_Q 쪽만 고치면 된다(drift 방지).
>
> 상태: **M1(계약 계층) 초안.** A2A 실구현(오케스트레이터·HTTP 어댑터)은 아직 착수 전.
> `06_REPO_API.md`가 다루는 현재 REST API(`/api/po`, `/api/decisions` 등)와는 별개다.

## MaintQ의 역할

MaintQ는 A2A 스킬을 **노출하지 않는다.** 모든 크로스도메인 시나리오에서 **요청을 시작하는
client** 역할이다. 예외는 S15 — InsuQ 응답을 받은 뒤 MaintQ가 FinAllQ를 2차로 부른다는 점에서만
"응답을 전달"하는 위치에 선다(스킬을 노출하는 건 아님).

## 이 레포에서 나가는 요청 (client 호출 목록)

| 트리거 (이 레포 내부 이벤트) | 대상 | 스킬 | 스키마 |
|---|---|---|---|
| 팀장 승인 완료 (`po.py` submit→approved) | FinAllQ | `request-withdrawal` | `A2A_Q/docs/schemas/request-withdrawal.json` |
| 환헤지 상담 요청(수동 트리거, 향후) | FinAllQ | `advise-hedge` | `A2A_Q/docs/schemas/advise-hedge.json` |
| 화재보험 갱신 상담 요청 | InsuQ | `advise-policy-renewal` | `A2A_Q/docs/schemas/advise-policy-renewal.json` |
| 담보 대출 상담 요청 | FinAllQ (→ 내부 2차홉 InsuQ) | `assess-loan` | `A2A_Q/docs/schemas/assess-loan.json` |
| 처분 서명 완료 (`decisions.py` sign) | InsuQ | `notify-asset-change` | `A2A_Q/docs/schemas/notify-asset-change.json` |
| 처분 확정 + 매각대금 입금 | FinAllQ | `request-settlement` | `A2A_Q/docs/schemas/request-settlement.json` |
| 중고설비 취득 검토 | FinAllQ (→ 내부 2차홉 InsuQ) | `assess-used-equipment-loan` | `A2A_Q/docs/schemas/assess-used-equipment-loan.json` |
| 신규 설비 등재 → 위험 프로파일 재계산 | InsuQ | `notify-risk-change` | `A2A_Q/docs/schemas/notify-risk-change.json` |
| 설비 화재 멸실 사고 | InsuQ (응답 후 FinAllQ 2차 호출) | `claim-insurance` → `advise-replacement-financing` | `A2A_Q/docs/schemas/claim-insurance.json`, `A2A_Q/docs/schemas/advise-replacement-financing.json` |
| 설비 취득 예산 확정 | FinAllQ | `advise-financing` | `A2A_Q/docs/schemas/advise-financing.json` |

## 신원은 두 층이다 — 토큰(actor) + payload(subject)

> A2A_Q `docs/A2A_IDENTITY.md` **결정 1 (2026-08-13 개정)**.
> 이전 초안의 "payload에 회사 식별자만 담는다"는 방식은 **폐기됐다.**

```
파트너 자격증명 → 서명된 액세스 토큰   = actor  "누가 호출했나"  → 인증
요청 payload 의 대상 식별자            = subject "누구 건인가"    → 대상 지정
```

**⛔ `requester` 객체는 인증 정보가 아니다.** 식별자는 공개정보라 번호만 알면 남의 회사
건을 요청할 수 있다 — 이 값만으로 상대 시스템이 요청을 승인해서는 안 된다.
실제 인증은 파트너 자격증명(토큰)이 하고, 상대 서버가 "이 actor가 이 subject를 다룰
권한이 있는가"를 자기 위임 테이블로 검사한다.

### 공통 requester 필드 (payload 스키마 자체는 변경 없음)

```json
"requester": {
  "finallq_company_id": "필수 — 전역 기업 식별자(subject). FinAllQ company.id 기준",
  "building_id": "선택 — 이 레포의 건물 참조(subject)",
  "policy_id": "선택 — InsuQ 계약 참조(subject)"
},
"request_chain_id": "필수 — 멀티홉 추적용. 최초 요청에서 발급 후 전 구간 전파"
```

## 호출 전제 — 사람이 연결을 승인하기 전에는 아무것도 못 나간다

A2A_Q **결정 2(초대 기반 온보딩)**로 연결은 **2단계**로 확정됐다:

```
[사람 단계] MaintQ 담당자 ↔ FinAllQ ADMIN 이 연결 자체를 승인
           → 그 시점에 파트너 자격증명 발급 (허용 작업·한도·유효기간 포함)
[기계 단계] 그 자격증명으로 에이전트가 액세스 토큰을 받아 스킬 호출
```

**위 표의 어떤 호출도 1단계 완료 전에는 발생할 수 없다.** 즉 이 문서의 트리거 열은
전부 "연결이 이미 승인돼 있다"를 암묵 전제로 한다. 온보딩 자체는 A2A 프로토콜이
아니라 FinAllQ 자체 기능이며, QMesh는 그 결과물(자격증명)만 전제로 삼는다.

## 이 레포가 채워야 할 자리 (2026-08-13 확정 → Sprint 8 에서 일부 구현)

`~~미해결: finallq_company_id 가 자산 마스터에 없다~~` → **설계 확정 · 스키마 구현 완료.**
상세는 `docs/A2A_IDENTITY.md`. 요약:

| 무엇 | 어디에 | 상태 |
|---|---|---|
| subject 매핑 (`finallq_company_id` 등) | 신규 `partner_links` 테이블 — 판정(`link_state`)과 식별자(`external_ref`)를 **분리**(D78 패턴) | ✅ **구현 (스키마)** — `data/seed.py §18`. DDL 세부는 D96 이 개정(`IS` · `subject_ref NOT NULL` · `linked_at DATETIME`) |
| "이미 연결됨" 전제 | `seed.py`에 심는다. **`NOT_LINKED` 대조군 1건 포함** | ✅ **구현 (시드)** — 5행(`LINKED` 4 / `NOT_LINKED` 1 = `BLD-D`). ⚠ **목업 전제**(`PARTNER_LINKS_MOCK=True`) — 실제 연결 승인이 아니다 |
| 파트너 자격증명 | `.env` + `backend/a2a/credentials.py`. **MCP 도구는 보지 않는다**(D15) | 🟡 **구현 (env 계층)** — 4키(값 전부 빈칸) + 상태 4종 로더. **토큰 캐시 미착수**(호출부가 없다) |
| `request_chain_id` | `traces`에 nullable 컬럼 신설. `event_type` 신설은 **하지 않는다** | 🟡 **구현 (컬럼만)** — 전 행 NULL 이 정상. `event_type` 은 3종 그대로 |
| 나간 요청 원문 | 해당 `tool_result` 행의 `tool_payload`. **⛔ 인증 헤더는 제외** | ⚠ **미구현** — **쓰는 쪽(A2A 호출부)이 없다.** 스파이크 `⑪-b` 가 *"쓰는 코드 0건"* 을 명시적으로 기록한다(D76-2 재발 방지) |

> ⛔ **위 호출 목록 표(§"이 레포에서 나가는 요청")는 여전히 전부 미구현이다.** Sprint 8 이 채운 것은
> **신원·계측 자리**이지 요청을 보내는 코드가 아니다 — 실제 HTTP 호출·오케스트레이터는 QMesh 착수 후다.

> ⚠ subject 매핑값을 trace **컬럼으로 복제하지 않는다.** "그때 어느 company_id로
> 보냈나"는 그 이벤트의 `tool_payload`(요청 원문)를 여는 것이 정식 판정 경로다 —
> `link_state`가 나중에 바뀌어도 과거 원문은 그 시점 그대로 남는다.

> 📌 **subject 매핑에서 InsuQ 는 예외 취급이 아니라 원칙 적용이다** — InsuQ 건물 행은
> `external_ref` **없이(NULL) 연결 승인(`link_state`)만** 담는다. **증권 식별자의 정본은
> `assets.policy_id`** 이고 `partner_links` 에 복제하지 않는다 (**D95**). 나가는 payload 의
> `policy_id` 는 그래서 `assets` 에서 읽는다. seed 검사 ㉔ 가 *"어디에도 복제되지 않았다"* 를 본다.

## 관련 문서

- `A2A_IDENTITY.md` — **이 레포의 신원 식별 조사·결정** (partner_links 스키마·seed 방침·trace)
- `06_REPO_API.md` — 이 레포의 실제(내부) REST API
- `11_ASSET_LIFECYCLE.md` — 처분·근거 3계층(S9·S10·S18, A2A 아님)
- A2A_Q `docs/A2A_IDENTITY.md` — 신원 식별 설계 결정 전체 (결정 1·2 원본 인용처)
- A2A_Q `11_A2A_SCENARIOS.md` — S5~S16 시나리오 상세
