# -*- coding: utf-8 -*-
"""발주 서비스 — 신원 stamp 와 상태 전이.

**신원이 도구 파라미터가 아닌 이유 (D23·D37).**
MCP 도구 스키마에 `requested_by` 가 있으면 LLM 이 그 값을 채울 수 있다 = 위조 경로다.
그래서 도구는 신원 없이 INSERT 하고, 백엔드가 같은 요청 안에서 X-User 값으로 stamp 한다.
백엔드는 사람 쪽 코드라 UPDATE 권한이 있어도 되고(D10 은 MCP 도구만 제약),
LLM 은 이 경로에 개입할 수 없다.

**상태 전이 (docs/06_REPO_API.md §2.4)**
    draft ──submit(정비사)──▶ pending ──approve(팀장)──▶ approved
                                 └──────reject(팀장)──▶ rejected
전이의 주체(역할)는 라우터가, 전이의 순서(현재 상태)는 여기서 강제한다.
"""

from __future__ import annotations

import json
import sqlite3
from pathlib import Path

from backend import manifest
from backend.db import connect
from data import po_draft

# 전이 규칙: 목표 상태 → 허용되는 현재 상태
ALLOWED_FROM: dict[str, str] = {
    "pending": "draft",
    "approved": "pending",
    "rejected": "pending",
}


class TransitionError(Exception):
    """현재 상태에서 할 수 없는 전이."""

    def __init__(self, po_id: str, current: str, target: str) -> None:
        self.po_id, self.current, self.target = po_id, current, target
        super().__init__(
            f"{po_id} 는 지금 '{current}' 상태라 '{target}' 로 전이할 수 없습니다 "
            f"('{ALLOWED_FROM[target]}' 에서만 가능)"
        )


def display_name(user_id: str | None, db_path: Path | None = None) -> str:
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


def iso_utc(ts: str | None) -> str | None:
    """DB 의 naive 문자열 → 타임존이 명시된 ISO-8601.

    SQLite 의 `CURRENT_TIMESTAMP` 는 **UTC** 인데 'YYYY-MM-DD HH:MM:SS' 로만 저장돼
    타임존 표기가 없다. 그대로 내보내면 브라우저가 로컬 시각으로 해석해
    KST 기준 9시간이 어긋난다 (실제로 "방금"이 "9시간 전"으로 보였다).
    저장은 UTC, 전송은 UTC 명시, 표시는 클라이언트가 로컬로 — 경계를 여기서 긋는다.
    """
    if not ts:
        return ts
    return ts.replace(" ", "T") + ("" if ts.endswith("Z") or "+" in ts else "Z")


# 표시명은 users 조인으로 붙인다 (D41) — 행마다 display_name() 을 부르면 N+1 이 된다.
# LEFT JOIN 인 이유: requested_by 는 stamp 전 NULL 이고, 미등록 ID 여도 행이 사라지면 안 된다
_PO_SELECT = (
    "SELECT p.*, pt.name AS part_name, s.name AS supplier_name,"
    " ru.display_name AS requested_by_name, du.display_name AS decided_by_name"
    " FROM po_drafts p"
    " JOIN parts pt ON pt.part_no = p.part_no"
    " JOIN suppliers s ON s.supplier_id = p.supplier_id"
    " LEFT JOIN users ru ON ru.user_id = p.requested_by"
    " LEFT JOIN users du ON du.user_id = p.decided_by"
)




def _row_to_po(r: sqlite3.Row) -> dict:
    d = dict(r)
    d["evidence"] = json.loads(d["evidence"]) if d.get("evidence") else None
    # 미등록·NULL 이면 ID 를 그대로 (display_name() 과 같은 규칙)
    d["requested_by_name"] = d.get("requested_by_name") or d.get("requested_by") or ""
    d["decided_by_name"] = d.get("decided_by_name") or d.get("decided_by") or ""
    d["created_at"] = iso_utc(d.get("created_at"))
    return d


def stamp_identity(
    po_id: str,
    requested_by: str,
    session_id: str | None = None,
    db_path: Path | None = None,
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


def quotes_for_part(part_no: str, db_path: Path | None = None) -> list[dict]:
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
    db_path: Path | None = None,
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
    db_path: Path | None = None,
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


def list_pos(state: str | None = None, db_path: Path | None = None) -> list[dict]:
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
        page = entry.get("manual_page")
        if isinstance(page, int) and not isinstance(page, bool) and page >= 1:
            entry["print_page"] = manifest.to_print_page(model, page)


def get_po(po_id: str, db_path: Path | None = None) -> dict | None:
    """상세 — 근거 카드와 공급사 비교에 필요한 것을 한 번에 준다 (화면 B)."""
    with connect(db_path) as con:
        r = con.execute(_PO_SELECT + " WHERE p.po_id = ?", (po_id,)).fetchone()
        if r is None:
            return None
        po = _row_to_po(r)
        _attach_print_pages(po)

        po["quotes"] = po_draft.list_quotes(con, part_no=po["part_no"])
        po["inventory"] = (
            dict(inv)
            if (
                inv := con.execute(
                    "SELECT qty, safety_stock, location FROM inventory WHERE part_no = ?",
                    (po["part_no"],),
                ).fetchone()
            )
            else None
        )
        # 화면 B "실행 로그 전체 보기" 링크 (D21)
        po["trace_url"] = f"/api/chat/{po['session_id']}/trace" if po["session_id"] else None
        return po


def transition(
    po_id: str,
    target: str,
    decided_by: str | None = None,
    note: str | None = None,
    db_path: Path | None = None,
) -> dict:
    """상태 전이. 현재 상태가 맞지 않으면 TransitionError."""
    with connect(db_path) as con:
        r = con.execute("SELECT state FROM po_drafts WHERE po_id = ?", (po_id,)).fetchone()
        if r is None:
            raise KeyError(po_id)
        if r["state"] != ALLOWED_FROM[target]:
            raise TransitionError(po_id, r["state"], target)

        if target == "pending":
            con.execute("UPDATE po_drafts SET state = ? WHERE po_id = ?", (target, po_id))
        else:
            con.execute(
                "UPDATE po_drafts SET state = ?, decided_by = ?, decision_note = ? WHERE po_id = ?",
                (target, decided_by, note, po_id),
            )
    return get_po(po_id, db_path) or {}


async def dispatch_a2a_withdrawal_request(
    po_id: str,
    base_url: str | None = None,
    db_path: Path | None = None,
) -> dict | None:
    """S5: approved 상태의 발주서를 FinAllQ A2A 어댑터(request-withdrawal)로 전송하고 traces에 기록한다."""
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

