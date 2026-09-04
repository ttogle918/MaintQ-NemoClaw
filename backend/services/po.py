# -*- coding: utf-8 -*-
"""발주 서비스 — 신원 stamp 와 상태 전이.

**신원이 도구 파라미터가 아닌 이유 (D23·D37).**
MCP 도구 스키마에 `requested_by` 가 있으면 LLM 이 그 값을 채울 수 있다 = 위조 경로다.
그래서 도구는 신원 없이 INSERT 하고, 백엔드가 같은 요청 안에서 X-User 값으로 stamp 한다.
백엔드는 사람 쪽 코드라 UPDATE 권한이 있어도 되고(D10 은 MCP 도구만 제약),
LLM 은 이 경로에 개입할 수 없다.

**상태 전이 (docs/06_REPO_API.md §2.4, D119 재무부 승인 단계 확장)**
    draft ──submit(정비사)──▶ pending ──approve(팀장)──▶ approved
                                 │                          ├──finance-approve(재무부)──▶ finance_approved
                                 │                          └──finance-reject(재무부)───▶ finance_rejected
                                 └──────reject(팀장)──▶ rejected
전이의 주체(역할)는 라우터가, 전이의 순서(현재 상태)는 여기서 강제한다.
"""

from __future__ import annotations

import json
import sqlite3

from backend import manifest
from backend.db import connect
from backend.services import po_documents, state_machine
from data import doc_fields as _df
from data import po_draft

# 전이 규칙: 목표 상태 → 허용되는 현재 상태
ALLOWED_FROM: dict[str, str] = {
    "pending": "draft",
    "approved": "pending",
    "rejected": "pending",
    "finance_approved": "approved",
    "finance_rejected": "approved",
}


class TransitionError(Exception):
    """현재 상태에서 할 수 없는 전이."""

    def __init__(self, po_id: str, current: str, target: str) -> None:
        self.po_id, self.current, self.target = po_id, current, target
        super().__init__(
            f"{po_id} 는 지금 '{current}' 상태라 '{target}' 로 전이할 수 없습니다 "
            f"('{ALLOWED_FROM[target]}' 에서만 가능)"
        )


#: 전이 골격(연결·잠금·404·409)은 `state_machine.Flow` 가 소유한다 (D126).
#: 여기 남는 것은 이 흐름 고유의 UPDATE 뿐이다.
FLOW = state_machine.Flow("po_drafts", "po_id", ALLOWED_FROM, TransitionError)


def display_name(user_id: str | None, db_path: str | None = None) -> str:
    """ASCII 사용자 ID → 화면 표시명 (D36 매핑을 D41 로 `users` 테이블 이관).

    하드코딩 딕셔너리였던 것을 DB 조회로 바꿨다 — 표시명이 코드에 박혀 있으면 사용자가
    늘 때마다 배포가 필요하고, `requested_by`/`decided_by` 의 FK 대상도 생기지 않는다.

    **미등록 ID 는 예외가 아니라 ID 를 그대로 돌려준다.** 표시명이 없다고 화면이 비면
    승인 큐에서 "누가 요청했는지"가 사라진다 — 삭제된 계정이어도 감사 추적은 남아야 한다.
    """
    if not user_id:
        return user_id or ""
    with connect(db_path) as con:
        r = con.execute("SELECT display_name FROM users WHERE user_id = ?", (user_id,)).fetchone()
    return r["display_name"] if r else user_id


# D39 경계(저장 UTC · 전송 명시)의 정본은 data/doc_fields.py 다 — agent/trace.py ·
# routers/equipment.py · services/{decisions,disposal,repairs}.py 5곳이 여기서
# import 하므로 이름을 그대로 재수출한다.
iso_utc = _df.iso_utc


# S5+ 재무부 승인 단계에 들어선 상태 — 이 상태들에서만 자금집행요청서(doc3) 내부통제를
# 계산한다 (D118·D119).
_FUND_EXECUTION_STATES = ("approved", "finance_approved", "finance_rejected")

