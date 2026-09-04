# -*- coding: utf-8 -*-
"""MCP 서버 엔트리포인트 (D15 — 백엔드와 프로세스 분리).

목업 DB를 실제 ERP로 갈아끼울 때 이 서버만 교체하면 되는 구조가 핵심이다.

코어 7종 (프로파일과 무관하게 항상 등록):
  - lookup_error_code         에러코드 정의·원인·조치 (exact match)
  - rag_search_manual         매뉴얼 본문 서술형 검색 (하이브리드, D47)
  - search_inventory          재고·안전재고·단종
  - find_alternative_parts    호환 대체품
  - get_supplier_quotes       리드타임·단가·MOQ
  - get_error_history         반복 고장 판정
  - create_po_draft           발주 초안 (유일한 쓰기 도구)

확장 14종 (`MAINTQ_TOOLS_PROFILE=full` 일 때만 등록 — D69):
  - check_disposal_blockers · verify_ownership · classify_part_criticality ·
    get_maintenance_metrics · classify_expenditure · assess_repair_value ·
    build_evidence_bundle · generate_disposal_document (**두 번째 쓰기 도구**) ·
    create_repair_record (**세 번째 쓰기 도구**, D98) ·
    track_deadlines · assess_risk_grade (Sprint 11, D102) ·
    search_insurance_clause · assess_equipment_loan (Sprint 16, MQ-1603 —
    백엔드 REST 를 HTTP 로 호출할 뿐 자격증명·파트너 대장을 참조하지 않는다)

**기본이 `core` 인 이유(D69)**: `eval/run_eval.py` 가 부모 env 를 상속해 이 서버를 띄우므로
기본이 `full` 이면 평가가 아무 표시 없이 확장 프롬프트로 돈다 — 그러면 "수정 효과 vs
도구 증가 효과"를 분리할 수 없다. enum 밖 값은 **폴백하지 않고 죽는다**: 조용히 core 로
떨어지면 "어느 프로파일로 돌았는지 모르는 실행 결과"가 남는다.

주의: `error_codes` 는 사람 승인 전이라 아직 0행이다. 그래서 lookup_error_code 는
실데이터에서 `status:"error"` + `reason:"catalog_not_loaded"` 를 돌려준다 (D50) —
not_found 가 아니라 미적재라고 정직하게 실패하는 게 의도된 동작이다.

실행:  uv run python mcp_server/server.py
       MAINTQ_TOOLS_PROFILE=full uv run python mcp_server/server.py
"""

from __future__ import annotations

import os
import sys
from pathlib import Path
from typing import Annotated

# 스크립트로 직접 실행될 때도 `mcp_server` 패키지로 임포트되게 한다
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from mcp.server.fastmcp import FastMCP  # noqa: E402
from pydantic import Field  # noqa: E402

from mcp_server.tools.create_po_draft import (  # noqa: E402
    DESCRIPTION as PO_DESC,
    create_po_draft as _create_po_draft,
)
from mcp_server.tools.find_alternative_parts import (  # noqa: E402
    DESCRIPTION as ALT_DESC,
    find_alternative_parts as _find_alternative_parts,
)
from mcp_server.tools.get_error_history import (  # noqa: E402
    DESCRIPTION as HIST_DESC,
    get_error_history as _get_error_history,
)
from mcp_server.tools.get_supplier_quotes import (  # noqa: E402
    DESCRIPTION as QUOTE_DESC,
    get_supplier_quotes as _get_supplier_quotes,
)
from mcp_server.tools.lookup_error_code import (  # noqa: E402
    DESCRIPTION as LOOKUP_DESC,
    lookup_error_code as _lookup_error_code,
)
from mcp_server.tools.rag_search_manual import (  # noqa: E402
    DESCRIPTION as RAG_DESC,
    rag_search_manual as _rag_search_manual,
)
from mcp_server.tools.search_inventory import (  # noqa: E402
    DESCRIPTION as INV_DESC,
    search_inventory as _search_inventory,
)

