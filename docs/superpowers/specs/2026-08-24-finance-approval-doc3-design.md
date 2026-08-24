# 재무부 승인 단계 신설 + doc3(자금집행요청서) 렌더 — 설계

**작성일**: 2026-08-24 · **브레인스토밍 세션**: 같은 날 대화(대시보드 작업 이후) · **상태**: 사용자 승인 완료(방향) — 구현 전 상세 스펙

## 0. 배경

D118이 doc3(자금집행요청서)을 "예산 한도·1일 누적 한도·FDS·SoD 확인 같은 내부통제 필드를 요구하는데
현재 DB엔 이 판정 로직이 없다"는 이유로 미룬 상태였다. 이번 세션에서 사용자가 재무부 승인 단계를
MaintQ 내부에 신설해서 doc3을 본격 구현하기로 결정했다.

`data/templates/03_자금집행요청서.docx` 플레이스홀더를 실측 추출(zipfile+regex, D118과 동일 방법)한
결과:

```
FUND_REQUEST_NO · REQUESTED_AT · PO_REQUEST_NO · DIAGNOSIS_DOC_NO
REQUESTER_DEPT · REQUESTER_NAME · REQUEST_CHAIN_ID · FUND_TYPE
PURPOSE · AMOUNT · AMOUNT_KOREAN · EXECUTION_DATE · FUNDING_METHOD
PAYEE_NAME · PAYEE_BIZ_NO · PAYEE_BANK · PAYEE_ACCOUNT_MASKED
[담보/대출 섹션 — "해당 시"] COLLATERAL_TYPE · COLLATERAL_ID · COLLATERAL_VALUE · LOAN_AMOUNT · LTV · REPAYMENT_PLAN
BUDGET_CHECK · BUDGET_EVIDENCE
DAILY_LIMIT_CHECK · DAILY_LIMIT_EVIDENCE
FDS_VERDICT · FDS_EVIDENCE
SOD_CHECK · SOD_EVIDENCE
REQUESTER_NAME/SIGNED_AT · MANAGER_NAME/SIGNED_AT · FINANCE_APPROVER/SIGNED_AT
APPROVAL_RESULT · MFA_STATUS · A2A_DELEGATED · A2A_TARGET · DOC_STATUS
```

핵심 발견: **3단계 서명**(정비사 요청 → 팀장 승인 → **재무담당자 승인**, 신규)이 문서에 이미
전제돼 있고, `A2A_DELEGATED`/`A2A_TARGET`는 기존 `dispatch_a2a_withdrawal_request`(S5,
`backend/services/po.py:394`)와 직결된다.

## 1. 범위

**포함**: `po_drafts` 상태 전이 확장(`approved` 뒤에 재무 승인 단계 삽입) · 내부통제 판정 4종
(예산/일일한도/FDS/SoD) · `POST /api/po/{po_id}/finance-approve`·`finance-reject` 신설 ·
doc3 렌더(`po_documents.py` 확장) · A2A request-withdrawal 전송 시점을 재무 승인 이후로 이동

**명시적으로 제외**:
- 담보/대출 정보 섹션(`COLLATERAL_*`·`LOAN_AMOUNT`·`LTV`) — 일반 부품 발주(S1/S2)만 대상이라
  N/A 고정. S8(assess-loan) 대출 흐름과의 연결은 별도 과제
- `MFA_STATUS` — MaintQ에 다단계 인증 시스템이 없다. 이 필드 하나만 "미구현" 정직 고지(D62 —
  문서 전체가 아니라 이 필드만 확인 불가한 경우이므로, 핵심 내부통제 4종이 전부 실측이면
  D118이 04(담보대출심사회신서)를 제외시켰던 이유("빈 칸투성이")와는 다르다)

## 2. 상태 전이 확장

```
draft ──submit(정비사)──▶ pending ──approve(팀장)──▶ approved
                                                          │
                                          finance-approve(재무담당자)
                                                          ▼
                                       finance_pending ──┴──▶ finance_approved
                                                          └──▶ finance_rejected
```

`backend/services/po.py`의 `ALLOWED_FROM` 확장:
```python
ALLOWED_FROM: dict[str, str] = {
    "pending": "draft",
    "approved": "pending",
    "rejected": "pending",
    "finance_approved": "approved",   # 신규
    "finance_rejected": "approved",   # 신규
}
```

**`approve()`가 자동으로 `finance_pending`을 만드는가, 아니면 `approved`가 곧 `finance_pending`을
겸하는가?** — 별도 상태 `finance_pending`을 두지 않고 **`approved` 자체가 "재무 승인 대기중"을
겸한다**(스키마 단순화). `finance-approve`/`finance-reject`는 `ALLOWED_FROM`에서 `approved`를
전제로 하므로 위 다이어그램의 `finance_pending` 박스는 개념적 표기일 뿐, 실제 DB 상태값으로는
안 만든다. `po_drafts.state` CHECK 확장:
```sql
CHECK (state IN ('draft','pending','approved','rejected','finance_approved','finance_rejected'))
```