# 표시명은 users 조인으로 붙인다 (D41) — 행마다 display_name() 을 부르면 N+1 이 된다.
# LEFT JOIN 인 이유: requested_by 는 stamp 전 NULL 이고, 미등록 ID 여도 행이 사라지면 안 된다
# 조회 SQL·행 매핑의 정본은 data/doc_fields.py 다 (D124) — MCP 읽기 도구가 같은
# 컨텍스트를 봐야 하는데 그쪽은 backend 를 import 할 수 없다(D15).
_PO_SELECT = _df.PO_SELECT


_row_to_po = _df.row_to_po


def stamp_identity(
    po_id: str,
    requested_by: str,
    session_id: str | None = None,
    db_path: str | None = None,
) -> bool:
    """도구가 만든 draft 에 신원·세션을 새긴다 (D37).

    draft 상태에서 아직 비어 있을 때만 1회 — 이미 stamp 된 발주의 요청자를
    나중에 바꿀 수 있으면 감사 추적이 무너진다.
    """
    with connect(db_path) as con:
        cur = con.execute(
            "UPDATE po_drafts SET requested_by = ?, session_id = ?"
            " WHERE po_id = ? AND state = 'draft' AND requested_by IS NULL",
            (requested_by, session_id, po_id),
        )
        return cur.rowcount == 1


class NotEditableError(Exception):
    """draft 상태가 아닌 발주 초안을 수정하려는 시도 (`PATCH /api/po/{po_id}`)."""

    def __init__(self, po_id: str, current: str) -> None:
        self.po_id, self.current = po_id, current
        super().__init__(
            f"{po_id} 는 지금 '{current}' 상태라 수정할 수 없습니다 ('draft' 에서만 가능)"
        )


_VALID_MODELS = ("iG5A", "S100", "IE5")


def _validate_input(
    *, part_no: str, qty: int, supplier_id: str, reason: str, urgency: str,
    model: str | None, error_code: str | None,
) -> dict | None:
    """스키마 경계 검증 — `mcp_server/tools/create_po_draft.py`와 의도적으로 같은 체크를
    반복한다(공유 계층으로 옮기지 않는 이유는 `data/po_draft.py` 모듈 docstring 참고)."""
    if not part_no or not supplier_id:
        return {"status": "error", "reason": "invalid_input", "message": "part_no·supplier_id 는 필수입니다"}
    if not reason or not reason.strip():
        return {
            "status": "error", "reason": "reason_required",
            "message": "reason 은 필수입니다 — 승인자가 판단 근거를 추적할 수 있어야 합니다 (D5)",
        }
    if qty < 1:
        return {"status": "error", "reason": "invalid_input", "message": f"qty 는 1 이상이어야 합니다: {qty}"}
    if urgency not in ("urgent", "normal"):
        return {"status": "error", "reason": "invalid_input", "message": f"urgency 는 urgent|normal 이어야 합니다: {urgency!r}"}
    if (model is None) != (error_code is None):
        return {"status": "error", "reason": "model_code_pair", "message": "model 과 error_code 는 둘 다 있거나 둘 다 없어야 합니다 (D33)"}
    if model is not None and model not in _VALID_MODELS:
        return {
            "status": "error", "reason": "invalid_model",
            "message": f"model 은 {' | '.join(_VALID_MODELS)} 이어야 합니다: {model!r}",
        }
    return None


def quotes_for_part(part_no: str, db_path: str | None = None) -> list[dict]:
    """`GET /api/po/quotes/{part_no}` — 발주 초안을 만들기 전 공급사를 고르기 위한 조회.
    부품·공급사가 없으면 빈 리스트(404 아님 — "없다"는 유효한 조회 결과다, D62)."""
    with connect(db_path) as con:
        return po_draft.list_quotes(con, part_no=part_no)