TOOLS_PROFILE = os.environ.get("MAINTQ_TOOLS_PROFILE") or "core"
if TOOLS_PROFILE not in ("core", "full"):
    # 폴백 금지 (D69). 오타 하나가 "확장 도구가 없는 이유"를 미궁으로 만든다.
    raise SystemExit(f"MAINTQ_TOOLS_PROFILE 은 core|full 이어야 합니다: {TOOLS_PROFILE!r}")

mcp = FastMCP("maintq")


@mcp.tool(description=LOOKUP_DESC)
def lookup_error_code(model: str, code: str) -> dict:
    """model 은 enum('iG5A','S100','IE5') 강제 (D6·D13·D109). 표에 없으면 not_found —
    유사 코드를 추측해 돌려주지 않는다. 0행이면 not_found 가 아니라 error/catalog_not_loaded (D50)."""
    return _lookup_error_code(model=model, code=code)


@mcp.tool(description=RAG_DESC)
def rag_search_manual(model: str, query: str, top_k: int = 3) -> dict:
    """절차·배경 등 서술형 정보만. 에러코드 정의는 lookup_error_code 다 (D1).
    결과가 없으면 empty — 이때 절차를 지어내지 않는다."""
    return _rag_search_manual(model=model, query=query, top_k=top_k)


@mcp.tool(description=INV_DESC)
def search_inventory(
    part_no: str | None = None,
    part_name: str | None = None,
    model: str | None = None,
) -> dict:
    return _search_inventory(part_no=part_no, part_name=part_name, model=model)


@mcp.tool(description=ALT_DESC)
def find_alternative_parts(part_no: str) -> dict:
    return _find_alternative_parts(part_no=part_no)


@mcp.tool(description=QUOTE_DESC)
def get_supplier_quotes(part_no: str, qty: int = 1) -> dict:
    return _get_supplier_quotes(part_no=part_no, qty=qty)


@mcp.tool(description=HIST_DESC)
def get_error_history(
    equipment_id: str | None = None,
    # int 로 좁히면 LLM 이 라인 **이름**("2번 가공라인")을 넣었을 때 스키마 검증이 예외를
    # 던져 도구가 status 로 실패를 못 돌려준다 (D9 위반). 넓게 받아 도구 안에서 판정한다.
    line_id: int | str | None = None,
    code: str | None = None,
    days: int | str = 30,
) -> dict:
    return _get_error_history(equipment_id=equipment_id, line_id=line_id, code=code, days=days)


@mcp.tool(description=PO_DESC)
def create_po_draft(
    part_no: str,
    qty: int,
    supplier_id: str,
    reason: str,
    urgency: str = "normal",
    model: str | None = None,
    error_code: str | None = None,
    evidence: dict | None = None,
) -> dict:
    """⚠️ 유일한 쓰기 도구. 신원(requested_by)·session_id 는 **파라미터에 없다** —
    스키마에 없으므로 LLM 이 위조할 수 없고, 백엔드가 INSERT 직후 stamp 한다 (D23·D37)."""
    return _create_po_draft(
        part_no=part_no,
        qty=qty,
        supplier_id=supplier_id,
        reason=reason,
        urgency=urgency,
        model=model,
        error_code=error_code,
        evidence=evidence,
    )


# ─────────────────────────────────────────────────────────────────────────────
# 확장 14종 — `MAINTQ_TOOLS_PROFILE=full` 에서만 등록한다 (D69·D98·D102·D112·D125)
#
# ★ 파라미터 타입을 좁히지 않는다. `get_error_history.line_id` 주석과 같은 이유다 —
#   타입을 좁히면 LLM 이 문자열로 넘긴 순간 pydantic 이 본체 진입 전에 예외를 던져
#   도구가 `status` 로 실패를 못 돌려준다 (D9 위반). 넓게 받아 도구 안에서 판정한다.
# ★ 반대로 **필수 파라미터에는 기본값을 두지 않는다** (D80). 기본값을 두면 FastMCP 가
#   `required` 에서 빼 optional 로 노출하고, LLM 이 인자 없이 호출 → `invalid_input`
#   → 재시도하는 낭비 루프가 생긴다. 두 규칙은 충돌하지 않는다 —
#   "받는 타입은 넓게, 안 받는 것은 불가능하게".
# ★ `DESCRIPTION` 은 도구 파일 소유라 여기서 고치지 않는다. 도구 문안이 말하지 않는
#   호출 요령(특히 `disposal_date`)은 **파라미터 스키마 설명**으로 유도한다.
# ─────────────────────────────────────────────────────────────────────────────

