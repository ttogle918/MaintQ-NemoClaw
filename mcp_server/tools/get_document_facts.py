# -*- coding: utf-8 -*-
"""get_document_facts — 결재 문서에 실제로 찍힐 값을 **조회만** 한다 (D125).

**이 파일은 얇은 래퍼다** (`track_deadlines.py` 와 같은 구조). 필드맵 산출은
`data/doc_fields.py` 에 있다. 여기 남는 것은 둘뿐이다:
  1. `DESCRIPTION` — `04 §21` 이 정본으로 인용한다
  2. 커넥션 수명 (`read_only()`)

★ 이 도구는 아무것도 쓰지 않는다 (D10)
────────────────────────────────────────────────────────────────────────────────
`read_only()` 만 쓴다 — `draft_writer()`·`decision_writer()`·`repair_writer()` 를
부르지 않는다. 값을 고치려면 `create_po_draft` 로 **새 draft 를 INSERT** 하거나
사람이 화면에서 수정한다(`PATCH /api/po`(D111)·`/api/repairs`·`/api/decisions`).

  MCP UPDATE 로 얻는 건 "이미 만든 걸 대화로 고치기" 하나인데, 잃는 건 이 프로젝트가
  내세우는 문장 자체다 — *"AI 가 제안하고 사람이 결정한다"*.

  처분(05·06)은 더 심하다: `assets` 를 고치면 `bundle_hash` 가 달라지고 `sign()` 이
  `EvidenceChanged` 로 서명을 막는다(D84). 사용자에겐 *"고쳤더니 결재가 안 된다"* 로
  나타난다.

★ 신원·서명 필드는 애초에 만들어지지 않는다 (D23·D81)
────────────────────────────────────────────────────────────────────────────────
`data/doc_fields.py` 가 `WITHHELD_KEYS` 를 **만들지 않으므로** 여기서 뺄 일도 없다.
목록만 `withheld` 로 함께 실어 *"안 준다"* 를 밝힌다.

★ `withheld` 와 `unavailable` 을 나눠 싣는 이유 (D62)
────────────────────────────────────────────────────────────────────────────────
**"안 준다"와 "없다"는 다른 사실이다.** 하나로 합치면 에이전트가 *"요청자 이름이
시스템에 없다"* 고 말하게 되는데, 그건 거짓이다 — 있고, 주지 않을 뿐이다.

★ 03(자금집행요청서)은 대상이 아니다
────────────────────────────────────────────────────────────────────────────────
03 의 핵심은 예산 한도·1일 누적 한도·FDS·직무분리 **내부통제 판정**(D119)인데,
`create_po_draft` 로 새 draft 를 넣어도 달라지지 않는다 — **교정 경로가 없는 값**이다.
도구가 고칠 수 없는 값을 보여주면 에이전트가 그것을 두고 대화하게 된다.
(docx 다운로드는 03 을 포함해 5종 전부 지원한다 — 제외는 이 도구의 범위에만 적용된다.)
"""

from __future__ import annotations

from data import doc_fields as df

from ..db import read_only

DOC_TYPES = ("po", "disposal")

_UNAVAILABLE_PO = {
    "03": (
        "자금집행요청서(03)의 내부통제 판정(예산 한도·1일 누적 한도·FDS·직무분리)은 "
        "재무 승인 경로에서만 산출되며 이 도구가 조회할 수 없습니다."
    )
}

_NO_ERROR_CODE = (
    "설비이상진단보고서(01)는 이 발주에 에러코드 정의가 없어 만들 수 없습니다 "
    "(model·error_code 가 비었거나 error_codes 정본에 없는 코드입니다)."
)

CORRECTION_HINT = (
    "이 도구는 조회만 합니다. 값이 틀렸다면 create_po_draft 로 새 초안을 만들어 다시 "
    "제안하거나, 사람이 화면에서 직접 수정하도록 안내하세요 "
    "(PATCH /api/po · /api/repairs · /api/decisions). 기존 초안을 이 도구로 고칠 수는 없습니다."
)

DESCRIPTION = (
    "결재 문서에 실제로 찍힐 값을 문서 양식의 자리 이름 그대로 조회한다. "
    "doc_type='po' 면 설비이상진단보고서(01)·정비부품발주요청서(02), "
    "doc_type='disposal' 이면 설비처분승인서(05)·진술및보장서(06) 의 필드맵을 돌려준다. "
    "발주·처분 초안의 내용을 확인하거나 어느 항목이 비었는지 짚어 말할 때 쓸 것. "
    "'확인되지 않음' 은 '해당 없음' 이 아니라 시스템에 원천이 없다는 뜻이므로 추측으로 "
    "채워 말하지 말 것. 요청자·승인자 이름과 서명 정보는 이 도구가 돌려주지 않는다"
    "(withheld 목록 참조) — 없는 것이 아니라 도구에 노출하지 않는 값이다. "
    "이 도구는 조회만 하며 아무것도 수정하지 않는다. 값을 고치려면 create_po_draft 로 "
    "새 초안을 만들거나 사람이 화면에서 수정해야 한다."
)


def _po_payload(con, ref_id: str) -> dict | None:
    ctx = df.po_context(con, ref_id)
    if ctx is None:
        return None
    fields = {"02": df.fields_02(ctx)}
    unavailable = dict(_UNAVAILABLE_PO)
    if ctx.get("error_code_def"):
        fields["01"] = df.fields_01(ctx)
    else:
        # 빈 칸투성이 문서를 만들지 않는다 — 미리보기도 같은 조건에서 None 이다 (D62).
        unavailable["01"] = _NO_ERROR_CODE
    return {"fields": fields, "unavailable": unavailable}


def _disposal_payload(con, ref_id: str) -> dict | None:
    ctx = df.disposal_context(con, ref_id)
    if ctx is None:
        return None
    common = {
        "verdict": ctx["verdict"],
        "bundle_hash": ctx["bundle_hash"],
        "decision_id": ctx["decision_id"],
        "doc_state": ctx["state"],
        "created_at": ctx["created_at"],
    }
    return {
        "fields": {
            "05": df.fields_05(ctx["bundle"], reason=ctx["reason"], **common),
            "06": df.fields_06(ctx["bundle"], **common),
        },
        "unavailable": {},
    }


def get_document_facts(doc_type: str, ref_id: str) -> dict:
    if doc_type not in DOC_TYPES:
        return {
            "status": "error",
            "reason": "invalid_input",
            "message": f"doc_type 은 {' | '.join(DOC_TYPES)} 중 하나여야 합니다: {doc_type!r}",
        }
    if not (ref_id or "").strip():
        return {"status": "error", "reason": "invalid_input", "message": "ref_id 가 비었습니다"}

    try:
        with read_only() as con:
            payload = (
                _po_payload(con, ref_id)
                if doc_type == "po"
                else _disposal_payload(con, ref_id)
            )
    except FileNotFoundError as e:
        return {"status": "error", "reason": "db_missing", "message": str(e)}
    except Exception as e:  # noqa: BLE001 — 도구는 예외를 던지지 않는다 (D9)
        return {"status": "error", "reason": "db_error", "message": str(e)}

    if payload is None:
        return {
            "status": "error",
            "reason": "not_found",
            "message": f"{doc_type} 초안을 찾을 수 없습니다: {ref_id}",
        }

    return {
        "status": "ok",
        "doc_type": doc_type,
        "ref_id": ref_id,
        "fields": payload["fields"],
        "withheld": sorted(df.WITHHELD_KEYS),
        "unavailable": payload["unavailable"],
        "correction_hint": CORRECTION_HINT,
    }