def create(
    *,
    part_no: str,
    qty: int,
    supplier_id: str,
    reason: str,
    urgency: str = "normal",
    model: str | None = None,
    error_code: str | None = None,
    evidence: dict | None = None,
    requested_by: str,
    db_path: str | None = None,
) -> dict:
    """`POST /api/po` — 화면이 발주 초안을 직접 생성한다(P39 축소판).

    `requested_by`를 생성 즉시 stamp한다 — 채팅 경로(`stamp_identity`)와 달리 2단계가
    필요 없다. 이 함수를 부르는 요청 자체가 이미 `X-User`를 통과한 신뢰된 백엔드 경로다
    (D52 태도). 산출 로직은 `data/po_draft.py`에 있다 — MCP 도구(`create_po_draft`)와
    같은 함수를 쓴다(D73·D101 패턴).
    """
    invalid = _validate_input(
        part_no=part_no, qty=qty, supplier_id=supplier_id, reason=reason,
        urgency=urgency, model=model, error_code=error_code,
    )
    if invalid is not None:
        return invalid

    code = error_code.upper() if error_code else None
    try:
        with connect(db_path) as con:
            result = po_draft.validate_and_price(
                con, part_no=part_no, qty=qty, supplier_id=supplier_id, model=model, error_code=code,
            )
            if result["status"] != "ok":
                return result

            po_id = po_draft.next_po_id(con)
            po_draft.insert_draft(
                con,
                po_id=po_id, part_no=part_no, qty=qty, supplier_id=supplier_id,
                model=model, error_code=code,
                evidence_json=json.dumps(evidence, ensure_ascii=False) if evidence else None,
                unit_price=result["unit_price"], reason=reason.strip(), urgency=urgency,
                requested_by=requested_by,
            )
    except sqlite3.IntegrityError as e:
        return {"status": "error", "reason": "integrity", "message": str(e)}

    return get_po(po_id, db_path) or {}


def update(
    po_id: str,
    *,
    part_no: str,
    qty: int,
    supplier_id: str,
    reason: str,
    urgency: str = "normal",
    model: str | None = None,
    error_code: str | None = None,
    evidence: dict | None = None,
    db_path: str | None = None,
) -> dict:
    """`PATCH /api/po/{po_id}` — draft 상태에서만 수정. 없으면 KeyError, draft 가
    아니면 NotEditableError(라우터가 각각 404·409로 매핑). supplier/qty/model/
    error_code 변경 시 단가·MOQ·에러코드를 재검증해 새 스냅샷을 찍는다(D31 정신 —
    오래된 단가를 그대로 두지 않는다).
    """
    invalid = _validate_input(
        part_no=part_no, qty=qty, supplier_id=supplier_id, reason=reason,
        urgency=urgency, model=model, error_code=error_code,
    )
    if invalid is not None:
        return invalid

    code = error_code.upper() if error_code else None
    with connect(db_path) as con:
        row = con.execute("SELECT state FROM po_drafts WHERE po_id=?", (po_id,)).fetchone()
        if row is None:
            raise KeyError(po_id)
        if row["state"] != "draft":
            raise NotEditableError(po_id, row["state"])

        result = po_draft.validate_and_price(
            con, part_no=part_no, qty=qty, supplier_id=supplier_id, model=model, error_code=code,
        )
        if result["status"] != "ok":
            return result

        po_draft.update_draft(
            con,
            po_id=po_id, part_no=part_no, qty=qty, supplier_id=supplier_id,
            model=model, error_code=code,
            evidence_json=json.dumps(evidence, ensure_ascii=False) if evidence else None,
            unit_price=result["unit_price"], reason=reason.strip(), urgency=urgency,
        )
    return get_po(po_id, db_path) or {}


def list_pos(state: str | None = None, db_path: str | None = None) -> list[dict]:
    sql = _PO_SELECT
    args: list[object] = []
    if state:
        sql += " WHERE p.state = ?"
        args.append(state)
    sql += " ORDER BY p.urgency = 'urgent' DESC, p.created_at DESC, p.po_id DESC"
    with connect(db_path) as con:
        return [_row_to_po(r) for r in con.execute(sql, args).fetchall()]