# 인용 조문의 시점 판정·세액공제 잔존기간이 이 값에 걸려 있다. 없으면 `TAX-CREDIT-2Y` 가
# 항상 `INSUFFICIENT_FACTS` 라 verdict 가 늘 `INSUFFICIENT_FACTS` 로 수렴한다 (D62 —
# 모르는 날짜를 오늘로 메우지 않기 때문이다). 그래서 스키마 설명에서 명시적으로 유도한다.
_DISPOSAL_DATE_FIELD = Field(
    default=None,
    description=(
        "처분 예정일 (ISO 'YYYY-MM-DD'). 알고 있으면 반드시 함께 넘길 것 — "
        "없으면 세액공제 조항(TAX-CREDIT-2Y)이 사실 부족으로 남아 판정이 "
        "INSUFFICIENT_FACTS 에 머문다. 모르는 날짜를 오늘로 대체하지 말 것."
    ),
)
_DISPOSAL_MODE_FIELD = Field(
    default="SALE",
    description="처분 방식 — SALE | SCRAP | TRANSFER 중 하나. 유사어를 임의로 해석하지 않는다.",
)

if TOOLS_PROFILE == "full":
    from mcp_server.tools.assess_repair_value import (  # noqa: E402
        DEFAULT_REPAIR_SCOPE,
        DESCRIPTION as REPAIR_VALUE_DESC,
        assess_repair_value as _assess_repair_value,
    )
    from mcp_server.tools.build_evidence_bundle import (  # noqa: E402
        DESCRIPTION as BUNDLE_DESC,
        build_evidence_bundle as _build_evidence_bundle,
    )
    from mcp_server.tools.check_disposal_blockers import (  # noqa: E402
        DESCRIPTION as DISPOSAL_DESC,
        check_disposal_blockers as _check_disposal_blockers,
    )
    from mcp_server.tools.classify_expenditure import (  # noqa: E402
        DESCRIPTION as EXPENDITURE_DESC,
        classify_expenditure as _classify_expenditure,
    )
    from mcp_server.tools.classify_part_criticality import (  # noqa: E402
        DESCRIPTION as CRITICALITY_DESC,
        classify_part_criticality as _classify_part_criticality,
    )
    from mcp_server.tools.create_repair_record import (  # noqa: E402
        DESCRIPTION as REPAIR_RECORD_DESC,
        create_repair_record as _create_repair_record,
    )
    from mcp_server.tools.generate_disposal_document import (  # noqa: E402
        DESCRIPTION as DISPOSAL_DOC_DESC,
        generate_disposal_document as _generate_disposal_document,
    )
    from mcp_server.tools.get_maintenance_metrics import (  # noqa: E402
        DEFAULT_WINDOW_MONTHS,
        DESCRIPTION as METRICS_DESC,
        get_maintenance_metrics as _get_maintenance_metrics,
    )
    from mcp_server.tools.verify_ownership import (  # noqa: E402
        DESCRIPTION as OWNERSHIP_DESC,
        verify_ownership as _verify_ownership,
    )
    from mcp_server.tools.track_deadlines import (  # noqa: E402
        DEFAULT_WINDOW_DAYS,
        DESCRIPTION as DEADLINES_DESC,
        track_deadlines as _track_deadlines,
    )
    from mcp_server.tools.assess_risk_grade import (  # noqa: E402
        DESCRIPTION as RISK_GRADE_DESC,
        assess_risk_grade as _assess_risk_grade,
    )
    from mcp_server.tools.search_insurance_clause import (  # noqa: E402
        DESCRIPTION as INSURANCE_CLAUSE_DESC,
        search_insurance_clause as _search_insurance_clause,
    )
    from mcp_server.tools.assess_equipment_loan import (  # noqa: E402
        DESCRIPTION as EQUIPMENT_LOAN_DESC,
        assess_equipment_loan as _assess_equipment_loan,
    )
    from mcp_server.tools.get_document_facts import (  # noqa: E402
        DESCRIPTION as DOC_FACTS_DESC,
        get_document_facts as _get_document_facts,
    )

    @mcp.tool(description=DISPOSAL_DESC)
    def check_disposal_blockers(
        asset_id: str | None = None,
        equipment_id: str | None = None,
        disposal_mode: Annotated[str, _DISPOSAL_MODE_FIELD] = "SALE",
        disposal_date: Annotated[str | None, _DISPOSAL_DATE_FIELD] = None,
    ) -> dict:
        """`asset_id`·`equipment_id` 는 **둘 중 하나 필수**라 스키마상 둘 다 optional 이다
        (D80 의 either-or 공백). 둘 다 비면 도구가 `invalid_input` 으로 되돌린다."""
        return _check_disposal_blockers(
            asset_id=asset_id,
            equipment_id=equipment_id,
            disposal_mode=disposal_mode,
            disposal_date=disposal_date,
        )

    @mcp.tool(description=OWNERSHIP_DESC)
    def verify_ownership(
        asset_id: str | None = None,
        equipment_id: str | None = None,
    ) -> dict:
        return _verify_ownership(asset_id=asset_id, equipment_id=equipment_id)

    @mcp.tool(description=CRITICALITY_DESC)
    def classify_part_criticality(part_no: str) -> dict:
        """`part_no` 는 필수 — 기본값을 두지 않는다 (D80)."""
        return _classify_part_criticality(part_no=part_no)

    @mcp.tool(description=METRICS_DESC)
    def get_maintenance_metrics(
        asset_id: str | None = None,
        equipment_id: str | None = None,
        # 좁히면 LLM 이 "12개월" 같은 문자열을 넣었을 때 스키마가 예외를 던진다 (D9).
        window_months: int | str = DEFAULT_WINDOW_MONTHS,
    ) -> dict:
        return _get_maintenance_metrics(
            asset_id=asset_id, equipment_id=equipment_id, window_months=window_months
        )

    @mcp.tool(description=EXPENDITURE_DESC)
    def classify_expenditure(
        part_class: Annotated[
            str,
            Field(
                description=(
                    "부품 등급 — CRITICAL | STANDARD | CONSUMABLE. "
                    "모르면 classify_part_criticality 로 먼저 조회할 것 (추측 금지)."
                )
            ),
        ],
        repair_scope: Annotated[
            str,
            Field(description="수리 범위 — RESTORE(원상 회복) | UPGRADE(성능·내용연수 향상)."),
        ],
        amount: Annotated[
            int | str,
            Field(description="지출 금액(원, 0 초과). 견적·단가 조회 결과의 값만 쓸 것."),
        ],
        asset_id: str | None = None,
    ) -> dict:
        """★ D80 — `part_class`·`repair_scope`·`amount` 에 기본값을 두지 않는다.
        기본값을 두는 순간 스키마에서 optional 이 되어 LLM 이 인자 없이 부르고,
        도구는 `invalid_input` 을 돌려주며 재시도 루프가 생긴다. `asset_id` 만 optional 이다
        (없으면 20% 중요성 판단을 하지 않았다고 결과가 스스로 밝힌다)."""
        return _classify_expenditure(
            part_class=part_class,
            repair_scope=repair_scope,
            amount=amount,
            asset_id=asset_id,
        )

    @mcp.tool(description=REPAIR_VALUE_DESC)
    def assess_repair_value(
        equipment_id: str,
        failed_part: Annotated[
            str, Field(description="고장 부품 품번 — lookup_error_code 의 related_parts 값을 쓸 것.")
        ],
        repair_cost: Annotated[
            int | str,
            Field(
                description=(
                    "예상 수리비(원). 이 도구는 적정성을 검증하지 않는다 — "
                    "견적은 get_supplier_quotes 로 확인한 값을 넣을 것."
                )
            ),
        ],
        repair_scope: str = DEFAULT_REPAIR_SCOPE,
    ) -> dict:
        """`equipment_id`·`failed_part`·`repair_cost` 는 필수 (D80).
        verdict 가 `ROOT_CAUSE_FIRST` 면 3지 선택지 자체를 제시하지 않는다 (규칙 14)."""
        return _assess_repair_value(
            equipment_id=equipment_id,
            failed_part=failed_part,
            repair_cost=repair_cost,
            repair_scope=repair_scope,
        )

    @mcp.tool(description=BUNDLE_DESC)
    def build_evidence_bundle(
        asset_id: str | None = None,
        equipment_id: str | None = None,
        disposal_mode: Annotated[str, _DISPOSAL_MODE_FIELD] = "SALE",
        disposal_date: Annotated[str | None, _DISPOSAL_DATE_FIELD] = None,
    ) -> dict:
        """판정하지도 저장하지도 않는다 — 근거를 묶어 해시로 고정할 뿐이다 (D10)."""
        return _build_evidence_bundle(
            asset_id=asset_id,
            equipment_id=equipment_id,
            disposal_mode=disposal_mode,
            disposal_date=disposal_date,
        )

    @mcp.tool(description=DISPOSAL_DOC_DESC)
    def generate_disposal_document(
        reason: Annotated[
            str,
            Field(
                description=(
                    "처분을 요청하는 사유. 사용자가 밝힌 근거를 그대로 적을 것 — "
                    "승인자가 판단 근거를 추적한다. 지어내지 말고 없으면 먼저 물어볼 것."
                )
            ),
        ],
        asset_id: str | None = None,
        equipment_id: str | None = None,
        disposal_mode: Annotated[str, _DISPOSAL_MODE_FIELD] = "SALE",
        disposal_date: Annotated[str | None, _DISPOSAL_DATE_FIELD] = None,
    ) -> dict:
        """⚠️ 두 번째 쓰기 도구. `decisions` 에 **draft INSERT 만** 한다 (D10).

        ★ `override`·`override_reason`·`reviewed_by` 파라미터를 **여기에 추가하지 말 것** (D81).
          스키마에 키가 없어야 LLM 이 BLOCKING 을 뚫는 사유를 지어내 호출하는 경로가
          구조적으로 막힌다 — D23(신원)·D31(단가)을 파라미터에서 뺀 것과 같은 이유다.
          예외 적용은 서명 API 가 `X-User` 와 함께 받는다.
        ★ `reason` 은 필수 — 기본값을 두지 않는다 (D80).
        """
        return _generate_disposal_document(
            reason=reason,
            asset_id=asset_id,
            equipment_id=equipment_id,
            disposal_mode=disposal_mode,
            disposal_date=disposal_date,
        )

    @mcp.tool(description=REPAIR_RECORD_DESC)
    def create_repair_record(
        equipment_id: str,
        work_type: Annotated[
            str, Field(description="PLANNED | UNPLANNED. 미기재 거부 — 기본값이 없다 (12 §7).")
        ],
        repair_scope: Annotated[
            str,
            Field(description="RESTORE | UPGRADE | OVERHAUL | REPLACE_UNIT. 폴백하지 않는다."),
        ],
        cost: Annotated[
            int | str, Field(description="수리 비용(원, 0 초과). 견적·청구 금액만 넣을 것.")
        ],
        parts: Annotated[
            list[dict],
            Field(
                description=(
                    "교체한 부품 배열, 1건 이상. 각 항목은 {part_no(필수), serial, qty} — "
                    "등록되지 않은 part_no 는 거부된다(unknown_part)."
                )
            ),
        ],
        downtime_hours: float | int | str | None = None,
        model: str | None = None,
        error_code: str | None = None,
        note: str | None = None,
    ) -> dict:
        """⚠️ 세 번째 쓰기 도구. `repair_records` 에 **draft INSERT 만** 한다 (D10·D98).

        ★ `performed_by`·`verified_by`·`signed_at`·`record_hash`·`requested_by`·`session_id`·
          `state` 는 파라미터에 **없다** — 스키마에 없으므로 LLM 이 채울 수 없고, 도구가
          NULL 리터럴로 박거나(`state`만 `'draft'` 리터럴) 백엔드가 서명 API 에서 stamp 한다.
        ★ `part_class`·`expenditure_class` 도 파라미터가 아니다 — 전자는 `parts` 조회,
          후자는 `data/maint_value.expenditure()` 산출이다. LLM 이 회계 판정을 지어낼
          경로를 막는다 (D31·D81 과 같은 이유).
        ★ `equipment_id`·`work_type`·`repair_scope`·`cost`·`parts` 는 필수 (D80).
        """
        return _create_repair_record(
            equipment_id=equipment_id,
            work_type=work_type,
            repair_scope=repair_scope,
            cost=cost,
            parts=parts,
            downtime_hours=downtime_hours,
            model=model,
            error_code=error_code,
            note=note,
        )

    @mcp.tool(description=DEADLINES_DESC)
    def track_deadlines(
        asset_id: str | None = None,
        # 좁히면 LLM 이 문자열로 넘겼을 때 스키마가 예외를 던진다 (D9, get_error_history.days 와 같은 이유).
        window_days: int | str = DEFAULT_WINDOW_DAYS,
    ) -> dict:
        """읽기 전용 — 아무것도 쓰지 않는다. 기본 호출이 0건이어도 실패가 아니다 (D62)."""
        return _track_deadlines(asset_id=asset_id, window_days=window_days)

    @mcp.tool(description=RISK_GRADE_DESC)
    def assess_risk_grade(
        building_id: str | None = None,
        asset_id: str | None = None,
    ) -> dict:
        """`building_id`·`asset_id` 는 **둘 중 하나 필수**라 스키마상 둘 다 optional 이다
        (D80 의 either-or 공백). 둘 다 비거나 둘 다 있으면 도구가 `invalid_input` 으로 되돌린다."""
        return _assess_risk_grade(building_id=building_id, asset_id=asset_id)

    @mcp.tool(description=INSURANCE_CLAUSE_DESC)
    def search_insurance_clause(question: str) -> dict:
        """`question` 은 필수 (D80). MaintQ 백엔드 REST(`/api/a2a/lookup-clause`)를 HTTP 로
        호출할 뿐 A2A 자격증명·파트너 대장을 직접 참조하지 않는다 (D15·D93)."""
        return _search_insurance_clause(question=question)

    @mcp.tool(description=EQUIPMENT_LOAN_DESC)
    def assess_equipment_loan(
        loan_amount: float, purpose: str, collateral_building_id: str
    ) -> dict:
        """세 파라미터 전부 필수 (D80). MaintQ 백엔드 REST(`/api/a2a/assess-loan`)를 HTTP 로
        호출할 뿐 A2A 자격증명·파트너 대장을 직접 참조하지 않는다 (D15·D93)."""
        return _assess_equipment_loan(
            loan_amount=loan_amount, purpose=purpose, collateral_building_id=collateral_building_id
        )

    @mcp.tool(description=DOC_FACTS_DESC)
    def get_document_facts(
        doc_type: Annotated[
            str,
            Field(
                description=(
                    "문서 종류 — po(발주: 설비이상진단보고서 01 · 정비부품발주요청서 02) | "
                    "disposal(처분: 설비처분승인서 05 · 진술및보장서 06)."
                )
            ),
        ],
        ref_id: Annotated[
            str, Field(description="발주 ID(예: PO-0117) 또는 처분 결정 ID(예: DEC-0007).")
        ],
    ) -> dict:
        """둘 다 필수 — 기본값을 두지 않는다 (D80).

        **읽기 전용이다** (D10·D125). 이 도구로 초안을 고칠 수 없다 — 교정은
        `create_po_draft` 새 INSERT 또는 사람의 화면 수정이다."""
        return _get_document_facts(doc_type=doc_type, ref_id=ref_id)


if __name__ == "__main__":
    mcp.run()