## 3. 신규 컬럼 (`po_drafts`)

기존 `decided_by`/`decision_note`는 **팀장 승인**(`approved`/`rejected`) 전용으로 그대로 두고,
재무 승인은 별도 3컬럼을 추가한다(3자 서명 각각 독립 기록, `MANAGER_SIGNED_AT`/`FINANCE_SIGNED_AT`
분리 렌더를 위해 필수):

```sql
ALTER TABLE po_drafts ADD COLUMN decided_at TIMESTAMP;              -- 기존 approve/reject 도 지금까지 시각이 없었다 (신규 gap)
ALTER TABLE po_drafts ADD COLUMN finance_decided_by TEXT REFERENCES users;
ALTER TABLE po_drafts ADD COLUMN finance_decision_note TEXT;
ALTER TABLE po_drafts ADD COLUMN finance_decided_at TIMESTAMP;
```

`decided_at`이 지금까지 없었다는 것도 이번에 드러난 기존 갭이다 — `MANAGER_SIGNED_AT`을 렌더하려면
필요하므로 이번 스코프에 포함한다.

## 4. REST 엔드포인트 (`backend/routers/po.py`)

기존 `submit`/`approve`/`reject`와 같은 패턴:

```python
@router.post("/{po_id}/finance-approve")
async def finance_approve(po_id: str, body: ApproveBody | None = None, c: Caller = Depends(caller)) -> dict:
    """approved → finance_approved. 재무부 소속 manager 전용 (SoD, D119)."""
    require(c, "manager", "자금집행 승인")
    if c.department != "finance":
        raise HTTPException(403, "자금집행 승인은 재무부 소속만 수행할 수 있습니다 (D119)")
    result = _finance_transition(po_id, "finance_approved", c.user_id, body.note if body else None)
    try:
        await svc.dispatch_a2a_withdrawal_request(po_id)   # ← S5 전송을 여기로 이동
    except Exception:
        logger.exception("A2A request-withdrawal 전송 실패: po_id=%s", po_id)
    return result


@router.post("/{po_id}/finance-reject")
def finance_reject(po_id: str, body: RejectBody, c: Caller = Depends(caller)) -> dict:
    """approved → finance_rejected. 사유 필수 (D38 선례)."""
    require(c, "manager", "자금집행 반려")
    if c.department != "finance":
        raise HTTPException(403, "자금집행 반려는 재무부 소속만 수행할 수 있습니다 (D119)")
    return _finance_transition(po_id, "finance_rejected", c.user_id, body.reason)
```

기존 `approve()`(`po.py:156-174`)에서 `dispatch_a2a_withdrawal_request` 호출을 **제거**한다 —
재무 승인 전에 자금이 나가면 안 된다는 게 이번 설계의 핵심이다.

**D108과의 관계 (신규 D119)**: D108은 "`department`는 권한이 아니다, `require()`는 `role`만
본다"고 못박았다. 이번 두 엔드포인트가 `c.department == "finance"`를 직접 검사하는 건 D108을
어기는 게 아니라 **명시적으로 등재하는 예외**다 — `require()` 자체(모든 다른 라우트가 쓰는
공용 함수)는 여전히 department를 안 본다, 오직 이 두 엔드포인트가 자기 함수 본문에서 SoD
목적으로 추가 검사를 한다. `docs/10_DECISIONS.md`에 D119로 정확히 이 구분을 적어야 한다
(구현 스테이지에서 D10 절대 규칙에 따라 먼저 등재).

## 5. 내부통제 판정 로직 (신규, 전부 "목업 전제" 명시 고지)

신규 파일 `data/expenditure_limits.py` (D74 `residual_curve` 목업 공식·D92 `partner_links`
목업 전제와 같은 패턴 — 근거 없는 상수는 코드 주석과 문서 양쪽에 "목업"이라고 밝힌다):

```python
# -*- coding: utf-8 -*-
"""자금집행 내부통제 판정 — 전부 목업 상수/규칙이다. 실제 재무 정책이 아니다."""

BUDGET_LIMIT = 5_000_000       # 건당 예산 한도 (원) — 목업 상수
DAILY_LIMIT = 15_000_000       # 부서 1일 누적 한도 (원) — 목업 상수
FDS_WARNING_RATIO = 0.5        # 예산한도 대비 이 비율 초과 시 "주의" — 목업 규칙


def budget_check(amount: int) -> tuple[bool, str]:
    ok = amount <= BUDGET_LIMIT
    return ok, f"{amount:,}원 / 한도 {BUDGET_LIMIT:,}원 ({'이내' if ok else '초과'})"


def daily_limit_check(amount: int, today_total_before: int) -> tuple[bool, str]:
    total = today_total_before + amount
    ok = total <= DAILY_LIMIT
    return ok, f"금일 누적 {total:,}원 / 한도 {DAILY_LIMIT:,}원 ({'이내' if ok else '초과'})"


def fds_verdict(amount: int) -> tuple[str, str]:
    ratio = amount / BUDGET_LIMIT
    verdict = "주의" if ratio > FDS_WARNING_RATIO else "정상"
    return verdict, f"예산한도 대비 {ratio:.0%} — 목업 규칙(FDS_WARNING_RATIO={FDS_WARNING_RATIO})"


def sod_check(requested_by: str, decided_by: str, finance_decided_by: str) -> tuple[bool, str]:
    ids = {requested_by, decided_by, finance_decided_by}
    ok = len(ids) == 3
    return ok, f"요청자·팀장·재무 3인 {'전원 상이' if ok else '중복 있음'} ({sorted(ids)})"
```