def _attach_print_pages(po: dict) -> None:
    """`evidence.basis[]` 각 항목에 `print_page` 를 얹는다 (D57 — W-6 근본 해소).

    저장(`evidence` 컬럼)은 물리 페이지 그대로다(D26 불변) — 이 계산은 **응답 조립
    시점**에만 하고 DB 에 쓰지 않는다. SSE 경로의 `sse.citation_for()` 와 나란한
    REST 경로의 렌더 지점이고, 오프셋 산술 자체는 두 경로 모두 `manifest.to_print_page()`
    한 곳에 위임한다(D32 원 취지 — "1곳"은 이 공유 함수를 뜻하지 REST·SSE 각자의
    호출 지점을 하나로 합치라는 뜻이 아니다).

    `model` 이 NULL(에러코드 승인 전의 현재 시드 — D33 은 이 상태를 허용)이거나
    `manual_page` 가 없으면 **필드 자체를 뺀다** — 지어낸 값을 얹지 않는다. 프론트의
    "PDF p." 폴백(W-6 표시측, Stage 1)이 그 경우를 계속 정직하게 표시한다.
    """
    model = po.get("model")
    if model not in manifest.MODELS:
        return
    evidence = po.get("evidence")
    if not evidence:
        return
    for entry in evidence.get("basis") or []:
        # `evidence`는 LLM이 create_po_draft 호출 시 자유 형식으로 채우는 값이라(D34,
        # 스키마 강제 없음) basis 항목이 항상 dict라는 보장이 없다 — 실측: 문자열 항목이
        # 섞여 들어와 .get() 호출이 AttributeError로 터지며 PO 카드 렌더 자체가 실패했다
        # (create_po_draft는 이미 성공한 뒤였는데도 채팅 응답이 "생성 실패"로 보임).
        # 모양이 다른 항목은 그냥 건너뛴다 — 지어내지 않고, 죽지도 않는다.
        if not isinstance(entry, dict):
            continue
        page = entry.get("manual_page")
        if isinstance(page, int) and not isinstance(page, bool) and page >= 1:
            entry["print_page"] = manifest.to_print_page(model, page)


def fund_execution_inputs(con, po: dict, db_path: str | None = None) -> tuple | None:
    """03 자금집행요청서가 필요로 하는 `(controls, a2a_info, payee)`. 대상 상태가 아니면 None.

    `get_po()` 안에 인라인으로 있던 블록을 그대로 꺼낸 것이다 — docx 다운로드
    (`backend/services/document_download.py`)가 **같은 값**을 써야 하기 때문이다.
    두 벌로 두면 화면 미리보기와 docx 가 다른 내부통제 판정을 말하게 된다
    (D119·D121 이 걸려 있는 계산이다).

    ⛔ DB 에 쓰지 않는다 — 호출자의 지역 변수로만 조립돼 렌더에 쓰이고 버려진다(D86).
    approved 이전(draft·pending)에는 재무부 승인 대상이 아직 아니므로 None —
    빈 칸투성이 문서 대신 null 을 준다(D62).
    """
    if po["state"] not in _FUND_EXECUTION_STATES:
        return None

    from backend.services import a2a_history
    from data import expenditure_limits as limits

    po_id = po["po_id"]
    amount = po["unit_price"] * po["qty"]
    # po_id != ? — 이미 finance_approved 로 확정된 발주를 재조회할 때 자기 금액이
    # "오늘 누적"에 중복 산입되는 것을 막는다(스펙 원문에는 없던 조건, 자기중복 버그
    # 방지를 위해 이 프로젝트에서 추가 — D121).
    today_total = con.execute(
        "SELECT COALESCE(SUM(unit_price * qty), 0) FROM po_drafts"
        " WHERE state = 'finance_approved' AND po_id != ?"
        " AND DATE(finance_decided_at) = CURRENT_DATE",
        (po_id,),
    ).fetchone()[0]
    controls = {
        "budget": limits.budget_check(amount),
        "daily_limit": limits.daily_limit_check(amount, today_total),
        "fds": limits.fds_verdict(amount),
        "sod": (
            limits.sod_check(po["requested_by"], po["decided_by"], po["finance_decided_by"])
            if po.get("requested_by") and po.get("decided_by") and po.get("finance_decided_by")
            # 신원 3종(요청자·팀장·재무 담당) 중 하나라도 없으면 SOD 를 지어내지
            # 않는다(D62) — 함수 자체를 부르지 않는다. `finance_decided_by` 만 보던
            # 원래 가드는 `requested_by`가 NULL 인 정상 상태(D23·D37 — 챗봇 경유
            # draft 가 아직 stamp 안 된 경우)에서 sod_check() 내부 `sorted({...})`가
            # None 과 str 을 비교해 TypeError 로 죽는 버그가 있었다(실측: Stage 3
            # 회귀에서 backend/routers/test_po_a2a_trigger.py 4건 FAIL 로 발견).
            else (None, "확인 전 — 요청자·팀장·재무 승인자 중 아직 지정되지 않은 신원이 있습니다")
        ),
    }
    # A2A 이력은 이 한 곳(list_a2a_history)만 재사용한다 — SQL 을 여기 복제하지
    # 않는다(D114, W2/W5 드리프트 재발 방지).
    a2a_result = a2a_history.list_a2a_history(
        po_id=po_id, skill="request-withdrawal", limit=1, db_path=db_path
    )
    a2a_info = a2a_result["items"][0] if a2a_result["items"] else None
    payee_row = con.execute(
        "SELECT account_number, bank_code FROM suppliers WHERE supplier_id = ?",
        (po["supplier_id"],),
    ).fetchone()
    payee = dict(payee_row) if payee_row else None
    return controls, a2a_info, payee


def get_fund_execution_inputs(po: dict, db_path: str | None = None) -> tuple | None:
    """커넥션을 직접 여는 얇은 래퍼 — docx 다운로드 엔드포인트용."""
    with connect(db_path) as con:
        return fund_execution_inputs(con, po, db_path)


def get_po(po_id: str, db_path: str | None = None) -> dict | None:
    """상세 — 근거 카드와 공급사 비교에 필요한 것을 한 번에 준다 (화면 B)."""
    with connect(db_path) as con:
        po = _df.po_context(con, po_id)
        if po is None:
            return None
        _attach_print_pages(po)

        # 화면 B "실행 로그 전체 보기" 링크 (D21)
        po["trace_url"] = f"/api/chat/{po['session_id']}/trace" if po["session_id"] else None

        # D118·D119 — 자금집행요청서(03) 미리보기. 저장하지 않고 조회 시점에 렌더한다(D86).
        fund_execution = None
        if (fund_inputs := fund_execution_inputs(con, po, db_path)) is not None:
            fund_execution = po_documents.render_fund_execution_document(po, *fund_inputs)

        # D118 — 발주요청서(02)·진단보고서(01)·자금집행요청서(03) 미리보기. 저장하지 않고
        # 조회 시점에 렌더한다(D86 과 같은 이유: 문안이 바뀌면 저장본이 조용히 낡는다).
        po["documents_preview"] = {
            "po_request": po_documents.render_po_request_document(po),
            # 에러코드 진단에서 시작한 발주가 아니면(예: 단종 대체·정기 교체) 진단 보고서
            # 자체가 성립하지 않는다 — 빈 칸투성이 문서 대신 null 을 준다 (D62).
            "diagnosis": po_documents.render_diagnosis_document(po) if po["error_code_def"] else None,
            "fund_execution": fund_execution,
        }
        return po