`daily_limit_check`의 `today_total_before`는 실측 SQL 집계다(목업 아님):
```sql
SELECT COALESCE(SUM(unit_price * qty), 0) FROM po_drafts
WHERE state = 'finance_approved' AND DATE(finance_decided_at) = CURRENT_DATE
```

`sod_check`는 실측(목업 아님) — DB의 실제 `requested_by`/`decided_by`/`finance_decided_by` 3개
값을 그대로 비교한다.

## 6. 문서 렌더 (`backend/services/po_documents.py` 확장)

기존 `render_po_request_document`·`render_diagnosis_document`와 같은 패턴(문안은 코드 상수,
값만 치환, 저장 안 함 — D86)으로 `render_fund_execution_document(po)` 신설. `get_po()`가 이미
`decided_by`·(신규)`finance_decided_by` 등을 갖고 있으므로 추가 조회 없이 조합 가능. 담보 섹션은
전부 `"해당 없음"` 고정 문자열, `MFA_STATUS`는 `"미구현 (MaintQ 에 MFA 시스템 없음)"` 고정.

## 7. 화면 반영

- 매니저 승인 큐(`PoDetail.tsx`)에 `finance_approved`/`finance_rejected` 상태 렌더 추가 —
  기존 `lib/queueState.ts`(D87 상태뷰 단일 소스, disposal 선례) 확장
- doc3 미리보기는 기존 `DocumentPreview.tsx`(01·02 삽입 선례) 확장
- 재무 승인 액션 버튼은 **`c.department === "finance"`인 매니저 로그인일 때만** 노출 — 지금
  목업 신원은 `mgr-01`(department 미배정 추정)·`mgr-02`(department='finance')뿐이므로,
  `mgr-02`로 전환하는 방법(역할 전환 UI에 부서 선택 추가할지, 별도 로그인 경로를 둘지)은
  구현 스테이지에서 화면 쪽과 함께 확정 필요 — **이번 스펙에서 미결 항목**

## 8. 회귀 영향

- `data/seed.py`: `po_drafts` 시드 케이스에 `finance_approved`/`finance_rejected` 표본 추가,
  `decided_at`/`finance_decided_*` 컬럼 자가검증 항목 신설(케이스 맵 번호 이어받음)
  `error_codes` 65→70 처럼 이번에도 `--with-error-codes` 류의 별도 게이트는 필요 없음(사람
  승인 불필요, 목업 상수라 즉시 적재)
- `spikes/api_contract.py`·`spikes/write_tool_contract.py` 급으로 새 스파이크 또는 기존
  확장 필요 — `finance-approve`/`finance-reject` 권한 경계(재무부 아닌 manager → 403,
  technician → 403, 상태 순서 위반 → 409) 계약 검사
- `docs/06_REPO_API.md` §2.4 상태 전이 다이어그램 갱신
- `frontend/spikes/ui_honesty_contract.py`(L2) — `PoDetail.tsx`가 신규 상태를 상태뷰 맵을
  거치지 않고 직접 비교하면 D87 위반이 될 것 — 기존 글롭에 이미 편입돼 있어 자동 스캔됨

## 9. 미결 항목 (구현 스테이지에서 확정)

1. §7의 재무부 로그인 전환 UX
2. `docs/10_DECISIONS.md`에 D119 정식 등재(위 §4 문안 기반)
3. `docs/00_MVP_SCOPE.md`·`docs/02_SCENARIOS.md`에 이 흐름이 어느 S# 시나리오 확장인지
   명기할지(S5의 확장으로 보임 — "S5+"로 표기하는 게 기존 "S1+"·"S10" 표기 관례와 맞음)

## 10. 구현 권고

이 스펙은 새 상태 2종·컬럼 4개·REST 엔드포인트 2개·판정 로직 4종·문서 렌더 확장·화면 반영을
포함해 이번 세션의 대시보드 작업보다 크다. `/sprint`로 스테이지를 나눠 진행할 것을 권한다
(예: Stage 1 DB·상태전이·판정로직, Stage 2 REST+A2A 이동, Stage 3 문서렌더, Stage 4 화면).