def transition(
    po_id: str,
    target: str,
    decided_by: str | None = None,
    note: str | None = None,
    db_path: str | None = None,
) -> dict:
    """상태 전이. 현재 상태가 맞지 않으면 TransitionError.

    `now_utc_sql` 은 함수 안에서 지연 임포트한다 — `decisions.py` 가(직접, 그리고
    `disposal.py` 를 거쳐 간접적으로) `po.py` 를 이미 임포트하므로, 이 파일 상단에
    `from backend.services.decisions import now_utc_sql` 을 두면 `po → decisions →
    disposal → po`(초기화 도중, `iso_utc` 미정의) 순환 임포트가 실제로 발생한다
    (실측 확인됨 — `repairs.py` 의 상단 임포트 선례는 `repairs.py` 자신이 그 순환
    사이클에 들어 있지 않아 성립하는 것이라 `po.py` 에는 그대로 적용되지 않는다).
    함수 호출 시점엔 두 모듈이 이미 완전히 로드돼 있어 이 지연 임포트는 안전하다.
    """
    from backend.services.decisions import now_utc_sql

    with FLOW.transition(po_id, target, db_path=db_path) as (con, _row):
        if target == "pending":
            con.execute("UPDATE po_drafts SET state = ? WHERE po_id = ?", (target, po_id))
        else:
            con.execute(
                "UPDATE po_drafts SET state = ?, decided_by = ?, decision_note = ?,"
                " decided_at = ? WHERE po_id = ?",
                (target, decided_by, note, now_utc_sql(), po_id),
            )
    return get_po(po_id, db_path) or {}


def _finance_transition(
    po_id: str,
    target: str,
    finance_decided_by: str,
    note: str | None,
    db_path: str | None = None,
) -> dict:
    """재무 승인 전이. 팀장 전용 `decided_by`/`decision_note`와 별도 컬럼 3종을 쓴다."""
    from backend.services.decisions import now_utc_sql

    with FLOW.transition(po_id, target, db_path=db_path) as (con, _row):
        con.execute(
            "UPDATE po_drafts SET state = ?, finance_decided_by = ?,"
            " finance_decision_note = ?, finance_decided_at = ? WHERE po_id = ?",
            (target, finance_decided_by, note, now_utc_sql(), po_id),
        )
    return get_po(po_id, db_path) or {}


async def dispatch_a2a_withdrawal_request(
    po_id: str,
    base_url: str | None = None,
    db_path: str | None = None,
) -> dict | None:
    """S5: finance_approved 상태의 발주서를 FinAllQ A2A 어댑터(request-withdrawal)로 전송하고 traces에 기록한다."""
    import os
    import uuid
    from backend.a2a.client import call_skill
    from backend.a2a.payloads import build_request_withdrawal_payload, get_finallq_company_id
    from backend.a2a.trace import record_a2a_trace

    finallq_url = base_url or os.environ.get("MAINTQ_A2A_FINALLQ_BASE_URL")
    if not finallq_url:
        return None

    company_id = get_finallq_company_id(db_path)
    if not company_id:
        return None

    po = get_po(po_id, db_path)
    if not po:
        return None

    request_chain_id = f"CHAIN-{po_id}-{uuid.uuid4().hex[:8]}"
    payload = build_request_withdrawal_payload(po, request_chain_id=request_chain_id, db_path=db_path)

    try:
        res = await call_skill(
            partner="finallq",
            skill_id="request-withdrawal",
            payload=payload,
            request_chain_id=request_chain_id,
            base_url=finallq_url,
        )
        record_a2a_trace(
            session_id=po.get("session_id") or "",
            skill_id="request-withdrawal",
            request_payload=payload,
            response_payload=res,
            request_chain_id=request_chain_id,
            status="ok",
            db_path=db_path,
        )
        return res
    except Exception as exc:
        record_a2a_trace(
            session_id=po.get("session_id") or "",
            skill_id="request-withdrawal",
            request_payload=payload,
            response_payload={"error": str(exc)},
            request_chain_id=request_chain_id,
            status="error",
            db_path=db_path,
        )
        raise

